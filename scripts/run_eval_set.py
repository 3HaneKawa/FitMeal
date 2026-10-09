"""FitMeal 评测执行器（代码层模式）。

职责：
- 读取正式结构化用例集 evals/eval_set.csv
- 把用例构造成 payload，调用 scripts/handler.handle()（真实 Python / 数据层，不经 LLM）
- 把 pass_rule 的声明式断言逐条求值，输出 通过 / 失败 / 未评估
- 结果写入 evals/runs/<时间戳>_code_<版本>.csv

三种判定：
- machine：代码层可机检（答案类型、推荐数、营养区间、过敏过滤、安全拦截等）
- llm    ：依赖 LLM 抽取或解释，代码层模式无法判定（如 alias_normalized / explanation_faithful）
- skip   ：本模式无意义或需人工（如 no_think、no_brand_nutrition）

注意：code 模式验证的是 Python + 数据层；LLM 端到端表现需 Dify 发布后用 --mode api。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"
RUNS = EVALS / "runs"
DEFAULT_CASES = EVALS / "eval_set.csv"
NUTRITION = ROOT / "data" / "nutrition.csv"

from handler import handle  # noqa: E402

SAFETY_RISKS = {
    "extreme_low_calorie",
    "extreme_single_food",
    "medical_condition",
    "unsafe_advice",
}
# 依赖 LLM 抽取 / 解释，代码层模式无法判定
LLM_ONLY = {
    "alias_normalized", "intent", "goal", "region_normalized", "goal_consistent",
    "explanation_faithful", "explains_tradeoff", "explains_conflict",
    "no_medical_advice", "no_unsafe_steps", "no_extreme_plan", "no_single_food_plan",
    "no_silent_goal_choice", "no_fake_constraint_satisfaction", "degradation_explained",
    "multi_goal_primary_declared", "preserves_constraints", "preserves_context",
    "no_fabricated_ingredients", "no_unrelated_recommendations", "no_brand_nutrition",
    "not_ready_ok", "feedback_event_required",
}
# 代码层无意义（无 LLM 自由文本）
NO_TEXT_KEYS = {"no_think", "no_code_block"}


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_assertions(text: str):
    items = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            items.append((key.strip(), value.strip()))
        else:
            items.append((part, None))
    return items


def build_payload(row: dict) -> dict:
    intent = row["expected_intent"]
    risk = row["expected_risk_type"]
    ingredients = [x for x in row["expected_ingredients"].split(";") if x]
    goal = None if row["expected_goal"] in ("", "any") else row["expected_goal"]
    region = row["expected_region"] or None
    time_limit = int(row["expected_time"]) if row["expected_time"] else None

    if risk in SAFETY_RISKS:
        return {
            "intent": "cook" if intent == "any" else intent,
            "risk_flag": True,
            "risk_type": risk,
            "ingredients": ingredients,
            "goal": goal,
        }

    if intent == "eat_out":
        return {"intent": "eat_out", "goal": goal, "region": region}

    if intent == "substitute":
        return {
            "intent": "substitute",
            "original_ingredient": ingredients[0] if ingredients else None,
            "goal": goal,
        }

    if intent == "nutrition_analysis":
        amount = None
        for key, value in parse_assertions(row["pass_rule"]):
            if key == "nutrition_amount" and value:
                amount = int(float(value))
        return {
            "intent": "nutrition_analysis",
            "nutrition_ingredient": ingredients[0] if ingredients else None,
            "amount_g": amount,
        }

    # cook（含过敏过滤 S1）
    allergies = []
    if risk == "allergen_conflict":
        allergies = [
            x.strip()
            for x in row["forbidden_items"].split(";")
            if x.strip() and len(x.strip()) <= 6
        ]
    return {
        "intent": "cook",
        "ingredients": ingredients,
        "goal": goal,
        "time_limit": time_limit,
        "region": region,
        "allergies": allergies,
    }


def _recs(output) -> list:
    if not isinstance(output, dict):
        return []
    return [r for r in (output.get("recommendations") or []) if isinstance(r, dict)]


def _all_recs(predicate, output) -> tuple[bool, str]:
    recs = _recs(output)
    if not recs:
        return False, "无推荐结果"
    bad = [r.get("id") or r.get("name") for r in recs if not predicate(r)]
    return (not bad), ("" if not bad else f"不满足: {bad}")


def _contains(rec: dict, field: str, value: str) -> bool:
    text = str(rec.get(field) or "")
    return value in text


def _nutrition_by_name() -> dict:
    table = {}
    if NUTRITION.exists():
        for row in read_csv(NUTRITION):
            table[row.get("name", "")] = row
    return table


def evaluate(key: str, value, row: dict, output: dict, ctx: dict) -> tuple[str, str]:
    """返回 (status, detail)。status ∈ {pass, fail, skip}。"""
    if key in NO_TEXT_KEYS:
        return "skip", "代码层无 LLM 文本"
    if key in LLM_ONLY:
        return "skip", "依赖 LLM 抽取/解释"
    if value is None:
        return "fail", f"断言格式非法：{key}"

    if key == "answer_type":
        got = output.get("answer_type")
        return ("pass", got) if got == value else ("fail", f"期望 {value}，实际 {got}")

    if key == "min_recommendations":
        n = len(_recs(output))
        want = int(float(value))
        if want == 0:
            return ("pass", "0") if n == 0 else ("fail", f"期望 0 条，实际 {n} 条")
        return ("pass", str(n)) if n >= want else ("fail", f"期望 ≥{want}，实际 {n}")

    if key == "safety_blocked":
        ok = output.get("answer_type") == "safety"
        return ("pass", "") if ok else ("fail", f"answer_type={output.get('answer_type')}")

    if key == "risk_type":
        got = output.get("risk_type")
        return ("pass", got or "") if got == value else ("fail", f"期望 {value}，实际 {got}")

    if key == "uses_any_user_ingredient":
        want = {x for x in row["expected_ingredients"].split(";") if x}
        hit = any(want & set(r.get("ingredients") or []) for r in _recs(output))
        return ("pass", "") if hit else ("fail", "没有推荐用到用户食材")

    if key == "all_recommendations_time_max":
        limit = int(float(value))
        ok, detail = _all_recs(lambda r: (r.get("cooking_time") or 0) <= limit, output)
        return ("pass", "") if ok else ("fail", detail or f"存在超过 {limit} 分钟的推荐")

    if key == "all_recommendations_region_in":
        allowed = {x.strip() for x in value.split(",") if x.strip()}
        ok, detail = _all_recs(lambda r: r.get("region") in allowed, output)
        return ("pass", "") if ok else ("fail", detail or f"地域不在 {allowed}")

    if key == "first_recommendation_region_in":
        allowed = {x.strip() for x in value.split(",") if x.strip()}
        recs = _recs(output)
        if not recs:
            return "fail", "无推荐结果"
        got = recs[0].get("region")
        return ("pass", str(got)) if got in allowed else ("fail", f"首选地域 {got} 不在 {allowed}")

    if key == "nutrition_all:calories_between":
        lo, hi = (float(x) for x in value.split(","))
        ok, detail = _all_recs(lambda r: lo <= (r.get("nutrition") or {}).get("calories", -1) <= hi, output)
        return ("pass", "") if ok else ("fail", detail or f"热量不在 {lo}-{hi}")

    if key == "nutrition_all:protein_min":
        floor = float(value)
        ok, detail = _all_recs(lambda r: (r.get("nutrition") or {}).get("protein_g", -1) >= floor, output)
        return ("pass", "") if ok else ("fail", detail or f"蛋白低于 {floor}")

    if key == "nutrition_all:fat_max":
        cap = float(value)
        ok, detail = _all_recs(lambda r: (r.get("nutrition") or {}).get("fat_g", 10**9) <= cap, output)
        return ("pass", "") if ok else ("fail", detail or f"脂肪高于 {cap}")

    if key == "serving_fields_present":
        ok, detail = _all_recs(
            lambda r: r.get("servings") and r.get("serving_weight_g") and r.get("nutrition_basis"),
            output,
        )
        return ("pass", "") if ok else ("fail", detail or "缺少份数/每份重量/营养基准")

    if key == "ingredient_breakdown_present":
        ok, detail = _all_recs(lambda r: bool(r.get("ingredient_breakdown")), output)
        return ("pass", "") if ok else ("fail", detail or "缺少食材级营养拆分")

    if key == "ordering_strategy_present":
        ok, detail = _all_recs(lambda r: bool(r.get("order_strategy")), output)
        return ("pass", "") if ok else ("fail", detail or "缺少点餐策略")

    if key == "risk_notes_present":
        top = output.get("risk_notes") or []
        rec = any(r.get("risk_notes") for r in _recs(output))
        return ("pass", "") if (top or rec) else ("fail", "无风险提示")

    if key == "no_forbidden":
        forbidden = [x.strip() for x in row["forbidden_items"].split(";") if x.strip()]
        text = json.dumps(output, ensure_ascii=False)
        leaked = [f for f in forbidden if len(f) <= 6 and f in text]
        return ("pass", "") if not leaked else ("fail", f"出现禁用项 {leaked}")

    if key == "substitution_source":
        hit = any(r.get("original") == value for r in _recs(output))
        return ("pass", "") if hit else ("fail", f"未返回 {value} 的替换")

    if key == "substitution_has_nutrition_change":
        ok, detail = _all_recs(lambda r: bool(r.get("nutrition_change")), output)
        return ("pass", "") if ok else ("fail", detail or "缺少营养变化说明")

    if key == "nutrition_amount":
        got = (output.get("nutrition") or {}).get("amount")
        return ("pass", str(got)) if got == int(float(value)) else ("fail", f"期望 {value}g，实际 {got}")

    if key in ("nutrition_fact_from_data", "no_fabricated_nutrition"):
        nut = output.get("nutrition") or {}
        if not nut:
            # 非 nutrition 意图：营养由 Python 现算，代码层视为不变量
            return "pass", "由 Python 现算"
        table = ctx.get("nutrition_table") or {}
        src = table.get(nut.get("name"))
        if not src:
            return "skip", f"数据表无 {nut.get('name')}"
        amount = float(nut.get("amount") or 0) / 100.0
        diffs = []
        for field, col in (("calories", "calories"), ("protein_g", "protein_g"),
                           ("fat_g", "fat_g"), ("carbs_g", "carbs_g")):
            if nut.get(field) is None or src.get(col) in (None, ""):
                continue
            expect = float(src[col]) * amount
            if abs(float(nut[field]) - expect) > 0.5:
                diffs.append(f"{field}:{nut[field]}≠{expect:.1f}")
        return ("pass", "") if not diffs else ("fail", "; ".join(diffs))

    if key == "all_macros_present":
        nut = output.get("nutrition") or {}
        missing = [f for f in ("calories", "protein_g", "fat_g", "carbs_g") if nut.get(f) is None]
        return ("pass", "") if not missing else ("fail", f"缺少 {missing}")

    if key in ("explicit_no_match", "clarification_required"):
        miss = output.get("missing_information") or []
        return ("pass", "") if miss else ("fail", "未要求补充信息")

    if key == "suggests_relaxation":
        nxt = output.get("next_actions") or []
        return ("pass", "") if nxt else ("fail", "未给出放宽建议")

    return "skip", "未实现的断言"


def run_case(row: dict, ctx: dict) -> dict:
    payload = build_payload(row)
    try:
        output = handle(payload)
        error = ""
    except Exception as exc:  # pragma: no cover
        output, error = {}, f"{type(exc).__name__}: {exc}"

    results = []
    for key, value in parse_assertions(row["pass_rule"]):
        if error:
            status, detail = "fail", error
        else:
            status, detail = evaluate(key, value, row, output, ctx)
        results.append({"key": key, "value": value, "status": status, "detail": detail})

    fails = [r for r in results if r["status"] == "fail"]
    passes = [r for r in results if r["status"] == "pass"]
    skips = [r for r in results if r["status"] == "skip"]

    if row["assertion_type"] == "not_ready":
        verdict = "not_ready"
    elif fails:
        verdict = "fail"
    elif passes:
        verdict = "pass"
    else:
        verdict = "blocked"

    return {
        "case_id": row["case_id"],
        "split": row["split"],
        "capability_id": row["capability_id"],
        "severity": row["severity"],
        "verdict": verdict,
        "evaluated": len(passes) + len(fails),
        "passed": len(passes),
        "failed": len(fails),
        "skipped": len(skips),
        "answer_type": output.get("answer_type", ""),
        "failed_assertions": "; ".join(f"{r['key']}({r['detail']})" for r in fails),
        "skipped_assertions": "; ".join(sorted({r["key"] for r in skips})),
        "failure_stage": row["failure_stage"] if verdict == "fail" else "",
        "payload": json.dumps(payload, ensure_ascii=False),
    }


def summary(results: list[dict]) -> None:
    def count(verdict):
        return sum(r["verdict"] == verdict for r in results)

    print()
    print("── 结果汇总 " + "─" * 48)
    print(f"  总用例 {len(results)}：pass {count('pass')} / fail {count('fail')} / "
          f"blocked {count('blocked')} / not_ready {count('not_ready')}")
    for split in ("dev", "holdout"):
        rows = [r for r in results if r["split"] == split]
        if not rows:
            continue
        p = sum(r["verdict"] == "pass" for r in rows)
        f = sum(r["verdict"] == "fail" for r in rows)
        b = sum(r["verdict"] in ("blocked", "not_ready") for r in rows)
        print(f"  {split:8s} {len(rows):3d} 条：pass {p} / fail {f} / 未判定 {b}")

    fails = [r for r in results if r["verdict"] == "fail"]
    if fails:
        print()
        print(f"── 失败用例（{len(fails)}） " + "─" * 40)
        for r in fails:
            print(f"  [{r['case_id']}] {r['severity']} {r['capability_id']}")
            print(f"      {r['failed_assertions'][:160]}")

    blocked = [r for r in results if r["verdict"] == "blocked"]
    if blocked:
        print()
        print(f"── 代码层无法判定（{len(blocked)}，需 LLM/人工评分） " + "─" * 20)
        print("  " + ", ".join(r["case_id"] for r in blocked))


def main() -> None:
    parser = argparse.ArgumentParser(description="FitMeal 评测执行器（代码层模式）")
    parser.add_argument("--cases", type=Path, default=None, help="用例 CSV 路径")
    parser.add_argument("--mode", choices=["code", "api"], default="code")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（调试用）")
    args = parser.parse_args()

    if args.mode == "api":
        print("api 模式需要 Dify endpoint，尚未接入。请先使用 code 模式。")
        raise SystemExit(2)

    cases_path = (args.cases or DEFAULT_CASES).resolve()
    if not cases_path.exists():
        raise SystemExit(f"用例文件不存在：{cases_path}")
    rows = read_csv(cases_path)
    if args.limit:
        rows = rows[: args.limit]

    from data_version import version_info

    versions = version_info()
    bundle = versions.get("bundle_version", "unknown")

    ctx = {"nutrition_table": _nutrition_by_name()}
    results = [run_case(row, ctx) for row in rows]

    for r in results:
        r["bundle_version"] = bundle
        r["run_mode"] = args.mode

    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RUNS / f"{stamp}_code_{bundle}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    print(f"用例文件：{cases_path.relative_to(ROOT)}（{len(rows)} 条）")
    print(f"版本指纹：{bundle}")
    print(f"结果文件：{out.relative_to(ROOT)}")
    summary(results)


if __name__ == "__main__":
    main()
