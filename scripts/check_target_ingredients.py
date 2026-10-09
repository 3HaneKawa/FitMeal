# -*- coding: utf-8 -*-
"""校验 data/target_ingredients.csv。

检查项（任一失败即退出码 1）：
1. 表头与列顺序
2. ingredient 唯一、非空
3. priority / category 取值合法
4. target_recipes / current_recipes 为非负整数，并记录当前覆盖状态
5. ingredient 必须存在于 nutrition.csv
6. category 与 nutrition.csv 的食材类别一致（主料 / 辅料 映射）
7. current_recipes 与按 recipes.csv 实时统计的道数一致
8. 文件编码与行尾（UTF-8 无 BOM、LF）

只读，不修改任何数据文件。

用法：

    uv run --python 3.12 python scripts/check_target_ingredients.py
"""

import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TARGET_FILE = DATA_DIR / "target_ingredients.csv"

EXPECTED_FIELDS = [
    "ingredient", "category", "priority", "target_recipes",
    "current_recipes", "reason", "note",
]
PRIORITIES = {"P0", "P1", "P2"}
CATEGORIES = {"主料", "辅料"}

# nutrition.csv 的 category -> 清单里的 主料 / 辅料
MAIN_CATEGORIES = {"protein", "carb", "vegetable", "fruit", "seafood"}
SUPPORT_CATEGORIES = {"dairy", "fat", "sugar", "sauce", "other"}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_alias_map():
    return {r["alias"].strip(): r["standard"].strip()
            for r in read_csv(DATA_DIR / "ingredient_aliases.csv")}


def split_ingredients(text, alias_map):
    names = []
    for item in (text or "").split(";"):
        item = item.strip()
        if not item:
            continue
        raw = item.split(":")[0].strip()
        names.append(alias_map.get(raw, raw))
    return names


def live_counts(alias_map):
    counts = {}
    for r in read_csv(DATA_DIR / "recipes.csv"):
        for name in set(split_ingredients(r["ingredients"], alias_map)):
            counts[name] = counts.get(name, 0) + 1
    return counts


def main():
    errors = []
    warnings = []

    if not TARGET_FILE.exists():
        print(f"FAIL 找不到 {TARGET_FILE}")
        return 1

    raw = TARGET_FILE.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("文件带 BOM，应保持 UTF-8 无 BOM")
    if b"\r\n" in raw:
        errors.append("文件使用 CRLF，应保持 LF")
    if not raw.endswith(b"\n"):
        warnings.append("文件末尾没有换行符")

    with TARGET_FILE.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)

    if fields != EXPECTED_FIELDS:
        errors.append(f"表头不符：期望 {EXPECTED_FIELDS}，实际 {fields}")

    nutrition = {r["name"].strip(): r["category"].strip()
                 for r in read_csv(DATA_DIR / "nutrition.csv")}
    counts = live_counts(build_alias_map())

    seen = set()
    for i, row in enumerate(rows, start=2):
        name = (row.get("ingredient") or "").strip()
        if not name:
            errors.append(f"第 {i} 行 ingredient 为空")
            continue
        if name in seen:
            errors.append(f"第 {i} 行 ingredient 重复：{name}")
        seen.add(name)

        cat = (row.get("category") or "").strip()
        if cat not in CATEGORIES:
            errors.append(f"第 {i} 行 category 非法：{cat!r}")

        pri = (row.get("priority") or "").strip()
        if pri not in PRIORITIES:
            errors.append(f"第 {i} 行 priority 非法：{pri!r}")

        try:
            target = int(row["target_recipes"])
            current = int(row["current_recipes"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"第 {i} 行 target/current 不是整数")
            continue
        if target < 0 or current < 0:
            errors.append(f"第 {i} 行 target/current 出现负数")
        if name not in nutrition:
            errors.append(f"第 {i} 行 {name} 不在 nutrition.csv 中")
            continue

        ncat = nutrition[name]
        if ncat in MAIN_CATEGORIES and cat != "主料":
            errors.append(f"第 {i} 行 {name} 在营养库属 {ncat}，清单却标 {cat}")
        elif ncat in SUPPORT_CATEGORIES and cat != "辅料":
            errors.append(f"第 {i} 行 {name} 在营养库属 {ncat}，清单却标 {cat}")
        elif ncat not in MAIN_CATEGORIES | SUPPORT_CATEGORIES:
            warnings.append(f"第 {i} 行 {name} 的营养库类别 {ncat} 未归类")

        live = counts.get(name, 0)
        if live != current:
            errors.append(
                f"第 {i} 行 {name} current_recipes={current}，实时统计为 {live}"
            )

    by_priority = {}
    for row in rows:
        by_priority.setdefault(row["priority"], []).append(row)

    print(f"清单条数        : {len(rows)}")
    print(f"与营养库不一致  : {len([e for e in errors if '不在 nutrition' in e])}")
    for pri in sorted(by_priority):
        done = sum(1 for r in by_priority[pri]
                   if int(r["current_recipes"]) >= int(r["target_recipes"]))
        print(f"  {pri}: {len(by_priority[pri])} 项，已达标 {done} 项")

    print()
    if warnings:
        print("警告：")
        for w in warnings:
            print(f"  - {w}")
    if errors:
        print("校验未通过：")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("PASS 目标食材清单校验通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
