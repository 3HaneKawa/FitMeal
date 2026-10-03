import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from recommend import recommend
from recommend import analyze_nutrition, recommend_eat_out, suggest_substitution


ROOT = Path(__file__).resolve().parents[1]
EVAL_CASES = ROOT / "evals" / "eval_cases.csv"
RUNS_DIR = ROOT / "evals" / "runs"


def load_cases():
    with EVAL_CASES.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def expected_hit(case, result):
    expected = [item for item in case["expected_recommendations"].split(";") if item]
    if not expected:
        return None
    return any(item["id"] in expected for item in result)


def case_result(case, output, hit=None, error=None):
    return {
        "run_id": "DRY_RUN",
        "case_id": case["case_id"],
        "intent": case["expected_intent"],
        "actual_output": json.dumps(output, ensure_ascii=False) if output is not None else "",
        "hit": hit if hit is not None else False,
        "score": 2 if hit else 0,
        "failure_reason": error or "",
    }


def unsafe_case_result(case):
    risky_keywords = {
        "500大卡": "extreme_low_calorie",
        "500 kcal": "extreme_low_calorie",
        "蛋白粉和菜叶": "extreme_single_food",
        "糖尿病": "medical_condition",
    }
    matched_risk = None
    for keyword, risk_type in risky_keywords.items():
        if keyword in case["user_input"]:
            matched_risk = risk_type
            break

    output = {
        "answer_type": "safety",
        "risk_type": matched_risk,
        "message": "该请求涉及潜在健康风险，FitMeal 不提供相应饮食方案，建议咨询医生或注册营养师。",
        "recommendations": [],
    }
    return case_result(case, output, hit=matched_risk is not None)


def infer_meal_type(case):
    user_input = case["user_input"]
    if "早餐" in user_input:
        return "breakfast"
    if "早上" in user_input:
        return "breakfast"
    if "午餐" in user_input:
        return "lunch"
    if "中午" in user_input:
        return "lunch"
    if "练后" in user_input or "训练后" in user_input:
        return "post_workout"
    return "dinner"


def infer_allergies(case):
    user_input = case["user_input"]
    allergies = []
    if "花生过敏" in user_input:
        allergies.append("花生")
    if "海鲜过敏" in user_input:
        allergies.extend(["虾仁", "三文鱼", "鲈鱼", "鱼虾"])
    if "乳糖不耐受" in user_input:
        allergies.append("牛奶")
    return allergies


def run_case(case):
    intent = case["expected_intent"]

    if intent == "unsafe":
        return unsafe_case_result(case)

    if intent == "eat_out":
        user_input = {
            "intent": "eat_out",
            "goal": case["expected_goal"] if case["expected_goal"] != "extreme" else None,
            "region": case["expected_region"],
        }
        try:
            output = recommend_eat_out(user_input)
            return case_result(case, output, hit=expected_hit(case, output))
        except Exception as exc:
            return case_result(case, None, error=str(exc))

    if intent == "substitute":
        original = None
        if "没有鸡蛋" in case["user_input"]:
            original = "鸡蛋"
        elif "没有" in case["user_input"]:
            start = case["user_input"].find("没有") + len("没有")
            end = case["user_input"].find("，", start)
            original = case["user_input"][start:end if end != -1 else None].strip()

        user_input = {
            "intent": "substitute",
            "original_ingredient": original,
            "goal": case["expected_goal"],
        }
        try:
            output = suggest_substitution(user_input)
            hit = bool(output)
            return case_result(case, output, hit=hit)
        except Exception as exc:
            return case_result(case, None, error=str(exc))

    if intent == "nutrition_analysis":
        ingredient = None
        amount = 150
        if "鸡胸肉" in case["user_input"]:
            ingredient = "鸡胸肉"

        user_input = {
            "intent": "nutrition_analysis",
            "nutrition_ingredient": ingredient,
            "amount_g": amount,
        }
        try:
            output = analyze_nutrition(user_input)
            hit = output is not None
            return case_result(case, output, hit=hit)
        except Exception as exc:
            return case_result(case, None, error=str(exc))

    user_input = {
        "intent": "cook",
        "ingredients": [
            item for item in case["expected_ingredients"].split(";") if item
        ],
        "goal": case["expected_goal"],
        "meal_type": infer_meal_type(case),
        "time_limit": int(case["expected_time"]) if case["expected_time"] else None,
        "region": case["expected_region"],
        "allergies": infer_allergies(case),
    }
    try:
        output = recommend(user_input)
        return case_result(case, output, hit=expected_hit(case, output))
    except Exception as exc:
        return case_result(case, None, error=str(exc))


def dry_run():
    cases = load_cases()
    results = []
    for case in cases:
        result = run_case(case)
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        results.append(result)

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RUNS_DIR / "dry_run.csv"
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    passed = sum(row["hit"] for row in results)
    print(f"Wrote {len(results)} dry-run results to {output_path}")
    print(f"Passed: {passed}/{len(results)}")
    print("Missed cases:", ", ".join(row["case_id"] for row in results if not row["hit"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        dry_run()
    else:
        print("Only --dry-run is supported before Dify API integration.")
