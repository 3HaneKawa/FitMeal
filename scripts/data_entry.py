# -*- coding: utf-8 -*-
"""数据录入业务层：校验 + 归一化 + 算营养 + 落库。

对外三个入口：
- server/app.py 的 POST /data/*  （给人填表 / 给脚本调）
- scripts/add_data.py            （命令行批量导入）
- 任何 Python 代码直接 import

一条铁律：**食谱的营养不接收用户传入**。调用方只给「用了什么、多少克」，
营养由 scripts/nutrition_calc.py 按 data/nutrition.csv 现算，杜绝手填错数。
"""

from __future__ import annotations

from typing import Any

from data_store import (
    TABLES,
    DataError,
    append_row,
    find_index,
    next_id,
    read_table,
    replace_row,
)
from nutrition_calc import NutritionIndex, compute_ingredients
from recommend import normalize_region

GOALS = ("fat_loss", "muscle_gain", "maintain")
GOAL_LABELS = {
    "fat_loss": "减脂",
    "muscle_gain": "增肌",
    "maintain": "维持",
}

REGION_LABELS = ("通用", "川渝", "粤式", "江浙", "北方")

MACRO_KEYS = ("calories", "protein_g", "fat_g", "carbs_g", "fiber_g")


# ---------------------------------------------------------------- 基础工具

def _text(payload: dict, field: str, default: str = "") -> str:
    value = payload.get(field, default)
    return "" if value is None else str(value).strip()


def _require(payload: dict, field: str, label: str) -> str:
    value = _text(payload, field)
    if not value:
        raise DataError(f"缺少必填字段 {field}（{label}）")
    return value


def _num(
    payload: dict,
    field: str,
    label: str,
    default: float | None = None,
    minimum: float | None = None,
) -> str:
    raw = payload.get(field, default)
    if raw is None or str(raw).strip() == "":
        if default is None:
            raise DataError(f"缺少必填字段 {field}（{label}）")
        raw = default
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        raise DataError(f"{field}（{label}）必须是数字，收到: {raw!r}") from None
    if value != value or value in (float("inf"), float("-inf")):
        raise DataError(f"{field}（{label}）不是有效数值: {raw!r}")
    if minimum is not None and value < minimum:
        raise DataError(f"{field}（{label}）不能小于 {minimum}，收到: {value}")
    return f"{value:g}"


def _list(payload: dict, field: str) -> list[str]:
    """同时接受列表与分号字符串。"""
    value = payload.get(field)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(";") if item.strip()]


def _join(items: list[str]) -> str:
    return ";".join(items)


def nutrition_rows() -> list[dict]:
    return read_table("nutrition")[1]


def build_index() -> NutritionIndex:
    """每次重建，保证读到的是磁盘上的最新数据。"""
    return NutritionIndex(
        nutrition_rows(),
        read_table("aliases")[1],
        read_table("units")[1],
    )


def reload_recommend_cache() -> None:
    """清掉 recommend 模块里的懒加载索引，新数据立即生效（不必重启服务）。"""
    import recommend

    recommend._NUTRITION_INDEX = None


def goal_rules() -> dict[str, dict]:
    return {row["goal"]: row for row in read_table("goal_rules")[1]}


def check_goal_fit(goal: str, nutrition: dict) -> dict[str, Any]:
    """判断一份营养是否落在该目标的区间内。只做提示，不阻止落库。"""
    rule = goal_rules().get(goal)
    if rule is None:
        return {"passed": None, "reasons": [f"没有 {goal} 的目标规则，无法判断"]}

    reasons = []
    kcal = float(nutrition["calories"])
    protein = float(nutrition["protein_g"])
    fat = float(nutrition["fat_g"])

    if kcal < float(rule["calorie_min"]):
        reasons.append(f"热量 {kcal:.0f} 低于下限 {rule['calorie_min']} kcal")
    if kcal > float(rule["calorie_max"]):
        reasons.append(f"热量 {kcal:.0f} 超过上限 {rule['calorie_max']} kcal")
    if protein < float(rule["protein_min"]):
        reasons.append(f"蛋白质 {protein:.1f}g 低于下限 {rule['protein_min']}g")
    if fat > float(rule["fat_max"]):
        reasons.append(f"脂肪 {fat:.1f}g 超过上限 {rule['fat_max']}g")

    return {"passed": not reasons, "reasons": reasons}


# ---------------------------------------------------------------- 营养库

