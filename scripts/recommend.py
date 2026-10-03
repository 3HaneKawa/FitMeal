import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

WEIGHTS = {
    "ingredient_match": 0.55,
    "nutrition_match": 0.30,
    "time_match": 0.05,
    "region_match": 0.05,
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


def recommend_eat_out(user_input, eat_out_foods=None, top_n=3):
    eat_out_foods = eat_out_foods or load_csv("eat_out_foods.csv")
    goal = user_input.get("goal")
    region = user_input.get("region", "generic")

    candidates = []
    for row in eat_out_foods:
        goals = split_items(row["suitable_goals"])
        if goal and goal not in goals:
            continue

        region_score = 0
        if row["region"] == "generic":
            region_score = 0.8
        elif row["region"] == region:
            region_score = 1.0
        else:
            continue

        score = region_score
        if "低脂" in row["tags"] or "高蛋白" in row["tags"]:
            score += 0.2

        candidates.append({
            "id": row["id"],
            "name": row["name"],
            "score": round(min(score, 1.0), 4),
            "region": row["region"],
            "suitable_goals": goals,
            "order_strategy": row["order_strategy"],
            "risk_notes": split_items(row["risk_notes"]),
            "calorie_range": row["calorie_range"],
            "tags": split_items(row["tags"]),
        })

    return sorted(candidates, key=lambda x: x["score"], reverse=True)[:top_n]


def suggest_substitution(user_input, substitutions=None):
    substitutions = substitutions or load_csv("substitutions.csv")
    original = user_input.get("original_ingredient")
    if not original:
        return []

    results = []
    for row in substitutions:
        if row["original"] != original:
            continue
        results.append({
            "id": row["id"],
            "original": row["original"],
            "substitute": row["substitute"],
            "reason": row["reason"],
            "nutrition_change": row["nutrition_change"],
            "applies_to": row["applies_to"],
        })
    return results


def analyze_nutrition(user_input, nutrition_data=None):
    nutrition_data = nutrition_data or load_csv("nutrition.csv")
    ingredient_name = user_input.get("nutrition_ingredient")
    amount_g = user_input.get("amount_g", 100)
    if not ingredient_name:
        return None

    for row in nutrition_data:
        if row["name"] != ingredient_name:
            continue
        factor = float(amount_g) / 100 if row["unit"] == "100g" else 1
        return {
            "id": row["id"],
            "name": row["name"],
            "unit": row["unit"],
            "amount": amount_g,
            "calories": round(float(row["calories"]) * factor, 1),
            "protein_g": round(float(row["protein_g"]) * factor, 1),
            "fat_g": round(float(row["fat_g"]) * factor, 1),
            "carbs_g": round(float(row["carbs_g"]) * factor, 1),
            "fiber_g": round(float(row["fiber_g"]) * factor, 1),
            "allergens": row["allergens"],
            "source": row["source"],
        }
    return None


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
