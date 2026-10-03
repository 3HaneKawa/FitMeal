import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

REQUIRED_COLUMNS = {
    "recipes.csv": [
        "id", "name", "region", "goal", "meal_type", "cooking_time",
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
        "goal", "meal_type", "calorie_min", "calorie_max", "protein_min",
        "fat_max", "carbs_min", "carbs_max", "description",
    ],
    "substitutions.csv": [
        "id", "original", "substitute", "reason", "nutrition_change",
        "applies_to",
    ],
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
    goals = {"fat_loss", "muscle_gain", "maintain"}
    meals = {"breakfast", "lunch", "dinner", "post_workout"}
    for row in rows:
        if row["goal"] not in goals:
            raise ValueError(f"Invalid goal in recipes.csv: {row['id']} {row['goal']}")
        if row["meal_type"] not in meals:
            raise ValueError(f"Invalid meal_type in recipes.csv: {row['id']} {row['meal_type']}")
        for field in ["calories", "protein_g", "fat_g", "carbs_g", "fiber_g"]:
            float(row[field])
        int(row["cooking_time"])


def validate_goal_rules(rows):
    for row in rows:
        for field in [
            "calorie_min", "calorie_max", "protein_min", "fat_max",
            "carbs_min", "carbs_max",
        ]:
            float(row[field])
        if float(row["calorie_min"]) > float(row["calorie_max"]):
            raise ValueError(f"Invalid calorie range in goal_rules.csv: {row}")


def main():
    for filename in REQUIRED_COLUMNS:
        rows = read_csv(filename)
        validate_columns(filename, rows)
        validate_unique_id(filename, rows)
        if filename == "recipes.csv":
            validate_recipes(rows)
        if filename == "goal_rules.csv":
            validate_goal_rules(rows)
        print(f"PASS {filename}: {len(rows)} rows")


if __name__ == "__main__":
    main()