def add_nutrition(payload: dict) -> dict[str, Any]:
    """新增 / 更新一条食材营养（每 100g）。"""
    name = _require(payload, "name", "食材标准名")
    mode = _text(payload, "mode", "upsert") or "upsert"
    if mode not in ("upsert", "append"):
        raise DataError("mode 只能是 upsert（默认，同名覆盖）或 append（同名报错）")

    row = {
        "name": name,
        "category": _text(payload, "category") or "other",
        "unit": "100g",
        "calories": _num(payload, "calories", "热量 kcal/100g", minimum=0),
        "protein_g": _num(payload, "protein_g", "蛋白质 g/100g", default=0, minimum=0),
        "fat_g": _num(payload, "fat_g", "脂肪 g/100g", default=0, minimum=0),
        "carbs_g": _num(payload, "carbs_g", "碳水 g/100g", default=0, minimum=0),
        "fiber_g": _num(payload, "fiber_g", "膳食纤维 g/100g", default=0, minimum=0),
        "allergens": _text(payload, "allergens") or "无",
        "substitutes": _join(_list(payload, "substitutes")),
        "source": _text(payload, "source") or "manual_entry",
    }

    index = find_index("nutrition", lambda r: r["name"].strip() == name)
    if index >= 0 and mode == "append":
        raise DataError(f"营养库已存在「{name}」，如需覆盖请把 mode 设为 upsert")
    if index >= 0:
        row["id"] = read_table("nutrition")[1][index]["id"]
        saved = replace_row("nutrition", index, row)
        action = "updated"
    else:
        _, rows = read_table("nutrition")
        row["id"] = next_id("nutrition", rows)
        saved = append_row("nutrition", row)
        action = "created"

    reload_recommend_cache()
    return {
        "action": action,
        "table": TABLES["nutrition"][0],
        "row": saved,
        "hint": "改动营养库后，请调用 POST /data/regen 重算食谱营养缓存",
    }


# ---------------------------------------------------------------- 食谱

def _prepare_recipe(payload: dict) -> tuple[dict, dict]:
    name = _require(payload, "name", "菜名")
    ingredients = _require(payload, "ingredients", "食材清单")
    goal = _text(payload, "goal")
    if goal not in GOALS:
        raise DataError(f"goal 必须是 {'/'.join(GOALS)} 之一，收到: {goal or '(空)'}")

    try:
        servings = int(float(_text(payload, "servings", "1") or "1"))
    except ValueError:
        raise DataError("servings 必须是整数") from None
    if servings < 1:
        raise DataError("servings 不能小于 1")

    calc = compute_ingredients(ingredients, build_index(), servings)
    if calc["unresolved"]:
        detail = "; ".join(
            f"{item['name']}（{item.get('reason', '')}）" for item in calc["unresolved"]
        )
        raise DataError(
            f"以下食材无法解析，请先补营养库 / 别名表 / 单位换算: {detail}"
        )

    nutrition = calc["nutrition"]
    row = {
        "name": name,
        "region": normalize_region(_text(payload, "region")),
        "goal": goal,
        "servings": str(servings),
        "serving_weight_g": str(int(round(calc["serving_weight_g"]))),
        "nutrition_basis": _text(payload, "nutrition_basis") or "每份",
        "cooking_time": _num(payload, "cooking_time", "耗时（分钟）", default=15, minimum=0),
        "difficulty": _text(payload, "difficulty") or "easy",
        "ingredients": ingredients,
        "steps": _join(_list(payload, "steps")),
        "tags": _join(_list(payload, "tags")),
        "allergens": _join(_list(payload, "allergens")),
        "missing_tolerance": _num(
            payload, "missing_tolerance", "可缺食材数", default=1, minimum=0
        ),
        "substitutes": _join(_list(payload, "substitutes")),
        "source": _text(payload, "source") or "api_entry",
        "notes": _text(payload, "notes"),
    }
    for key in MACRO_KEYS:
        row[key] = f"{nutrition[key]:.1f}"

    return row, calc


def preview_recipe(payload: dict) -> dict[str, Any]:
    """试算：不落库，只看营养和是否落在目标区间。"""
    _, calc = _prepare_recipe(payload)
    fit = check_goal_fit(_text(payload, "goal"), calc["nutrition"])
    return {
        "action": "preview",
        "nutrition": calc["nutrition"],
        "serving_weight_g": round(calc["serving_weight_g"], 1),
        "ingredient_breakdown": calc["ingredient_breakdown"],
        "goal_fit": fit,
    }


def add_recipe(payload: dict) -> dict[str, Any]:
    row, calc = _prepare_recipe(payload)
    name = row["name"]

    existing = find_index("recipes", lambda r: r["name"].strip() == name)
    if existing >= 0 and not payload.get("allow_duplicate"):
        raise DataError(
            f"已存在同名食谱「{name}」（{read_table('recipes')[1][existing]['id']}）；"
            "确需新增同名请传 allow_duplicate=true"
        )

    _, rows = read_table("recipes")
    row["id"] = next_id("recipes", rows)
    saved = append_row("recipes", row)

    fit = check_goal_fit(row["goal"], calc["nutrition"])
    warnings = []
    if fit["passed"] is False:
        warnings.append(
            "营养未落在目标区间（已落库，但建议调配方）: " + "；".join(fit["reasons"])
        )

    reload_recommend_cache()
    return {
        "action": "created",
        "table": TABLES["recipes"][0],
        "row": saved,
        "nutrition": calc["nutrition"],
        "ingredient_breakdown": calc["ingredient_breakdown"],
        "goal_fit": fit,
        "warnings": warnings,
    }


# ---------------------------------------------------------------- 外食

