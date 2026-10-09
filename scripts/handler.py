"""Dify Chatflow 代码节点入口。

用法（Dify 代码节点内）：

    from recommend import recommend, recommend_eat_out, suggest_substitution, analyze_nutrition
    # ...（或把 recommend.py 与本文件内容直接粘贴进同一个代码节点）
    def main(payload: dict) -> dict:
        return handle(payload)

设计约束：
- 本模块是**唯一**的计算与筛选来源，LLM 不得改写其输出。
- 只做参数分发 + 结构化，不做自然语言生成。
"""

import json
import re

from recommend import (
    analyze_nutrition,
    lookup_sources,
    recommend,
    recommend_eat_out,
    suggest_substitution,
)

SAFETY_MESSAGE = (
    "该请求涉及潜在健康风险，FitMeal 不提供相应饮食方案，"
    "建议咨询医生或注册营养师。"
)

# 意图归一化：LLM 可能返回大小写、空格、连字符或近义写法
INTENT_ALIASES = {
    "cook": "cook",
    "recipe": "cook",
    "cooking": "cook",
    "eat_out": "eat_out",
    "eating_out": "eat_out",
    "eatout": "eat_out",
    "substitute": "substitute",
    "substitution": "substitute",
    "replace": "substitute",
    "nutrition_analysis": "nutrition_analysis",
    "nutrition": "nutrition_analysis",
    "nutrition_query": "nutrition_analysis",
    "nutrient_query": "nutrition_analysis",
    "calorie_query": "nutrition_analysis",
    "provenance": "provenance",
    "source": "provenance",
    "sources": "provenance",
    "source_query": "provenance",
    "trace": "provenance",
    "traceability": "provenance",
    "explain": "provenance",
    "unsafe": "unsafe",
    "safety": "unsafe",
}

_TRUE_TOKENS = {"true", "1", "yes", "y", "是", "有", "命中", "unsafe"}
_FALSE_TOKENS = {"", "false", "0", "no", "n", "否", "无", "null", "none", "nan", "unknown"}

# 目标兜底：LLM 没抽到 goal 时，用用户显式说过的字眼补一个（不臆测未提到的信息）
GOAL_SIGNALS = (
    ("fat_loss", ("减脂", "低脂", "减重", "掉秤", "控卡", "控糖", "轻食", "瘦")),
    ("muscle_gain", ("增肌", "长肌肉", "涨肌肉", "高蛋白", "健身餐")),
    ("maintain", ("维持", "保持", "日常")),
)


def _normalize_bool(value):
    """把 LLM 可能返回的 'false' / '0' / 0 / None 统一成 bool。

    结构化输出并非 100% 守约：模型会把 boolean 写成字符串，
    这里统一归一化，避免字符串 'false' 被当成真值误触发安全短路。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
        return True
    return bool(value)


def _normalize_intent(value):
    """意图归一化；缺省按 cook 处理。"""
    if not value:
        return "cook"
    token = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return INTENT_ALIASES.get(token, token)


def _as_list(value):
    """把字符串 / None 统一成列表，避免单个字符串被逐字拆开。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.replace("，", ";").replace("、", ";").replace(",", ";")
        return [item.strip() for item in text.split(";") if item.strip()]
    return [str(value)]


_PARAM_KEYS = {
    "ingredients", "goal", "time_limit", "flavor_preference",
    "region", "allergies", "avoid_items", "original_ingredient",
    "nutrition_ingredient", "amount_g",
}
_INTENT_KEYS = {"intent", "confidence", "reason", "risk_flag", "risk_type"}


