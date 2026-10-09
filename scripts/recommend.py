import csv
import json
from pathlib import Path

from nutrition_calc import NutritionIndex, compute_ingredients, row_provenance


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# 与 docs/PRD.md 第 4.2 节、evals/rubric.md 保持一致
WEIGHTS = {
    "ingredient_match": 0.40,
    "nutrition_match": 0.30,
    "time_match": 0.10,
    "region_match": 0.15,
    "diversity": 0.05,
}

# 地域词表：接口 / Prompt 可传英文枚举、中文标签或城市名，统一归一化到数据表使用的中文标签
REGION_ALIASES = {
    "generic": "通用", "通用": "通用", "": "通用",
    "sichuan": "川渝", "川渝": "川渝", "川": "川渝", "四川": "川渝", "成都": "川渝", "重庆": "川渝",
    "cantonese": "粤式", "粤式": "粤式", "粤": "粤式", "广式": "粤式", "广东": "粤式", "广州": "粤式",
    "jiangsu": "江浙", "江浙": "江浙", "江": "江浙", "江苏": "江浙", "浙江": "江浙", "上海": "江浙", "杭州": "江浙",
    "northern": "北方", "北方": "北方", "北京": "北方", "东北": "北方",
}


def normalize_region(value):
    if value is None:
        return "通用"
    return REGION_ALIASES.get(str(value).strip().lower(), "通用")


def load_csv(filename):
    with (DATA_DIR / filename).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def split_items(value):
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


_NUTRITION_INDEX = None


def nutrition_index():
    """懒加载营养索引（别名表 + 单位换算表 + 每 100g 营养）。

    只加载一次；数据层改动后重启服务即可生效。
    """
    global _NUTRITION_INDEX
    if _NUTRITION_INDEX is None:
        _NUTRITION_INDEX = NutritionIndex(
            load_csv("nutrition.csv"),
            load_csv("ingredient_aliases.csv"),
            load_csv("unit_conversions.csv"),
        )
    return _NUTRITION_INDEX


def ingredient_names(value):
    names = []
    for item in split_items(value):
        names.append(item.split(":")[0].strip())
    return names


def matched_ingredient_names(recipe_ingredients, user_ingredients):
    """返回食谱中真正用到的用户食材（保持食谱顺序）。

    两侧都过一遍别名表：食谱里写「牛肉」、用户说「瘦牛肉」也算命中，
    避免因为叫法不同而漏掉本该推荐的菜。别名表缺失时退回原样比较。
    """
    index = nutrition_index()
    recipe_items = ingredient_names(recipe_ingredients)
    user_items = {
        index.standard_name(item)
        for item in (user_ingredients or [])
        if str(item).strip()
    }
    if not recipe_items or not user_items:
        return []
    return [item for item in recipe_items if index.standard_name(item) in user_items]


def ingredient_match_score(recipe_ingredients, user_ingredients):
    recipe_items = ingredient_names(recipe_ingredients)
    if not recipe_items:
        return 0.0
    return len(matched_ingredient_names(recipe_ingredients, user_ingredients)) / len(recipe_items)


def nutrition_match(nutrition, rule):
    """营养软门槛：只看热量、蛋白、脂肪，与 evals/rubric.md 一致。

    入参是 scripts/nutrition_calc.py 算出来的每份营养，**不是** data/recipes.csv
    里的缓存列。carbs_min / carbs_max 保留在 goal_rules.csv 中供展示与后续
    软性匹配，当前不计入门槛，避免低碳水菜（如清蒸鱼）被误判。
    """
    return (
        float(nutrition["calories"]) >= float(rule["calorie_min"])
        and float(nutrition["calories"]) <= float(rule["calorie_max"])
        and float(nutrition["protein_g"]) >= float(rule["protein_min"])
        and float(nutrition["fat_g"]) <= float(rule["fat_max"])
    )


def time_match_score(cooking_time, time_limit):
    """时间满足上限时给出 [0.5, 1.0] 的分；越快越高。"""
    if not time_limit:
        return 1.0
    limit = float(time_limit)
    if limit <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - 0.5 * (float(cooking_time) / limit)))


def region_match_score(recipe_region, user_region):
    """通用菜适配所有人；明确地域时本地菜优先。"""
    rr = normalize_region(recipe_region)
    ur = normalize_region(user_region)
    if rr == ur:
        return 1.0
    if rr == "通用":
        return 1.0
    if ur == "通用":
        return 0.6
    return 0.0


def has_allergen(recipe, allergies):
    """过敏原命中判断：原词与别名标准名都算，宁可多拦不放过。"""
    if not allergies:
        return False
    index = nutrition_index()
    recipe_text = ";".join([
        recipe.get("ingredients", ""),
        recipe.get("tags", ""),
        recipe.get("allergens", ""),
        recipe.get("substitutes", ""),
    ]).lower()
    for item in allergies:
        term = str(item).strip().lower()
        if not term:
            continue
        for candidate in (term, index.standard_name(term).lower()):
            if candidate and candidate in recipe_text:
                return True
    return False


def primary_ingredient(candidate):
    ingredients = candidate.get("ingredients") or []
    return ingredients[0] if ingredients else ""


def select_top(candidates, top_n):
    """在等分附近做轻度多样性去重：同一主食材的菜品会被轻微降权。"""
    selected = []
    pool = list(candidates)
    while pool and len(selected) < top_n:
        used = {primary_ingredient(item) for item in selected}
        best = max(
            pool,
            key=lambda item: item["score"]
            - WEIGHTS["diversity"] * (1.0 if primary_ingredient(item) in used else 0.0),
        )
        selected.append(best)
        pool.remove(best)
    return selected