def add_eat_out(payload: dict) -> dict[str, Any]:
    name = _require(payload, "name", "档口 / 菜品类型")
    goals = _list(payload, "suitable_goals")
    if not goals:
        raise DataError("缺少 suitable_goals（如 ['fat_loss','muscle_gain']）")
    invalid = [g for g in goals if g not in GOALS]
    if invalid:
        raise DataError(f"suitable_goals 含非法值 {invalid}；只允许 {list(GOALS)}")

    row = {
        "name": name,
        "region": normalize_region(_text(payload, "region")),
        "suitable_goals": _join(goals),
        "order_strategy": _text(payload, "order_strategy"),
        "risk_notes": _join(_list(payload, "risk_notes")),
        "calorie_range": _text(payload, "calorie_range"),
        "tags": _join(_list(payload, "tags")),
    }

    existing = find_index("eat_out", lambda r: r["name"].strip() == name)
    if existing >= 0 and not payload.get("allow_duplicate"):
        raise DataError(f"已存在同名外食条目「{name}」；确需新增请传 allow_duplicate=true")

    _, rows = read_table("eat_out")
    row["id"] = next_id("eat_out", rows)
    saved = append_row("eat_out", row)
    return {"action": "created", "table": TABLES["eat_out"][0], "row": saved}


# ---------------------------------------------------------------- 别名 / 单位

def add_alias(payload: dict) -> dict[str, Any]:
    alias = _require(payload, "alias", "别名")
    standard = _require(payload, "standard", "标准名")
    if alias == standard:
        raise DataError("别名不能与标准名相同，否则等于没归一化")

    names = {r["name"].strip() for r in nutrition_rows()}
    if standard not in names:
        raise DataError(
            f"标准名「{standard}」不在 nutrition.csv 里；请先调用 POST /data/nutrition 添加"
        )

    row = {
        "alias": alias,
        "standard": standard,
        "note": _text(payload, "note"),
    }
    existing = find_index("aliases", lambda r: r["alias"].strip() == alias)
    if existing >= 0:
        saved = replace_row("aliases", existing, row)
        action = "updated"
    else:
        saved = append_row("aliases", row)
        action = "created"

    reload_recommend_cache()
    return {"action": action, "table": TABLES["aliases"][0], "row": saved}


def add_unit(payload: dict) -> dict[str, Any]:
    unit = _require(payload, "unit", "单位（个 / 瓣 / 张 …）")
    grams = _num(payload, "grams", "该单位等于多少克", minimum=0.01)
    ingredient = _text(payload, "ingredient")

    if ingredient:
        names = {r["name"].strip() for r in nutrition_rows()}
        if ingredient not in names:
            raise DataError(
                f"食材「{ingredient}」不在 nutrition.csv 里；请先添加该食材的营养"
            )

    row = {
        "unit": unit,
        "ingredient": ingredient,
        "grams": grams,
        "note": _text(payload, "note"),
    }
    existing = find_index(
        "units",
        lambda r: r["unit"].strip() == unit and r["ingredient"].strip() == ingredient,
    )
    if existing >= 0:
        saved = replace_row("units", existing, row)
        action = "updated"
    else:
        saved = append_row("units", row)
        action = "created"

    reload_recommend_cache()
    return {"action": action, "table": TABLES["units"][0], "row": saved}


# ---------------------------------------------------------------- 维护

def regen_recipes() -> dict[str, Any]:
    """按当前营养库重算所有食谱的营养缓存列。改过营养库 / 别名 / 单位后调用。"""
    import regen_recipe_nutrition as regen

    summary = regen.regen()
    reload_recommend_cache()
    return {"action": "regenerated", **summary}


def describe_tables() -> dict[str, Any]:
    """给录入端用的表结构清单。"""
    out = {}
    for table, (filename, prefix) in TABLES.items():
        fieldnames, rows = read_table(table)
        out[table] = {
            "file": filename,
            "columns": fieldnames or [],
            "rows": len(rows),
            "id_prefix": prefix,
        }
    return out


def import_batch(items: list[dict]) -> dict[str, Any]:
    """按 items[*].table 逐条分发，逐条返回成功 / 失败，不因一条失败中断整批。"""
    handlers = {
        "nutrition": add_nutrition,
        "recipes": add_recipe,
        "eat_out": add_eat_out,
        "aliases": add_alias,
        "units": add_unit,
    }
    results = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            results.append({"index": i, "ok": False, "error": "条目必须是对象"})
            continue
        table = str(item.get("table", "")).strip()
        handler = handlers.get(table)
        if handler is None:
            results.append(
                {
                    "index": i,
                    "ok": False,
                    "error": f"未知 table: {table!r}；可用: {', '.join(handlers)}",
                }
            )
            continue
        payload = {k: v for k, v in item.items() if k != "table"}
        try:
            results.append({"index": i, "ok": True, "table": table, "result": handler(payload)})
        except DataError as exc:
            results.append({"index": i, "ok": False, "table": table, "error": str(exc)})

    ok = sum(1 for r in results if r["ok"])
    return {"ok": ok, "failed": len(results) - ok, "total": len(results), "results": results}