def _extract_json_object(value):
    """从 LLM 原始文本中提取最后一个 JSON 对象。

    GLM-5.1 等模型会先输出 <think>...</think>，再输出最终 JSON；
    Dify 的 structured_output 可能因此解析失败，这里保留文本兜底。
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    text = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", value, flags=re.I | re.S)
    text = re.sub(r"</?think\s*>", "", text, flags=re.I)
    candidates = [m.group(1) for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.I | re.S)]
    candidates.append(text)
    for candidate in reversed(candidates):
        try:
            parsed = json.loads(candidate.strip())
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            pass
        starts = [m.start() for m in re.finditer(r"\{", candidate)]
        for start in reversed(starts):
            depth = 0
            in_string = False
            escaped = False
            for idx in range(start, len(candidate)):
                ch = candidate[idx]
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(candidate[start:idx + 1])
                        except (TypeError, ValueError):
                            break
                        if isinstance(parsed, dict):
                            return parsed
                        break
    return {}


def _coerce_source(source):
    """把结构化对象、text 字段或 JSON 字符串统一成 dict。"""
    if isinstance(source, dict):
        if isinstance(source.get("text"), str):
            parsed = _extract_json_object(source["text"])
            if parsed:
                return parsed
        for key in ("structured_output", "output", "json"):
            inner = source.get(key)
            if isinstance(inner, dict) and inner:
                return inner
            if isinstance(inner, str):
                parsed = _extract_json_object(inner)
                if parsed:
                    return parsed
        return source
    if isinstance(source, str):
        return _extract_json_object(source)
    return {}


def _merge_sources(*sources):
    """合并参数抽取与意图判断结果；与节点编号、输入顺序无关。"""
    parsed = [_coerce_source(source) for source in sources]
    intent_part = next(
        (part for part in parsed if any(key in part for key in _INTENT_KEYS)),
        {},
    )
    param_part = next(
        (part for part in parsed if any(key in part for key in _PARAM_KEYS)),
        {},
    )
    merged = {}
    for part in (param_part, intent_part):
        for key, value in part.items():
            if value is not None:
                merged[key] = value
    return merged


def _infer_goal(payload):
    """goal 缺失时的兜底：只依据用户显式提到过的字眼。"""
    goal = payload.get("goal")
    if isinstance(goal, str) and goal.strip():
        return goal.strip()
    haystack = " ".join(
        _as_list(payload.get("flavor_preference"))
        + _as_list(payload.get("ingredients"))
        + _as_list(payload.get("tags"))
        + _as_list(payload.get("goal_hint"))
    )
    for name, keywords in GOAL_SIGNALS:
        if any(word in haystack for word in keywords):
            return name
    return None


def _safety(risk_type=None, message=None):
    return {
        "answer_type": "safety",
        "risk_type": risk_type,
        "recommendations": [],
        "message": message or SAFETY_MESSAGE,
        "risk_notes": ["涉及极端饮食或健康状况请求，已拦截。"],
    }


def handle(payload):
    """把抽取好的参数分发到对应推荐函数，返回 api-contract 响应结构。"""
    payload = dict(payload or {})

    intent = _normalize_intent(payload.get("intent"))
    risk_flag = _normalize_bool(payload.get("risk_flag"))

    # 先归一化字段，再进入计算：字符串 / None / 单值 都会被收敛
    payload["intent"] = intent
    payload["goal"] = _infer_goal(payload)
    payload["ingredients"] = _as_list(payload.get("ingredients"))
    payload["allergies"] = _as_list(payload.get("allergies"))
    payload["avoid_items"] = _as_list(payload.get("avoid_items"))
    payload["flavor_preference"] = _as_list(payload.get("flavor_preference"))

    # 兜底：LLM 把待替换/待查询的食材塞进 ingredients 或 avoid_items 时捞回来
    if intent == "substitute" and not payload.get("original_ingredient"):
        fallback = payload.get("avoid_items") or payload["ingredients"]
        if fallback:
            payload["original_ingredient"] = fallback[0]
    if intent == "nutrition_analysis" and not payload.get("nutrition_ingredient"):
        if payload["ingredients"]:
            payload["nutrition_ingredient"] = payload["ingredients"][0]
    if intent == "provenance":
        # 溯源问题常把食材写在 nutrition_ingredient / original_ingredient / avoid_items
        for key in ("nutrition_ingredient", "original_ingredient"):
            value = payload.get(key)
            if value and str(value).strip() not in payload["ingredients"]:
                payload["ingredients"].append(str(value).strip())

    if intent == "unsafe" or risk_flag:
        return _safety(risk_type=payload.get("risk_type"))

    if intent == "eat_out":
        return {
            "answer_type": "eat_out",
            "recommendations": recommend_eat_out(payload),
            "risk_notes": [],
        }

    if intent == "substitute":
        return {
            "answer_type": "substitution",
            "recommendations": suggest_substitution(payload),
            "risk_notes": [],
        }

    if intent == "provenance":
        return {
            "answer_type": "provenance",
            "sources": lookup_sources(payload.get("ingredients")),
            "recommendations": [],
            "risk_notes": [],
        }

    if intent == "nutrition_analysis":
        result = analyze_nutrition(payload)
        return {
            "answer_type": "nutrition",
            "nutrition": result,
            "recommendations": [],
            "risk_notes": [],
        }

    # 默认按 cook 处理
    recommendations = recommend(payload)
    response = {
        "answer_type": "recipe",
        "recommendations": recommendations,
        "missing_information": [],
        "risk_notes": [],
        "next_actions": [],
    }

    # 用户给了食材但没有一道菜至少用上其中一种：明确返回无匹配，交由解释节点追问。
    if payload["ingredients"] and not recommendations:
        response["missing_information"] = ["请确认可用的食材，或放宽目标 / 时间条件"]
        response["risk_notes"] = [
            "当前数据库中没有至少使用一种现有食材、且满足目标与时间条件的食谱。"
        ]
        response["next_actions"] = [
            "换一种现有食材，或放宽目标 / 时间条件后重试。"
        ]

    return response


if __name__ == "__main__":
    import json

    demo = {
        "intent": "cook",
        "ingredients": ["鸡胸肉", "西兰花", "鸡蛋"],
        "goal": "fat_loss",
        "time_limit": 20,
        "region": "generic",
        "allergies": [],
    }
    print(json.dumps(handle(demo), ensure_ascii=False, indent=2))
