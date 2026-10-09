import csv
from pathlib import Path

from nutrition_calc import NutritionIndex, compute_ingredients


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

GOALS = {"fat_loss", "muscle_gain", "maintain"}
REGIONS = {"通用", "川渝", "粤式", "江浙", "北方"}

REQUIRED_COLUMNS = {
    "recipes.csv": [
        "id", "name", "region", "goal", "servings", "serving_weight_g",
        "nutrition_basis", "cooking_time",
        "difficulty", "ingredients", "steps", "calories", "protein_g",
        "fat_g", "carbs_g", "fiber_g", "tags", "allergens",
        "missing_tolerance", "substitutes", "source", "notes",
    ],
    "nutrition.csv": [
        "id", "name", "category", "unit", "calories", "protein_g",
        "fat_g", "carbs_g", "fiber_g", "allergens", "substitutes", "source",
    ],
    "eat_out_foods.csv": [
        "id", "name", "region", "suitable_goals", "order_strategy",
        "risk_notes", "calorie_range", "tags",
    ],
    "goal_rules.csv": [
        "goal", "calorie_min", "calorie_max", "protein_min",
        "fat_max", "carbs_min", "carbs_max", "description",
    ],
    "substitutions.csv": [
        "id", "original", "substitute", "reason", "nutrition_change",
        "applies_to",
    ],
    "ingredient_aliases.csv": ["alias", "standard", "note"],
    "unit_conversions.csv": ["unit", "ingredient", "grams", "note"],
}


def read_csv(filename):
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing required data file: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def validate_columns(filename, rows):
    required = REQUIRED_COLUMNS[filename]
    missing = [col for col in required if col not in (rows[0].keys() if rows else [])]
    if missing:
        raise ValueError(f"{filename} missing columns: {', '.join(missing)}")


def validate_unique_id(filename, rows):
    if not rows:
        raise ValueError(f"{filename} is empty")
    ids = [row["id"] for row in rows if "id" in row]
    if not ids:
        return
    duplicated = {row_id for row_id in ids if ids.count(row_id) > 1}
    if duplicated:
        raise ValueError(f"{filename} has duplicated ids: {sorted(duplicated)}")


def validate_recipes(rows):
    for row in rows:
        if row["goal"] not in GOALS:
            raise ValueError(f"Invalid goal in recipes.csv: {row['id']} {row['goal']}")
        if row["region"] not in REGIONS:
            raise ValueError(f"Invalid region in recipes.csv: {row['id']} {row['region']}")
        for field in ["calories", "protein_g", "fat_g", "carbs_g", "fiber_g"]:
            float(row[field])
        int(row["cooking_time"])
        if int(row["servings"]) < 1:
            raise ValueError(f"Invalid servings in recipes.csv: {row['id']} {row['servings']}")
        if float(row["serving_weight_g"]) <= 0:
            raise ValueError(
                f"Invalid serving_weight_g in recipes.csv: {row['id']} {row['serving_weight_g']}"
            )
        if not row["nutrition_basis"].strip():
            raise ValueError(f"Missing nutrition_basis in recipes.csv: {row['id']}")


def validate_goal_rules(rows):
    combos = set()
    for row in rows:
        if row["goal"] not in GOALS:
            raise ValueError(f"Invalid goal in goal_rules.csv: {row['goal']}")
        combo = row["goal"]
        if combo in combos:
            raise ValueError(f"Duplicated goal rule: {combo}")
        combos.add(combo)
        for field in [
            "calorie_min", "calorie_max", "protein_min", "fat_max",
            "carbs_min", "carbs_max",
        ]:
            float(row[field])
        if float(row["calorie_min"]) > float(row["calorie_max"]):
            raise ValueError(f"Invalid calorie range in goal_rules.csv: {row}")


def validate_eat_out(rows):
    for row in rows:
        if row["region"] not in REGIONS:
            raise ValueError(f"Invalid region in eat_out_foods.csv: {row['id']} {row['region']}")
        goals = [g for g in row["suitable_goals"].split(";") if g]
        if not goals:
            raise ValueError(f"eat_out_foods.csv missing suitable_goals: {row['id']}")
        invalid = [g for g in goals if g not in GOALS]
        if invalid:
            raise ValueError(f"Invalid goal in eat_out_foods.csv: {row['id']} {invalid}")


def validate_substitutions(rows):
    for row in rows:
        if row["applies_to"] not in GOALS:
            raise ValueError(f"Invalid applies_to in substitutions.csv: {row['id']} {row['applies_to']}")

def build_nutrition_index(nutrition_rows, alias_rows, unit_rows):
    return NutritionIndex(nutrition_rows, alias_rows, unit_rows)


def validate_aliases(rows, nutrition_names):
    for row in rows:
        alias = row["alias"].strip()
        standard = row["standard"].strip()
        if not alias or not standard:
            raise ValueError("ingredient_aliases.csv 存在空 alias / standard")
        if alias == standard:
            raise ValueError(f"ingredient_aliases.csv 别名与标准名相同: {alias}")
        if standard not in nutrition_names:
            raise ValueError(
                f"ingredient_aliases.csv 指向营养库里不存在的食材: {alias} -> {standard}"
            )


