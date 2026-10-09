# -*- coding: utf-8 -*-
"""中国食物成分表（标准版 第6版）来源管线。

背景与定位：

- ``data/nutrition.csv`` 里仍有一批中式食材，``source=local`` 且 ``confidence=L2``
  （多为「USDA 无同口径条目 + 本地估算」）。USDA 覆盖不到的地方，需要用中国本地
  权威源补位。
- 本脚本把《中国食物成分表 标准版（第6版）》第一册「能量和食物一般营养成分」的
  结构化表格作为本地权威源，逐条把 L2 转正为 L3（每 100g 可食部）。

数据底座（离线）：

- ``data/sources/cfct/raw_json/merged_*.json``  按分类拆分的基础表格
- ``data/sources/cfct/cfct_index.csv``          由 ``build`` 生成的扁平索引
- 数值来源：开源数字化项目 ``Sanotsu/china-food-composition-data``（对原书表格做
  双模型交叉识别 + 恒等式/值域校验，并附原始截图）。本项目仅转录数值，著作权归
  原书作者；本仓库保留索引与映射作为可追溯引用。

子命令：

    uv run --python 3.12 python scripts/cn_food_composition.py build     # 建本地索引
    uv run --python 3.12 python scripts/cn_food_composition.py search 山药  # 查候选条目
    uv run --python 3.12 python scripts/cn_food_composition.py report    # 生成差异报告
    uv run --python 3.12 python scripts/cn_food_composition.py apply     # 按映射落库

映射表：``data/sources/cn_food_composition.csv``（人工审核的「本地食材 -> 食物成分表条目」）。
``apply`` 走 ``scripts/data_store.py`` 原子写入，只动营养列与来源列，不改口径。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

import data_store
from data_store import read_table, write_table


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "data" / "sources" / "cfct"
RAW_JSON_DIR = SRC_DIR / "raw_json"
INDEX_PATH = SRC_DIR / "cfct_index.csv"
MAPPING_PATH = ROOT / "data" / "sources" / "cn_food_composition.csv"

MACRO_KEYS = ("calories", "protein_g", "fat_g", "carbs_g", "fiber_g")
COL_CN = {
    "calories": "热量",
    "protein_g": "蛋白质",
    "fat_g": "脂肪",
    "carbs_g": "碳水",
    "fiber_g": "纤维",
}
# JSON 字段 -> 本地列
FIELD_MAP = {
    "energyKCal": "calories",
    "protein": "protein_g",
    "fat": "fat_g",
    "CHO": "carbs_g",
    "dietaryFiber": "fiber_g",
}
SOURCE_COLUMNS = ("source", "source_ref", "source_name", "confidence", "verified_at")
INDEX_FIELDS = [
    "food_code", "food_name", "category", "edible_pct",
    "calories", "protein_g", "fat_g", "carbs_g", "fiber_g",
    "remark", "src_file",
]


def _num(value):
    """食物成分表里的数值：'Tr' 记痕量按 0 处理，'—'/空 视为缺失（None）。"""
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "—", "-", "..."):
        return None
    if text in ("Tr", "tr", "TR", "微量"):
        return 0.0
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def build():
    """把 raw_json 下的分类 JSON 合成一张每 100g 可食部的扁平索引。"""
    if not RAW_JSON_DIR.exists():
        raise SystemExit(f"未找到原始 JSON 目录: {RAW_JSON_DIR.relative_to(ROOT)}")

    rows = []
    bad = 0
    for path in sorted(RAW_JSON_DIR.glob("merged_*.json")):
        category = path.stem[len("merged_"):]
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            print(f"跳过 {path.name}: 顶层不是列表", file=sys.stderr)
            continue
        for item in data:
            code = str(item.get("foodCode", "")).strip()
            name = str(item.get("foodName", "")).strip()
            if not code or not name:
                bad += 1
                continue
            rec = {
                "food_code": code,
                "food_name": name,
                "category": category,
                "edible_pct": _num(item.get("edible")),
                "remark": str(item.get("remark", "")).strip(),
                "src_file": path.name,
            }
            for src_key, col in FIELD_MAP.items():
                rec[col] = _num(item.get(src_key))
            rows.append(rec)

    rows.sort(key=lambda r: r["food_code"])
    with INDEX_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                k: ("" if r.get(k) is None else r.get(k)) for k in INDEX_FIELDS
            })

    by_cat = {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    print(f"PASS 索引已生成: {INDEX_PATH.relative_to(ROOT)} 共 {len(rows)} 条"
          f"（跳过无编码/名称 {bad} 条）")
    for cat in sorted(by_cat):
        print(f"     {cat:<34} {by_cat[cat]}")


def load_index():
    if not INDEX_PATH.exists():
        raise SystemExit("索引不存在，请先运行: cn_food_composition.py build")
    with INDEX_PATH.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_mapping():
    if not MAPPING_PATH.exists():
        raise SystemExit(f"映射表不存在: {MAPPING_PATH.relative_to(ROOT)}")
    with MAPPING_PATH.open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if (r.get("nutrition_name") or "").strip()]


def search(query, limit=30):
    rows = load_index()
    hits = [r for r in rows if query.strip() in r["food_name"]]
    for r in hits[:limit]:
        print(
            f'  {r["food_code"]:<9} {r["category"]:<30} '
            f'{float(r["calories"] or 0):>7.0f} kcal  '
            f'P {float(r["protein_g"] or 0):>5}  F {float(r["fat_g"] or 0):>5}  '
            f'C {float(r["carbs_g"] or 0):>5}  Fi {float(r["fiber_g"] or 0):>5}  '
            f'{r["food_name"]}'
        )
    if not hits:
        print("（无匹配）")
    return hits


def diff_report():
    _, nut_rows = read_table("nutrition")
    by_name = {r["name"].strip(): r for r in nut_rows}
    index = {r["food_code"]: r for r in load_index()}
    mapping = load_mapping()

    overwrite_n = keep_n = 0
    unmatched = []
    big = []
    for m in mapping:
        name = m["nutrition_name"].strip()
        local = by_name.get(name)
        if local is None:
            unmatched.append(f"{name}(营养库无此食材)")
            continue
        mode = (m.get("apply_mode") or "cfct").strip()
        if mode == "keep":
            keep_n += 1
            continue
        code = (m.get("cfct_code") or "").strip()
        src = index.get(code)
        if src is None:
            unmatched.append(f"{name}(食物成分表编码 {code} 不在索引)")
            continue
        overwrite_n += 1
        deltas = {}
        for key in MACRO_KEYS:
            old = float(local.get(key) or 0)
            new = float(src.get(key) or 0)
            base = old if abs(old) > 1e-9 else (new if abs(new) > 1e-9 else 1.0)
            deltas[key] = abs(new - old) / abs(base) * 100.0
        worst = max(deltas, key=deltas.get)
        worst_pct = deltas[worst]
        old_k = float(local.get("calories") or 0)
        new_k = float(src.get("calories") or 0)
        dk = (new_k - old_k) / old_k * 100 if abs(old_k) > 1e-9 else float("nan")
        flag = "!!" if worst_pct > 10 else "  "
        print(
            f'{flag}{name:<10}{old_k:>7.0f}{new_k:>7.0f}{dk:>6.0f}%  '
            f'{COL_CN[worst]:<10}{m.get("note", "")}'
        )
        if worst_pct > 10 or abs(dk) > 10:
            big.append((name, worst, worst_pct))

    print()
    if unmatched:
        print("未匹配（需人工处理）:")
        for name in unmatched:
            print(f"   - {name}")
        print()
    print(f"替换条目 {overwrite_n} / 保留口径 {keep_n} / 映射总数 {len(mapping)}")
    print(f"偏差 >10% 的替换条目: {len(big)} / {overwrite_n}")
    for name, worst, pct in big:
        print(f"   ! {name:<10} {COL_CN[worst]} 偏差 {pct:.1f}%")
    return overwrite_n


def apply():
    fieldnames, nut_rows = read_table("nutrition")
    by_name = {r["name"].strip(): i for i, r in enumerate(nut_rows)}
    index = {r["food_code"]: r for r in load_index()}
    mapping = load_mapping()
    today = date.today().isoformat()

    updated = kept = skipped = 0
    for m in mapping:
        name = m["nutrition_name"].strip()
        idx = by_name.get(name)
        if idx is None:
            print(f"跳过 {name}: 营养库无此食材", file=sys.stderr)
            skipped += 1
            continue
        row = dict(nut_rows[idx])
        mode = (m.get("apply_mode") or "cfct").strip()
        if mode == "keep":
            row["source"] = m.get("source_key", "local").strip() or "local"
            row["source_ref"] = ""
            row["source_name"] = m.get("note", "").strip() or "本地估算"
            row["confidence"] = m.get("confidence", "L2").strip() or "L2"
            row["verified_at"] = today
            nut_rows[idx] = row
            kept += 1
            continue
        code = (m.get("cfct_code") or "").strip()
        src = index.get(code)
        if src is None:
            print(f"跳过 {name}: 编码 {code} 不在索引", file=sys.stderr)
            skipped += 1
            continue
        for key in MACRO_KEYS:
            row[key] = src[key] if src[key] not in (None, "") else 0
        row["source"] = m.get("source_key", "cn_food_composition").strip() or "cn_food_composition"
        row["source_ref"] = f'CFCT6:{src["food_code"]}'
        row["source_name"] = src["food_name"]
        row["confidence"] = m.get("confidence", "L3").strip() or "L3"
        row["verified_at"] = today
        nut_rows[idx] = row
        updated += 1

    write_table("nutrition", fieldnames, nut_rows)
    print(f"PASS 权威值替换 {updated} 条，口径例外保留 {kept} 条，跳过 {skipped} 条")
    print("     下一步：uv run --python 3.12 python scripts/regen_recipe_nutrition.py")


def main():
    parser = argparse.ArgumentParser(description="中国食物成分表（第6版）权威营养来源管线")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="构建本地食物成分表索引")
    p_search = sub.add_parser("search", help="按关键词查询候选条目")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=30)
    sub.add_parser("report", help="生成旧值 vs 权威值差异报告")
    sub.add_parser("apply", help="按映射表落库（走 data_store 原子写入）")
    args = parser.parse_args()

    if args.cmd == "build":
        build()
    elif args.cmd == "search":
        search(args.query, args.limit)
    elif args.cmd == "report":
        diff_report()
    elif args.cmd == "apply":
        apply()


if __name__ == "__main__":
    main()
