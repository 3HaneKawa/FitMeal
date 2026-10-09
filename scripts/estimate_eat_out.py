# -*- coding: utf-8 -*-
"""外食菜品份量估算管线（L1 -> L2）。

背景：

- ``data/eat_out_foods.csv`` 的 50 条是**品类级菜品**（潮汕牛肉锅、冒菜、麻辣拌…），
  不是某家门店的 SKU，多数无法对到连锁品牌官方营养表。
- 因此按「标准份量模型」给出可复现的热量区间：主料 + 主食 + 蔬菜 + 烹调油，
  用量取《中国居民膳食指南 2022》的食物份量口径，营养值取 ``data/nutrition.csv``（L3 值）。
- 结果标 ``source=reference_estimate`` / ``confidence=L2``，并写明方法与口径。

模型文件：``data/sources/eat_out_portion_model.csv``（人工审核的「菜品 -> 组成食材 + 克数」）。
区间规则：``区间 = 标准份量估算值 ±15%``，向下 / 向上取整到 10 kcal。

子命令：

    uv run --python 3.12 python scripts/estimate_eat_out.py report   # 只看差异，不落库
    uv run --python 3.12 python scripts/estimate_eat_out.py apply    # 走 data_store 落库
"""

from __future__ import annotations

import argparse
import csv
import math
from datetime import date
from pathlib import Path

from data_store import read_table, write_table


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "data" / "sources" / "eat_out_portion_model.csv"
BAND = 0.15
SRC_REF = "CFCT6+DG2022"
SRC_NAME = (
    "标准份量估算：营养值取《中国食物成分表 第6版》口径的 nutrition.csv（每100g），"
    "份量取《中国居民膳食指南 2022》食物份量口径；区间为标准份量估算值 ±15% 分量波动"
)


def load_model():
    if not MODEL_PATH.exists():
        raise SystemExit(f"模型文件不存在: {MODEL_PATH.relative_to(ROOT)}")
    with MODEL_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("eat_out_id") or "").strip()]
    grouped = {}
    for r in rows:
        did = r["eat_out_id"].strip()
        grouped.setdefault(did, []).append(
            (r["ingredient"].strip(), float(r["grams"]))
        )
    return grouped


def build_kcal_index():
    _, nut = read_table("nutrition")
    _, aliases = read_table("aliases")
    alias_map = {a["alias"].strip(): a["standard"].strip() for a in aliases}
    kcal = {r["name"].strip(): float(r["calories"] or 0) for r in nut}
    def lookup(name):
        if name in kcal:
            return kcal[name]
        std = alias_map.get(name)
        if std and std in kcal:
            return kcal[std]
        raise SystemExit(f"营养库缺少食材: {name}（也不在 aliases 中）")
    return lookup


def estimate():
    grouped = load_model()
    lookup = build_kcal_index()
    out = {}
    for did, comps in grouped.items():
        base = sum(lookup(ing) / 100.0 * grams for ing, grams in comps)
        low = int(math.floor(base * (1 - BAND) / 10.0) * 10)
        high = int(math.ceil(base * (1 + BAND) / 10.0) * 10)
        out[did] = (base, low, high)
    return out


def report():
    _, eat = read_table("eat_out")
    est = estimate()
    print(f'{"id":<5}{"菜名":<12}{"旧区间":<14}{"标准份量估算":>10}{"新区间":>14}')
    missing = []
    for row in eat:
        did = row["id"].strip()
        if did not in est:
            missing.append(did)
            continue
        base, low, high = est[did]
        print(
            f'{did:<5}{row["name"]:<12}{row["calorie_range"]:<14}'
            f'{base:>10.0f}{f"{low}-{high} kcal":>14}'
        )
    if missing:
        print("模型缺少菜品:", ", ".join(missing))


def apply():
    fieldnames, eat = read_table("eat_out")
    est = estimate()
    today = date.today().isoformat()
    updated = skipped = 0
    for row in eat:
        did = row["id"].strip()
        if did not in est:
            print(f"跳过 {did}: 模型缺失", file=__import__("sys").stderr)
            skipped += 1
            continue
        _, low, high = est[did]
        row["calorie_range"] = f"{low}-{high} kcal"
        row["source"] = "reference_estimate"
        row["source_ref"] = SRC_REF
        row["source_name"] = SRC_NAME
        row["confidence"] = "L2"
        row["verified_at"] = today
        updated += 1
    write_table("eat_out", fieldnames, eat)
    print(f"PASS 外食区间已重算 {updated} 条，跳过 {skipped} 条")


def main():
    parser = argparse.ArgumentParser(description="外食菜品标准份量估算（L1->L2）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report", help="打印旧/新热量区间差异")
    sub.add_parser("apply", help="按模型重算并落库（走 data_store 原子写入）")
    args = parser.parse_args()
    if args.cmd == "report":
        report()
    elif args.cmd == "apply":
        apply()


if __name__ == "__main__":
    main()
