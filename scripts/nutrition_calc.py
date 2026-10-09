# -*- coding: utf-8 -*-
"""食材克重解析 + 每份营养计算（确定性，不调用 LLM）。

事实来源（按优先级）：
1. data/nutrition.csv          —— 每 100g 营养，**唯一营养事实来源**
2. data/ingredient_aliases.csv —— 食谱 / LLM 说法 → 营养库标准名
3. data/unit_conversions.csv   —— 「个 / 瓣 / 张 / 半根」等 → 克

设计要点：
- 本模块不做任何 I/O，数据由调用方通过 NutritionIndex 注入，
  因此同一份代码可以同时跑在本地数据服务与 Dify 代码节点（内联数据）里。
- 计算结果是唯一口径：data/recipes.csv 里的营养列只是它的缓存，
  由 scripts/validate_data.py 强制对齐，不允许手工改数。
- 调料（盐 / 酱油 / 食用油等）按实际用量计入，不再忽略。
"""

import re

# 中文数词：只支持单字，足够覆盖「半个柠檬」「两瓣蒜」这类写法
_CN_NUMBERS = {
    "半": 0.5,
    "一": 1.0,
    "二": 2.0,
    "两": 2.0,
    "俩": 2.0,
    "三": 3.0,
    "四": 4.0,
    "五": 5.0,
    "六": 6.0,
    "七": 7.0,
    "八": 8.0,
    "九": 9.0,
    "十": 10.0,
}

# 克 / 毫升：毫升按 1ml≈1g 的常规近似处理（数据字典已声明）
_GRAM_UNITS = {"", "g", "G", "克", "千克", "kg", "KG", "斤"}
_ML_UNITS = {"ml", "ML", "Ml", "毫升"}

_AMOUNT_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(.*)$")

MACRO_KEYS = ("calories", "protein_g", "fat_g", "carbs_g", "fiber_g")


def split_amount(text):
    """把 "150g" / "半个" / "2瓣" 拆成 (数量, 单位, 原始文本)。

    "半个" -> (0.5, "个", "半个")；无法识别数量时数量为 None。
    原始文本会先用于精确命中换算表（例如「半个柠檬 = 50g」）。
    """
    raw = str(text or "").strip()
    if not raw:
        return None, "", raw
    if raw[0] in _CN_NUMBERS:
        return _CN_NUMBERS[raw[0]], raw[1:].strip(), raw
    match = _AMOUNT_RE.match(raw)
    if not match:
        return None, "", raw
    return float(match.group(1)), match.group(2).strip(), raw


def _num(value, default=0.0):
    try:
        text = str(value).strip()
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def row_provenance(row):
    """抽取一条营养行的来源信息（用于向用户交代「这个数字哪来的」）。

    只透传数据表里已经存在的字段，不做任何推断：
    source / source_ref / source_name / confidence / verified_at。
    """
    if not row:
        return {}
    return {
        "source": str(row.get("source", "") or ""),
        "source_ref": str(row.get("source_ref", "") or ""),
        "source_name": str(row.get("source_name", "") or ""),
        "confidence": str(row.get("confidence", "") or ""),
        "verified_at": str(row.get("verified_at", "") or ""),
    }


