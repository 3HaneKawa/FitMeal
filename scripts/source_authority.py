# -*- coding: utf-8 -*-
"""权威营养来源管线（USDA FoodData Central）。

背景与定位：

- 现状：``data/nutrition.csv`` 里绝大多数行的 ``source`` 只写了 ``human_estimated`` /
  ``reference_estimate``（来源**类型**），没有可查证的**引用**，属于 L1/L2。
- 目标：把营养事实升级到 L3「权威可引用」，每条带 fdc_id / 来源描述 / 置信级 / 校验日期。

数据底座（离线，公有领域 CC0 / 美国政府作品）：

- ``data/sources/raw/fdc_foundation.zip``   Foundation Foods（最高质量，含样品/实验室元数据）
- ``data/sources/raw/fdc_sr_legacy.zip``    SR Legacy（USDA 经典营养库，覆盖最广）
- ``data/sources/raw/fdc_survey.zip``       FNDDS 调查食物（含复合/熟制菜品）

子命令：

    uv run --python 3.12 python scripts/source_authority.py index      # 建本地索引
    uv run --python 3.12 python scripts/source_authority.py search 豆腐  # 查候选条目
    uv run --python 3.12 python scripts/source_authority.py report     # 生成差异报告
    uv run --python 3.12 python scripts/source_authority.py apply      # 按映射落库

映射表：``data/sources/ingredient_sources.csv``（人工审核的「本地食材 -> FDC 条目」）。
只读/离线；不改任何既有数据口径，``apply`` 走 ``scripts/data_store.py`` 原子写入。
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

import data_store
from data_store import DataError, read_table, write_table


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SRC_DIR = DATA_DIR / "sources"
RAW_DIR = SRC_DIR / "raw"
INDEX_PATH = SRC_DIR / "fdc_index.csv"
MAPPING_PATH = SRC_DIR / "ingredient_sources.csv"

MACRO_KEYS = ("calories", "protein_g", "fat_g", "carbs_g", "fiber_g")
COL_CN = {
    "calories": "热量",
    "protein_g": "蛋白质",
    "fat_g": "脂肪",
    "carbs_g": "碳水",
    "fiber_g": "纤维",
}

# FDC nutrient_id -> 本地列（FDC 的 amount 按每 100g 计）
NUTRIENT_MAP = {
    "1003": "protein_g",
    "1004": "fat_g",
    "1005": "carbs_g",
    "1079": "fiber_g",
}
# 能量按优先级取：Chemical/Atwater 优先于通用 1008
ENERGY_IDS = ("1008", "2047", "2048")

# nutrition.csv 的来源字段（apply 时补齐）
SOURCE_COLUMNS = ("source", "source_ref", "source_name", "confidence", "verified_at")


def _num(value, default=0.0):
    try:
        text = str(value).strip()
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def discover_extracts():
    """定位所有已解压的 FDC 数据集目录（含 food.csv 的目录）。"""
    found = []
    if not RAW_DIR.exists():
        return found
    for top in sorted(RAW_DIR.glob("extract_*")):
        if (top / "food.csv").exists():
            found.append(top)
            continue
        for sub in sorted(p for p in top.iterdir() if p.is_dir()):
            if (sub / "food.csv").exists():
                found.append(sub)
    return found


def build_index():
    """把三个数据集的 food + food_nutrient 合成一张每 100g 的宽表。"""
    dirs = discover_extracts()
    if not dirs:
        raise SystemExit(
            "未找到 FDC 数据集。请先解压 data/sources/raw/fdc_*.zip 到 extract_* 目录。"
        )

    foods = {}
    for d in dirs:
        with (d / "food.csv").open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                data_type = row["data_type"].strip()
                if data_type not in KEEP_TYPES:
                    continue
                fdc_id = row["fdc_id"].strip()
                foods[fdc_id] = {
                    "fdc_id": fdc_id,
                    "data_type": data_type,
                    "description": row["description"].strip(),
                    "publication_date": row.get("publication_date", "").strip(),
                }

    nutrients = {}
    energy = {}
    have_ids = {}
    for d in dirs:
        with (d / "food_nutrient.csv").open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                fdc_id = row["fdc_id"].strip()
                if fdc_id not in foods:
                    continue
                nid = row["nutrient_id"].strip()
                have_ids.setdefault(fdc_id, set()).add(nid)
                if nid in NUTRIENT_MAP:
                    nutrients.setdefault(fdc_id, {})[NUTRIENT_MAP[nid]] = _num(row["amount"])
                elif nid in ENERGY_IDS:
                    energy.setdefault(fdc_id, {})[nid] = _num(row["amount"])

    rows = []
    skipped_incomplete = 0
    for fdc_id, meta in foods.items():
        ids = have_ids.get(fdc_id, set())
        # 只保留宏量营养完整的条目（Foundation 部分食物脂肪按脂肪酸拆分，缺少 1004/1008）
        # 纤维对肉类等天然为 0，不作为完整性要求，缺失按 0 处理
        required = {"1003", "1004", "1005"}
        if not (required <= ids and any(e in ids for e in ENERGY_IDS)):
            skipped_incomplete += 1
            continue
        vals = dict(nutrients.get(fdc_id, {}))
        kcal_map = energy.get(fdc_id, {})
        kcal = 0.0
        # 取第一个非零能量值（部分条目 1008 为空而 2047 有值）
        for nid in ENERGY_IDS:
            if _num(kcal_map.get(nid)) > 0:
                kcal = kcal_map[nid]
                break
        if kcal <= 0:
            kcal = max((_num(kcal_map.get(n)) for n in ENERGY_IDS), default=0.0)
        rows.append(
            {
                "fdc_id": fdc_id,
                "data_type": meta["data_type"],
                "description": meta["description"],
                "publication_date": meta["publication_date"],
                "calories": round(kcal, 1),
                "protein_g": round(vals.get("protein_g", 0.0), 1),
                "fat_g": round(vals.get("fat_g", 0.0), 1),
                "carbs_g": round(vals.get("carbs_g", 0.0), 1),
                "fiber_g": round(vals.get("fiber_g", 0.0), 1),
            }
        )

    fieldnames = [
        "fdc_id", "data_type", "description", "publication_date",
        "calories", "protein_g", "fat_g", "carbs_g", "fiber_g",
    ]
    with INDEX_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    by_type = {}
    for r in rows:
        by_type[r["data_type"]] = by_type.get(r["data_type"], 0) + 1
    print(f"PASS 索引已生成: {INDEX_PATH.relative_to(ROOT)} 共 {len(rows)} 条（跳过宏量不完整 {skipped_incomplete} 条）")
    for k in sorted(by_type):
        print(f"     {k:<16} {by_type[k]}")
    return rows


def load_index():
    if not INDEX_PATH.exists():
        raise SystemExit("索引不存在，请先运行: source_authority.py index")
    with INDEX_PATH.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# 只保留真实食物条目（排除 sample / market_acquisition 等实验样本行）
# survey_fndds 在本包内不含宏量营养，不作为事实来源
KEEP_TYPES = {"foundation_food", "sr_legacy_food"}
TYPE_WEIGHT = {"sr_legacy_food": 0, "foundation_food": 1}


def search(query, limit=25):
    rows = load_index()
    tokens = [t for t in query.lower().replace(",", " ").split() if t]
    hits = []
    for r in rows:
        desc = r["description"].lower()
        if all(t in desc for t in tokens):
            hits.append(r)
    hits.sort(key=lambda r: (TYPE_WEIGHT.get(r["data_type"], 9), len(r["description"])))
    for r in hits[:limit]:
        print(
            f'{r["fdc_id"]:>8}  {r["data_type"]:<15}  '
            f'{r["calories"]:>6} kcal  P{r["protein_g"]:>5}  F{r["fat_g"]:>5}  '
            f'C{r["carbs_g"]:>5}  Fi{r["fiber_g"]:>5}  {r["description"]}'
        )
    if not hits:
        print("（无匹配）")
    return hits


def load_mapping():
    if not MAPPING_PATH.exists():
        return []
    with MAPPING_PATH.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_nutrition():
    fieldnames, rows = read_table("nutrition")
    return fieldnames, rows


def diff_report():
    _, nutrition_rows = load_nutrition()
    by_name = {r["name"].strip(): r for r in nutrition_rows}
    index = {r["fdc_id"]: r for r in load_index()}
    mapping = load_mapping()

    print(f"映射条目: {len(mapping)} / 营养库: {len(nutrition_rows)}")
    print()
    header = f'{"食材":<10}{"旧kcal":>7}{"新kcal":>7}{"Δ%":>7}  {"最大偏差项":<10}备注'
    print(header)
    print("-" * 96)
    print("  （keep=口径不一致，保留本地值只标注来源；fdc=用 USDA 权威值替换）")
    print()

    unmatched, big_big, overwrite_n, keep_n = [], [], 0, 0
    for m in mapping:
        name = m["nutrition_name"].strip()
        local = by_name.get(name)
        if local is None:
            unmatched.append(name)
            continue
        mode = (m.get("apply_mode") or "fdc").strip()
        if mode == "keep":
            keep_n += 1
            print(f'[keep]{name:<10}{"":>7}{"":>7}{"":>7}  {"":<10}{m.get("note","")}')
            continue
        fdc_id = (m.get("fdc_id") or "").strip()
        src = index.get(fdc_id) if fdc_id else None
        if src is None:
            unmatched.append(f"{name}(fdc {fdc_id} 不在索引)")
            continue
        overwrite_n += 1
        deltas = {}
        for key in MACRO_KEYS:
            old = _num(local.get(key))
            new = _num(src.get(key))
            base = old if abs(old) > 1e-9 else (new if abs(new) > 1e-9 else 1.0)
            deltas[key] = abs(new - old) / abs(base) * 100.0
        worst = max(deltas, key=deltas.get)
        worst_pct = deltas[worst]
        old_k = _num(local.get("calories"))
        new_k = _num(src.get("calories"))
        dk = (new_k - old_k) / old_k * 100 if abs(old_k) > 1e-9 else float("nan")
        flag = "!!" if worst_pct > 10 else "  "
        print(
            f'{flag}{name:<10}{old_k:>7.0f}{new_k:>7.0f}{dk:>6.0f}%  '
            f'{COL_CN[worst]:<10}{m.get("note","")}'
        )
        if worst_pct > 10 or abs(dk) > 10:
            big_big.append((name, worst, worst_pct))

    print()
    if unmatched:
        print("未在营养库或索引中找到（需人工处理）:")
        for name in unmatched:
            print(f"   - {name}")
        print()
    print(f"替换条目 {overwrite_n} / 保留口径 {keep_n} / 映射总数 {len(mapping)}")
    print(f"偏差 >10% 的替换条目: {len(big_big)} / {overwrite_n}")
    for name, worst, pct in big_big:
        print(f"   ! {name:<10} {COL_CN[worst]} 偏差 {pct:.1f}%")
    return overwrite_n


def ensure_schema():
    """把 source 字段从「单一标签」扩成完整引用（缺列则补，列序不变，追加到末尾）。"""
    fieldnames, rows = read_table("nutrition")
    missing = [c for c in SOURCE_COLUMNS if c not in fieldnames]
    if not missing:
        return fieldnames, rows
    new_fields = fieldnames + [c for c in SOURCE_COLUMNS if c not in fieldnames]
    for row in rows:
        row.setdefault("source", "")
    write_table("nutrition", new_fields, rows)
    return new_fields, rows


def apply():
    fieldnames, rows = ensure_schema()
    by_name = {r["name"].strip(): i for i, r in enumerate(rows)}
    index = {r["fdc_id"]: r for r in load_index()}
    mapping = load_mapping()
    today = date.today().isoformat()

    updated = 0
    kept = 0
    skipped = 0
    for m in mapping:
        name = m["nutrition_name"].strip()
        idx = by_name.get(name)
        if idx is None:
            print(f"跳过 {name}: 营养库无此食材", file=sys.stderr)
            skipped += 1
            continue
        row = dict(rows[idx])
        mode = (m.get("apply_mode") or "fdc").strip()
        if mode == "keep":
            # 口径不一致：只标注来源与置信级，保留本地数值
            row["source"] = m.get("source_key", "local").strip() or "local"
            row["source_ref"] = ""
            row["source_name"] = m.get("note", "").strip() or "本地估算"
            row["confidence"] = m.get("confidence", "L2").strip() or "L2"
            row["verified_at"] = today
            rows[idx] = row
            kept += 1
            continue
        fdc_id = (m.get("fdc_id") or "").strip()
        src = index.get(fdc_id) if fdc_id else None
        if src is None:
            print(f"跳过 {name}: fdc_id {fdc_id} 不在索引", file=sys.stderr)
            skipped += 1
            continue
        for key in MACRO_KEYS:
            row[key] = src[key]
        row["source"] = m.get("source_key", "usda_fdc").strip() or "usda_fdc"
        row["source_ref"] = f'FDC:{src["fdc_id"]}'
        row["source_name"] = src["description"]
        row["confidence"] = m.get("confidence", "L3").strip() or "L3"
        row["verified_at"] = today
        rows[idx] = row
        updated += 1

    write_table("nutrition", fieldnames, rows)
    print(f"PASS 权威值替换 {updated} 条，口径例外保留 {kept} 条，跳过 {skipped} 条")
    print("     下一步：uv run --python 3.12 python scripts/regen_recipe_nutrition.py")


def main():
    parser = argparse.ArgumentParser(description="USDA FDC 权威营养来源管线")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index", help="构建本地 FDC 索引")
    p_search = sub.add_parser("search", help="按关键词查询候选条目")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("--limit", type=int, default=25)
    sub.add_parser("report", help="生成旧值 vs 权威值差异报告")
    sub.add_parser("apply", help="按映射表落库（走 data_store 原子写入）")
    args = parser.parse_args()

    if args.cmd == "index":
        build_index()
    elif args.cmd == "search":
        search(" ".join(args.query), args.limit)
    elif args.cmd == "report":
        diff_report()
    elif args.cmd == "apply":
        apply()


if __name__ == "__main__":
    main()