def recommend(user_input, recipes=None, rules=None, top_n=3):
    recipes = recipes or load_csv("recipes.csv")
    rules = rules or load_csv("goal_rules.csv")
    index = nutrition_index()
    goal = user_input.get("goal")
    ingredients = user_input.get("ingredients") or []
    time_limit = user_input.get("time_limit")
    region = user_input.get("region") or "通用"
    allergies = user_input.get("allergies") or []

    # goal 缺失时不再当硬门槛：取所有目标规则，避免用户没说目标就得到空推荐。
    # v0.6 起不再区分餐段（早餐/午餐/晚餐/练后），规则按 goal 聚合。
    eligible_rules = [
        row for row in rules
        if not goal or row["goal"] == goal
    ]

    candidates = []
    for recipe in recipes:
        if goal and recipe["goal"] != goal:
            continue
        if has_allergen(recipe, allergies):
            continue
        if time_limit is not None and int(recipe["cooking_time"]) > int(time_limit):
            continue

        # 营养一律现算：唯一口径来自 nutrition.csv，不接受食谱表里的缓存值
        calc = compute_ingredients(recipe["ingredients"], index, recipe["servings"])
        nutrition = calc["nutrition"]
        rule_match = any(nutrition_match(nutrition, rule) for rule in eligible_rules)

        recipe_ingredients = ingredient_names(recipe["ingredients"])
        matched_user_ingredients = matched_ingredient_names(
            recipe["ingredients"], ingredients
        )
        # 用户明确提供食材时，至少要用上一种；避免推荐与用户食材完全无关的菜。
        if ingredients and not matched_user_ingredients:
            continue

        ingredient_score = (
            len(matched_user_ingredients) / len(recipe_ingredients)
            if recipe_ingredients
            else 0.0
        )
        time_score = time_match_score(recipe["cooking_time"], time_limit)
        region_score = region_match_score(recipe["region"], region)

        score = (
            ingredient_score * WEIGHTS["ingredient_match"]
            + (1 if rule_match else 0) * WEIGHTS["nutrition_match"]
            + time_score * WEIGHTS["time_match"]
            + region_score * WEIGHTS["region_match"]
        )

        candidates.append({
            "id": recipe["id"],
            "name": recipe["name"],
            "goal": recipe["goal"],
            "score": round(score, 4),
            "region": recipe["region"],
            "servings": int(recipe["servings"]),
            "serving_weight_g": int(round(calc["serving_weight_g"])),
            "nutrition_basis": recipe["nutrition_basis"],
            "cooking_time": int(recipe["cooking_time"]),
            "nutrition": nutrition,
            "ingredient_breakdown": calc["ingredient_breakdown"],
            "ingredients": recipe_ingredients,
            "matched_ingredients": matched_user_ingredients,
            "steps": split_items(recipe["steps"]),
            "notes": recipe["notes"],
        })

    return select_top(candidates, top_n)


def recommend_eat_out(user_input, eat_out_foods=None, top_n=3):
    eat_out_foods = eat_out_foods or load_csv("eat_out_foods.csv")
    goal = user_input.get("goal")
    region = normalize_region(user_input.get("region", "通用"))

    candidates = []
    for row in eat_out_foods:
        goals = split_items(row["suitable_goals"])
        if goal and goal not in goals:
            continue

        row_region = normalize_region(row["region"])
        if row_region == region:
            region_score = 1.0
        elif row_region == "通用":
            region_score = 0.8
        elif region == "通用":
            region_score = 0.6
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


def lookup_sources(names, nutrition_data=None):
    """按食材名返回来源清单（用于回答「这个数字哪来的」）。

    返回 [{"name", "found", "source", "source_ref", "source_name",
           "confidence", "verified_at"}]，顺序与入参一致，同名去重。
    查不到的食材 found=False，不编造来源。
    """
    if nutrition_data:
        index = NutritionIndex(
            nutrition_data,
            load_csv("ingredient_aliases.csv"),
            load_csv("unit_conversions.csv"),
        )
    else:
        index = nutrition_index()

    seen = set()
    out = []
    for raw in names or []:
        key = str(raw or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        row, standard = index.find(key)
        if row is None:
            out.append({"name": key, "found": False})
            continue
        out.append({"name": standard, "found": True, **row_provenance(row)})
    return out


def analyze_nutrition(user_input, nutrition_data=None):
    ingredient_name = user_input.get("nutrition_ingredient")
    amount_g = user_input.get("amount_g") or 100
    if not ingredient_name:
        return None

    if nutrition_data:
        index = NutritionIndex(
            nutrition_data,
            load_csv("ingredient_aliases.csv"),
            load_csv("unit_conversions.csv"),
        )
    else:
        index = nutrition_index()

    row, standard_name = index.find(ingredient_name)
    if row is None:
        return None

    factor = float(amount_g) / 100.0
    return {
        "id": row["id"],
        "name": standard_name,
        "unit": row["unit"],
        "amount": amount_g,
        "calories": round(float(row["calories"]) * factor, 1),
        "protein_g": round(float(row["protein_g"]) * factor, 1),
        "fat_g": round(float(row["fat_g"]) * factor, 1),
        "carbs_g": round(float(row["carbs_g"]) * factor, 1),
        "fiber_g": round(float(row["fiber_g"]) * factor, 1),
        "allergens": row["allergens"],
        **row_provenance(row),
    }


if __name__ == "__main__":
    sample = {
        "intent": "cook",
        "ingredients": ["鸡胸肉", "西兰花", "鸡蛋"],
        "goal": "fat_loss",
        "time_limit": 20,
        "region": "generic",
        "allergies": [],
    }
    print(json.dumps(recommend(sample), ensure_ascii=False, indent=2))
