"""食谱 / 食材覆盖度诊断。

回答一个问题：用户随口说出两样家常食材时，现在的数据到底能撑起多少候选？

用法：

    uv run --python 3.12 python scripts/coverage_report.py
    uv run --python 3.12 python scripts/coverage_report.py --thin 2
    uv run --python 3.12 python scripts/coverage_report.py --query 鸡胸肉 西兰花

目标食材缺口来自 data/target_ingredients.csv（第 5 节）。

只读，不修改任何数据文件。
"""

import argparse
import csv
import itertools
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

GOALS = ["fat_loss", "muscle_gain", "maintain"]
REGION_ORDER = ["通用", "川渝", "粤式", "江浙", "北方"]


def read_csv(filename):
    with open(DATA_DIR / filename, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_alias_map():
    rows = read_csv("ingredient_aliases.csv")
    return {r["alias"].strip(): r["standard"].strip() for r in rows}


def split_ingredients(text, alias_map):
    """把 "鸡胸肉:150g;西兰花:200g" 拆成标准名列表（保持出现顺序）。"""
    names = []
    for item in (text or "").split(";"):
        item = item.strip()
        if not item:
            continue
        raw = item.split(":")[0].strip()
        names.append(alias_map.get(raw, raw))
    return names


def section(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def report_overall(recipes, nutrition, alias_map):
    section("1. 食谱 → 营养 覆盖率")

    nutrition_names = {r["name"].strip() for r in nutrition}
    used = Counter()
    unknown = Counter()

    for r in recipes:
        for name in split_ingredients(r["ingredients"], alias_map):
            used[name] += 1
            if name not in nutrition_names:
                unknown[name] += 1

    print(f"nutrition.csv 条目数        : {len(nutrition)}")
    print(f"recipes.csv 引用的食材种数  : {len(used)}")
    print(f"其中营养库缺失的种数        : {len(unknown)}")

    if unknown:
        print()
        print("缺失明细：")
        for name, n in unknown.most_common():
            print(f"  - {name}（{n} 道菜用到）")
    else:
        print()
        print("结论：食谱引用的食材，营养库已 100% 覆盖。")

    unused = sorted(n for n in nutrition_names if n not in used)
    if unused:
        print()
        print(f"营养库有、但没有菜谱用到（{len(unused)} 种）：")
        print("  " + "、".join(unused))


def report_density(recipes, alias_map, thin_threshold):
    section("2. 食材覆盖密度（真正决定推荐有没有得选）")

    per_ingredient = Counter()
    for r in recipes:
        for name in set(split_ingredients(r["ingredients"], alias_map)):
            per_ingredient[name] += 1

    total = len(per_ingredient)
    buckets = Counter()
    for n in per_ingredient.values():
        buckets[min(n, 5)] += 1

    print(f"共 {total} 种食材，按出现在多少道菜里分档：")
    for k in sorted(buckets):
        label = f"{k} 道" if k < 5 else "5 道及以上"
        share = buckets[k] / total * 100
        print(f"  只在 {label:<8}: {buckets[k]:>3} 种（{share:4.1f}%）")

    thin = sorted(
        ((n, name) for name, n in per_ingredient.items() if n <= thin_threshold),
        key=lambda x: (x[0], x[1]),
    )
    if thin:
        print()
        print(f"候选池过窄的食材（出现 ≤{thin_threshold} 道，共 {len(thin)} 种）：")
        line = []
        for n, name in thin:
            line.append(f"{name}({n})")
        for i in range(0, len(line), 6):
            print("  " + "、".join(line[i:i + 6]))

    return per_ingredient


def report_matrix(recipes):
    section("3. 目标 × 地域 分布")

    grid = Counter((r["goal"], r["region"]) for r in recipes)
    width = 8
    header = "目标".ljust(14) + "".join(reg.ljust(width) for reg in REGION_ORDER) + "合计"
    print(header)
    print("-" * len(header))
    for goal in GOALS:
        cells = [grid.get((goal, reg), 0) for reg in REGION_ORDER]
        print(goal.ljust(14) + "".join(str(c).ljust(width) for c in cells) + str(sum(cells)))
    print("-" * len(header))
    totals = [sum(grid.get((g, reg), 0) for g in GOALS) for reg in REGION_ORDER]
    print("合计".ljust(14) + "".join(str(t).ljust(width) for t in totals) + str(sum(totals)))

    empty = [
        (g, reg) for g in GOALS for reg in REGION_ORDER if grid.get((g, reg), 0) == 0
    ]
    if empty:
        print()
        print(f"空档（{len(empty)} 个组合，用户选到这个组合时只能跨地域兜底）：")
        for g, reg in empty:
            print(f"  - {g} × {reg}")


def report_pairs(recipes, alias_map, top=15):
    section(f"4. 高频食材组合（前 {top}）")

    pairs = Counter()
    for r in recipes:
        names = sorted(set(split_ingredients(r["ingredients"], alias_map)))
        for pair in itertools.combinations(names, 2):
            pairs[pair] += 1

    if not pairs:
        print("（无）")
        return

    print(f"出现最多的组合也只有 {pairs.most_common(1)[0][1]} 道菜。")
    print()
    for (a, b), n in pairs.most_common(top):
        print(f"  {a} + {b}: {n} 道")


def report_targets(recipes, alias_map):
    """读取 data/target_ingredients.csv，输出各优先级的达标进度与剩余缺口。"""
    path = DATA_DIR / "target_ingredients.csv"
    if not path.exists():
        return

    section("5. 目标食材缺口（target_ingredients.csv）")

    rows = read_csv("target_ingredients.csv")
    per_ingredient = Counter()
    for r in recipes:
        for name in set(split_ingredients(r["ingredients"], alias_map)):
            per_ingredient[name] += 1

    order = {"P0": 0, "P1": 1, "P2": 2}
    rows.sort(key=lambda r: (order.get(r["priority"], 9), r["ingredient"]))

    overall_done = 0
    for priority in ("P0", "P1", "P2"):
        group = [r for r in rows if r["priority"] == priority]
        if not group:
            continue
        done = [
            r for r in group
            if per_ingredient.get(r["ingredient"], 0) >= int(r["target_recipes"])
        ]
        overall_done += len(done)
        print()
        print(f"[{priority}] 已达标 {len(done)}/{len(group)} 项")
        for r in group:
            name = r["ingredient"]
            target = int(r["target_recipes"])
            current = per_ingredient.get(name, 0)
            if current >= target:
                continue
            note = r.get("note") or ""
            tail = f"（{note}）" if note else ""
            print(f"  {name}：{current}/{target} 道，还差 {target - current} 道{tail}")

    print()
    print(f"合计：{overall_done}/{len(rows)} 项达标。")


def report_query(recipes, alias_map, query, goal=None):
    section(f"6. 模拟提问：{' + '.join(query)}" + (f"（目标 {goal}）" if goal else ""))

    sets = [(set(split_ingredients(r["ingredients"], alias_map)), r) for r in recipes]

    def ok(r):
        return goal is None or r["goal"] == goal

    at_least_one = [(s, r) for s, r in sets if ok(r) and any(q in s for q in query)]
    all_of = [(s, r) for s, r in sets if ok(r) and all(q in s for q in query)]

    print(f"命中 ≥1 样用户食材 : {len(at_least_one)} 道")
    print(f"两样都用到         : {len(all_of)} 道")

    if at_least_one:
        print()
        print("命中 ≥1 样的前 5 道：")
        for s, r in at_least_one[:5]:
            hit = [q for q in query if q in s] or ["（别名/搭配命中）"]
            print(f"  {r['id']} {r['name']}（{r['goal']}）命中：{','.join(hit)}")
    else:
        print()
        print("⚠ 一道都没有。这类提问目前只能走「无匹配」追问分支。")


def main():
    parser = argparse.ArgumentParser(description="食谱 / 食材覆盖度诊断")
    parser.add_argument("--thin", type=int, default=2, help="多少道以下算「候选池过窄」，默认 2")
    parser.add_argument(
        "--query", nargs="+", metavar="食材",
        help="模拟一次真实提问，例如 --query 鸡胸肉 西兰花",
    )
    parser.add_argument("--goal", choices=GOALS, help="配合 --query 限定目标")
    args = parser.parse_args()

    recipes = read_csv("recipes.csv")
    nutrition = read_csv("nutrition.csv")
    alias_map = build_alias_map()

    print(f"recipes.csv   : {len(recipes)} 道")
    print(f"nutrition.csv : {len(nutrition)} 条")

    report_overall(recipes, nutrition, alias_map)
    report_density(recipes, alias_map, args.thin)
    report_matrix(recipes)
    report_pairs(recipes, alias_map)
    report_targets(recipes, alias_map)

    if args.query:
        report_query(recipes, alias_map, args.query, args.goal)


if __name__ == "__main__":
    main()