def validate_units(rows, nutrition_names):
    for row in rows:
        unit = row["unit"].strip()
        grams = float(row["grams"])
        if not unit:
            raise ValueError("unit_conversions.csv 存在空 unit")
        if grams <= 0:
            raise ValueError(f"unit_conversions.csv 克重必须为正: {row}")
        ingredient = row["ingredient"].strip()
        if ingredient and ingredient not in nutrition_names:
            raise ValueError(
                f"unit_conversions.csv 指向营养库里不存在的食材: {ingredient}"
            )


def validate_recipe_nutrition(rows, index):
    """recipes.csv 的营养列是计算结果缓存，必须与当前食材库现算结果一致。"""
    problems = []
    for row in rows:
        calc = compute_ingredients(row["ingredients"], index, row["servings"])
        if calc["unresolved"]:
            problems.append(f"{row['id']} 有食材无法解析: {calc['unresolved']}")
            continue
        weight = calc["serving_weight_g"]
        if abs(float(row["serving_weight_g"]) - weight) > 1.0:
            problems.append(
                f"{row['id']} serving_weight_g 缓存={row['serving_weight_g']} 计算={weight}"
            )
        for key in ("calories", "protein_g", "fat_g", "carbs_g", "fiber_g"):
            cached = float(row[key])
            computed = calc["nutrition"][key]
            if abs(cached - computed) > 0.051:
                problems.append(f"{row['id']} {key} 缓存={cached} 计算={computed}")
    if problems:
        raise ValueError(
            "recipes.csv 营养缓存与计算不一致（跑 scripts/regen_recipe_nutrition.py 重算）:\n  "
            + "\n  ".join(problems[:20])
        )


def report_goal_fit(rows, rules, index):
    """打印目标区间覆盖率，并对明显超标的食谱给出提示（不中断校验）。"""
    rule_by_goal = {row["goal"]: row for row in rules}
    stats = {}
    outliers = []
    for row in rows:
        rule = rule_by_goal.get(row["goal"])
        if rule is None:
            continue
        nutrition = compute_ingredients(row["ingredients"], index, row["servings"])["nutrition"]
        passed = (
            float(rule["calorie_min"]) <= nutrition["calories"] <= float(rule["calorie_max"])
            and nutrition["protein_g"] >= float(rule["protein_min"])
            and nutrition["fat_g"] <= float(rule["fat_max"])
        )
        total, hits = stats.get(row["goal"], (0, 0))
        stats[row["goal"]] = (total + 1, hits + (1 if passed else 0))
        if (
            nutrition["fat_g"] > float(rule["fat_max"]) * 1.5
            or nutrition["calories"] > float(rule["calorie_max"]) * 1.25
        ):
            outliers.append(
                f"{row['id']} {row['name']}（{row['goal']}）"
                f" {nutrition['calories']:.0f} kcal / 脂肪 {nutrition['fat_g']:.1f}g"
            )
    for goal in ("fat_loss", "muscle_gain", "maintain"):
        if goal in stats:
            total, hits = stats[goal]
            print(f"INFO goal fit {goal}: {hits}/{total} 条落在目标区间内")
    if outliers:
        print("WARN 以下食谱营养明显超出所属目标区间，建议核对标签或配方:")
        for line in outliers:
            print(f"     {line}")


def main():
    for filename in REQUIRED_COLUMNS:
        rows = read_csv(filename)
        validate_columns(filename, rows)
        validate_unique_id(filename, rows)
        if filename == "recipes.csv":
            validate_recipes(rows)
        if filename == "goal_rules.csv":
            validate_goal_rules(rows)
        if filename == "eat_out_foods.csv":
            validate_eat_out(rows)
        if filename == "substitutions.csv":
            validate_substitutions(rows)
        print(f"PASS {filename}: {len(rows)} rows")

    nutrition_rows = read_csv("nutrition.csv")
    alias_rows = read_csv("ingredient_aliases.csv")
    unit_rows = read_csv("unit_conversions.csv")
    nutrition_names = {row["name"].strip() for row in nutrition_rows}
    non_100g = sorted({row["unit"] for row in nutrition_rows if row["unit"].strip() != "100g"})
    if non_100g:
        raise ValueError(f"nutrition.csv 基准单位必须是 100g，发现: {non_100g}")
    validate_aliases(alias_rows, nutrition_names)
    print(f"PASS ingredient_aliases.csv: all {len(alias_rows)} aliases resolve")
    validate_units(unit_rows, nutrition_names)
    print(f"PASS unit_conversions.csv: all {len(unit_rows)} units resolve")

    index = build_nutrition_index(nutrition_rows, alias_rows, unit_rows)
    validate_recipe_nutrition(read_csv("recipes.csv"), index)
    print("PASS nutrition consistency: recipes.csv 与 nutrition.csv 现算结果一致")

    recipes = read_csv("recipes.csv")
    rules = read_csv("goal_rules.csv")
    covered = {r["goal"] for r in recipes}
    missing = [
        rule["goal"] for rule in rules
        if rule["goal"] not in covered
    ]
    if missing:
        raise ValueError(f"goal_rules.csv 存在没有对应食谱的组合: {missing}")
    print(f"PASS goal coverage: all {len(rules)} rules have recipes")
    report_goal_fit(recipes, rules, index)


if __name__ == "__main__":
    main()
