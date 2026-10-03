import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

WEIGHTS = {
    "ingredient_match": 0.40,
    "nutrition_match": 0.30,
    "time_match": 0.10,
    "region_match": 0.15,
    "diversity": 0.05,
}


def load_csv(filename):
    with (DATA_DIR / filename).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def split_items(value):
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def ingredient_names(value):
    names = []
    for item in split_items(value):
        names.append(item.split(":")[0].strip())
    return names


def ingredient_match_score(recipe_ingredients, user_ingredients):
    recipe_items = ingredient_names(recipe_ingredients)
    if not recipe_items:
        return 0.0
    matched = set(recipe_items) & set(user_ingredients)
    return len(matched) / len(recipe_items)


def nutrition_match(recipe, rule):
    return (
        int(recipe["calories"]) >= int(rule["calorie_min"])
        and int(recipe["calories"]) <= int(rule["calorie_max"])
        and float(recipe["protein_g"]) >= float(rule["protein_min"])
        and float(recipe["fat_g"]) <= float(rule["fat_max"])
    )


def has_allergen(recipe, allergies):
    if not allergies:
        return False
    recipe_text = ";".join([
        recipe.get("ingredients", ""),
        recipe.get("tags", ""),
        recipe.get("allergens", ""),
        recipe.get("substitutes", ""),
    ])
    return any(item.lower() in recipe_text.lower() for item in allergies)


def recommend(user_input, recipes=None, rules=None, top_n=3):
    recipes = recipes or load_csv("recipes.csv")
    rules = rules or load_csv("goal_rules.csv")
    goal = user_input.get("goal")
    meal_type = user_input.get("meal_type", "dinner")
    ingredients = user_input.get("ingredients", [])
    time_limit = user_input.get("time_limit")
    region = user_input.get("region", "generic")
    allergies = user_input.get("allergies", [])

    eligible_rules = [
        row for row in rules
        if row["goal"] == goal and row["meal_type"] == meal_type
    ]

    candidates = []
    for recipe in recipes:
        if recipe["goal"] != goal:
            continue
        if recipe["meal_type"] != meal_type:
            continue
        if has_allergen(recipe, allergies):
            continue
        if time_limit is not None and int(recipe["cooking_time"]) > int(time_limit):
            continue

        rule_match = False
        for rule in eligible_rules:
            if nutrition_match(recipe, rule):
                rule_match = True
                break

        ingredient_score = ingredient_match_score(recipe["ingredients"], ingredients)
        time_score = 1

        region_score = 0
        if recipe["region"] == "generic" or recipe["region"] == region:
            region_score = 1

        score = (
            ingredient_score * WEIGHTS["ingredient_match"]
            + (1 if rule_match else 0) * WEIGHTS["nutrition_match"]
            + time_score * WEIGHTS["time_match"]
            + region_score * WEIGHTS["region_match"]
            + WEIGHTS["diversity"]
        )

        candidates.append({
            "id": recipe["id"],
            "name": recipe["name"],
            "score": round(score, 4),
            "region": recipe["region"],
            "cooking_time": int(recipe["cooking_time"]),
            "nutrition": {
                "calories": int(recipe["calories"]),
                "protein_g": float(recipe["protein_g"]),
                "fat_g": float(recipe["fat_g"]),
                "carbs_g": float(recipe["carbs_g"]),
            },
            "ingredients": ingredient_names(recipe["ingredients"]),
            "steps": split_items(recipe["steps"]),
            "notes": recipe["notes"],
        })

    return sorted(candidates, key=lambda x: x["score"], reverse=True)[:top_n]


if __name__ == "__main__":
    sample = {
        "intent": "cook",
        "ingredients": ["鸡胸肉", "西兰花", "鸡蛋"],
        "goal": "fat_loss",
        "meal_type": "dinner",
        "time_limit": 20,
        "region": "generic",
        "allergies": [],
    }
    print(json.dumps(recommend(sample), ensure_ascii=False, indent=2))