class NutritionIndex:
    """别名 + 单位换算 + 每 100g 营养的查询索引。"""

    def __init__(self, nutrition_rows, alias_rows=None, unit_rows=None):
        self.nutrition = {}
        self.aliases = {}
        self.units = {}
        self.default_units = {}

        for row in nutrition_rows or []:
            name = str(row.get("name", "")).strip()
            if name:
                self.nutrition[name] = row
        for row in alias_rows or []:
            alias = str(row.get("alias", "")).strip()
            standard = str(row.get("standard", "")).strip()
            if alias and standard:
                self.aliases[alias] = standard
        for row in unit_rows or []:
            unit = str(row.get("unit", "")).strip()
            grams = _num(row.get("grams"))
            if not unit or grams <= 0:
                continue
            ingredient = str(row.get("ingredient", "")).strip()
            if ingredient:
                self.units[(unit, ingredient)] = grams
            else:
                self.default_units[unit] = grams

        self._standard_cache = {}

    def standard_name(self, name):
        """按别名表把食谱写法归一到营养库标准名（最多 4 跳，防环）。"""
        current = str(name or "").strip()
        if current in self._standard_cache:
            return self._standard_cache[current]
        seen = []
        for _ in range(4):
            nxt = self.aliases.get(current)
            if not nxt or nxt == current:
                break
            seen.append(current)
            if nxt in seen:
                break
            current = nxt
        self._standard_cache[seen[0] if seen else current] = current
        return current

    def find(self, name):
        """返回 (营养行, 标准名)；查不到时营养行为 None。"""
        standard = self.standard_name(name)
        return self.nutrition.get(standard), standard

    def to_grams(self, name, amount_text):
        """返回 (克重, 失败原因)；克重为 None 表示无法换算。"""
        standard = self.standard_name(name)
        quantity, unit, raw = split_amount(amount_text)
        if quantity is None:
            return None, "unparsed:" + str(amount_text)

        if unit in _GRAM_UNITS:
            if unit in ("千克", "kg", "KG"):
                return quantity * 1000.0, None
            if unit == "斤":
                return quantity * 500.0, None
            return quantity, None
        if unit in _ML_UNITS:
            return quantity, None

        # 1) 精确写法命中（「半个」这类整体单位，克重不再乘数量）
        for key in ((raw, standard), (raw, name)):
            if key in self.units:
                return self.units[key], None
        # 2) 常规单位 + 具体食材（表中克重 = 1 个该单位的重量）
        for key in ((unit, standard), (unit, name)):
            if key in self.units:
                return self.units[key] * quantity, None
        # 3) 通用默认值（如未登记的「个 = 50g」）
        if unit in self.default_units:
            return self.default_units[unit] * quantity, None
        return None, "nounit:" + unit


def compute_ingredients(ingredients_text, index, servings=1):
    """把 ingredients 字段算成每份营养 + 食材级拆解。

    ingredients_text 形如 "豆腐:150g;虾仁:100g;鸡蛋:1个"。
    返回 dict：
      servings / serving_weight_g / nutrition / ingredient_breakdown / unresolved
    """
    try:
        servings = int(servings)
    except (TypeError, ValueError):
        servings = 1
    if servings < 1:
        servings = 1

    totals = {key: 0.0 for key in MACRO_KEYS}
    total_weight = 0.0
    breakdown = []
    unresolved = []

    for item in str(ingredients_text or "").split(";"):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            raw_name, amount_text = item.split(":", 1)
        else:
            raw_name, amount_text = item, ""
        raw_name = raw_name.strip()
        amount_text = amount_text.strip()
        if not raw_name:
            continue

        row, standard = index.find(raw_name)
        if row is None:
            unresolved.append({"name": raw_name, "reason": "no_nutrition_row"})
            continue
        grams, reason = index.to_grams(raw_name, amount_text)
        if grams is None:
            unresolved.append(
                {"name": raw_name, "amount": amount_text, "reason": reason}
            )
            continue

        factor = grams / 100.0
        item_nutrition = {
            key: _num(row.get(key)) * factor for key in MACRO_KEYS
        }
        total_weight += grams
        for key in MACRO_KEYS:
            totals[key] += item_nutrition[key]

        breakdown.append(
            {
                "name": standard,
                "raw_name": raw_name,
                "amount_text": amount_text,
                "amount_g": round(grams / servings, 1),
                "calories": round(item_nutrition["calories"] / servings, 1),
                "protein_g": round(item_nutrition["protein_g"] / servings, 1),
                "fat_g": round(item_nutrition["fat_g"] / servings, 1),
                "carbs_g": round(item_nutrition["carbs_g"] / servings, 1),
                "fiber_g": round(item_nutrition["fiber_g"] / servings, 1),
                **row_provenance(row),
            }
        )

    nutrition = {
        key: round(totals[key] / servings, 1) for key in MACRO_KEYS
    }
    calories_total = nutrition["calories"]
    for item in breakdown:
        item["calorie_share"] = (
            round(item["calories"] / calories_total, 3) if calories_total > 0 else 0.0
        )

    return {
        "servings": servings,
        "serving_weight_g": round(total_weight / servings, 1),
        "nutrition": nutrition,
        "ingredient_breakdown": breakdown,
        "unresolved": unresolved,
    }
