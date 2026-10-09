# -*- coding: utf-8 -*-
"""命令行批量录入数据：菜谱 / 食材营养 / 外食 / 别名 / 单位换算。

批量文件用 JSON，结构是一个数组（或 {"items": [...]}），每条的 table 字段决定写哪张表：

    [
      {"table": "nutrition", "name": "秋葵", "category": "vegetable",
       "calories": 33, "protein_g": 2, "fat_g": 0.2, "carbs_g": 7.5, "fiber_g": 3.9},

      {"table": "aliases", "alias": "牛油果", "standard": "鳄梨"},

      {"table": "units", "unit": "根", "ingredient": "黄瓜", "grams": 200},

      {"table": "recipes", "name": "秋葵炒鸡胸", "goal": "fat_loss", "region": "上海",
       "cooking_time": 15, "ingredients": "鸡胸肉:150g;秋葵:200g",
       "steps": ["鸡胸切块腌制", "秋葵焯水", "少油翻炒"],
       "tags": ["高蛋白", "快手菜"]},

      {"table": "eat_out", "name": "轻食沙拉碗", "region": "上海",
       "suitable_goals": ["fat_loss", "maintain"], "order_strategy": "少酱，多加鸡胸",
       "calorie_range": "300-500 kcal", "tags": ["低脂"]}
    ]

用法：

    # 生成一份带注释的模板
    uv run --python 3.12 python scripts/add_data.py --template batch.json

    # 只试跑，不写盘（在数据副本上真实执行一遍，含批内先后依赖）
    uv run --python 3.12 python scripts/add_data.py --check batch.json

    # 正式导入，并重算食谱营养缓存
    uv run --python 3.12 python scripts/add_data.py --regen batch.json

退出码：0 = 全部成功；1 = 有失败条目；2 = 文件/参数错误。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_entry  # noqa: E402
import data_store  # noqa: E402


TEMPLATE = [
    {
        "_说明": "每条的 table 决定写哪张表：nutrition / recipes / eat_out / aliases / units",
        "table": "nutrition",
        "name": "秋葵",
        "category": "vegetable",
        "calories": 33,
        "protein_g": 2,
        "fat_g": 0.2,
        "carbs_g": 7.5,
        "fiber_g": 3.9,
        "allergens": "无",
        "source": "manual_entry",
    },
    {
        "_说明": "别名：把口语说法指到营养库里的标准名（标准名必须已存在）",
        "table": "aliases",
        "alias": "秋葵荚",
        "standard": "秋葵",
    },
    {
        "_说明": "单位换算：不填 ingredient 表示通用默认值（如「1张 = 20g」）",
        "table": "units",
        "unit": "根",
        "ingredient": "黄瓜",
        "grams": 200,
    },
    {
        "_说明": "食谱：只给食材与克重，营养由服务现算，不要手填营养数值",
        "table": "recipes",
        "name": "秋葵炒鸡胸",
        "goal": "fat_loss",
        "region": "上海",
        "servings": 1,
        "cooking_time": 15,
        "difficulty": "easy",
        "ingredients": "鸡胸肉:150g;秋葵:200g",
        "steps": ["鸡胸切块腌制", "秋葵焯水", "少油翻炒"],
        "tags": ["高蛋白", "快手菜"],
        "allergens": [],
        "notes": "秋葵黏液可保留，不用过度冲洗",
    },
    {
        "_说明": "外食：suitable_goals 用数组或分号字符串都行",
        "table": "eat_out",
        "name": "自选轻食碗",
        "region": "上海",
        "suitable_goals": ["fat_loss", "maintain"],
        "order_strategy": "少酱，多加鸡胸或虾仁",
        "calorie_range": "300-500 kcal",
        "tags": ["低脂", "高蛋白"],
    },
]


def load_items(path: str) -> list[dict]:
    if path == "-":
        raw = sys.stdin.read()
        source = "<stdin>"
    else:
        file = Path(path)
        if not file.exists():
            raise SystemExit(f"找不到文件: {file}")
        raw = file.read_text(encoding="utf-8-sig")
        source = str(file)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{source} 不是合法 JSON: {exc}") from None

    if isinstance(data, dict):
        data = data.get("items")
    if not isinstance(data, list):
        raise SystemExit(f"{source} 顶层必须是数组，或 {{\"items\": [...]}}")

    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            raise SystemExit(f"{source} 里有非对象条目: {item!r}")
        cleaned.append({k: v for k, v in item.items() if not k.startswith("_")})
    return cleaned


def run_in_sandbox(items: list[dict]) -> dict:
    """把 data/*.csv 复制到临时目录，在副本上真实跑一遍导入。

    这样 --check 能正确处理批内依赖（比如同一条批次里先加食材、再加用到该食材的菜谱），
    同时保证原始数据一个字节都不动。
    """
    original_dir = data_store.DATA_DIR
    tmp = Path(tempfile.mkdtemp(prefix="fitmeal-check-"))
    try:
        for source in original_dir.glob("*.csv"):
            shutil.copy2(source, tmp / source.name)
        data_store.DATA_DIR = tmp
        return data_entry.import_batch(items)
    finally:
        data_store.DATA_DIR = original_dir
        shutil.rmtree(tmp, ignore_errors=True)


def print_results(summary: dict) -> int:
    failures = 0
    for result in summary["results"]:
        if result["ok"]:
            payload = result["result"]
            row = payload.get("row", {})
            key = row.get("id") or row.get("name") or row.get("alias") or row.get("unit") or ""
            extra = ""
            nutrition = payload.get("nutrition")
            if nutrition:
                extra = f"  {nutrition['calories']:.0f} kcal / 蛋白 {nutrition['protein_g']:.1f}g"
            print(f"  [{result['index']}] OK   {result['table']:<10} {key}{extra}")
            for warning in payload.get("warnings", []):
                print(f"        WARN {warning}")
        else:
            failures += 1
            print(f"  [{result['index']}] FAIL {result.get('table', '?'):<10} {result['error']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="FitMeal 批量数据录入")
    parser.add_argument("file", nargs="?", help="JSON 文件路径，或 - 表示标准输入")
    parser.add_argument("--check", action="store_true", help="只试跑，不写盘")
    parser.add_argument("--regen", action="store_true", help="导入后重算食谱营养缓存")
    parser.add_argument("--template", metavar="PATH", help="生成示例模板后退出")
    args = parser.parse_args()

    if args.template:
        Path(args.template).write_text(
            json.dumps(TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"已生成模板: {args.template}")
        return 0

    if not args.file:
        parser.print_help()
        return 2

    items = load_items(args.file)
    print(f"共 {len(items)} 条待处理" + ("（试跑，不写盘）" if args.check else ""))

    if args.check:
        summary = run_in_sandbox(items)
        failures = print_results(summary)
        print(f"\n试跑完成：{summary['ok']} 成功 / {failures} 失败（原始数据未改动）")
        return 1 if failures else 0

    summary = data_entry.import_batch(items)
    failures = print_results(summary)
    print(f"\n导入完成：{summary['ok']} 成功 / {failures} 失败")

    if summary["ok"]:
        if args.regen:
            regen = data_entry.regen_recipes()
            print(
                f"已重算 {regen['recipes']} 条食谱营养缓存"
                f"（重量修正 {regen['weight_fixed']} 条）"
            )
        else:
            print("提示：如果改了营养库 / 别名 / 单位，记得加 --regen 重算食谱营养缓存")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
