from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "eval_set.csv"
MATRIX = ROOT / "evals" / "capability_matrix.csv"

REQUIRED_COLUMNS = [
    "case_id", "split", "capability_id", "prd_ref", "user_input", "expected_intent",
    "expected_goal", "expected_ingredients", "expected_region", "expected_time",
    "expected_behavior", "expected_risk_type", "pass_rule", "forbidden_items",
    "assertion_type", "data_sensitivity", "failure_stage", "severity", "grader",
    "data_version", "notes", "origin", "batch",
]
ALLOWED_SPLIT = {"dev", "holdout"}
ALLOWED_INTENT = {"cook", "eat_out", "substitute", "nutrition_analysis", "unsafe", "any"}
ALLOWED_GOAL = {"fat_loss", "muscle_gain", "maintain", "any"}
ALLOWED_BEHAVIOR = {
    "recommend_recipe", "recommend_eat_out", "suggest_substitution", "explain_nutrition",
    "safety_block", "clarify", "no_match", "collect_feedback",
}
ALLOWED_RISK = {
    "none", "allergen_conflict", "extreme_low_calorie", "extreme_single_food",
    "medical_condition", "unsafe_advice",
}
ALLOWED_ASSERTION = {"capability", "safety", "data_sensitive", "ranking", "format", "not_ready"}
ALLOWED_SENSITIVITY = {"invariant", "low", "medium", "high"}
ALLOWED_FAILURE_STAGE = {
    "intent", "extraction", "safety", "filter", "scoring", "explanation", "format", "data", "feedback",
}
ALLOWED_SEVERITY = {"high", "medium", "low"}
ALLOWED_GRADER = {"auto", "rubric", "human"}

MIN_DEV = 40
MIN_HOLDOUT = 10
REGION_KEYS = {"all_recommendations_region_in", "first_recommendation_region_in"}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL {message}")


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def assertion_pairs(text: str) -> list[tuple[str, str]]:
    pairs = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            pairs.append((key.strip(), value.strip()))
        else:
            pairs.append((part, ""))
    return pairs


def main() -> None:
    strict = "--strict" in sys.argv
    columns, rows = read_rows(CASES)
    if columns != REQUIRED_COLUMNS:
        fail(f"eval_set.csv columns differ from formal schema: {columns}")
    if not rows:
        fail("eval_set.csv has no data rows")

    matrix_columns, matrix_rows = read_rows(MATRIX)
    if "matrix_id" not in matrix_columns:
        fail("capability_matrix.csv has no matrix_id")
    matrix_ids = {row["matrix_id"] for row in matrix_rows}

    ids = [row["case_id"] for row in rows]
    if len(ids) != len(set(ids)):
        fail("case_id values must be unique")
    for cid in ids:
        if not cid.startswith("P") or not cid[1:].isdigit():
            fail(f"case_id {cid!r} must look like P001")

    seen_input: dict[str, str] = {}
    for row in rows:
        cid = row["case_id"]
        if row["split"] not in ALLOWED_SPLIT:
            fail(f"{cid}: invalid split={row['split']!r}")
        caps = [x for x in row["capability_id"].split(";") if x]
        if not caps:
            fail(f"{cid}: capability_id is empty")
        for cap in caps:
            if cap not in matrix_ids:
                fail(f"{cid}: capability_id {cap!r} not in capability_matrix.csv")

        enums = [
            ("expected_intent", ALLOWED_INTENT),
            ("expected_goal", ALLOWED_GOAL),
            ("expected_behavior", ALLOWED_BEHAVIOR),
            ("expected_risk_type", ALLOWED_RISK),
            ("assertion_type", ALLOWED_ASSERTION),
            ("data_sensitivity", ALLOWED_SENSITIVITY),
            ("failure_stage", ALLOWED_FAILURE_STAGE),
            ("severity", ALLOWED_SEVERITY),
            ("grader", ALLOWED_GRADER),
        ]
        for field, allowed in enums:
            if row[field] not in allowed:
                fail(f"{cid}: invalid {field}={row[field]!r}")

        if row["expected_intent"] == "any" and row["expected_behavior"] != "safety_block":
            fail(f"{cid}: expected_intent=any is only valid for safety_block")
        if (row["expected_risk_type"] != "none") != (row["assertion_type"] == "safety"):
            fail(f"{cid}: risk type must be set exactly when assertion_type=safety")
        if row["expected_behavior"] == "safety_block" and row["expected_risk_type"] == "none":
            fail(f"{cid}: safety_block must declare a risk type")

        for field in ("prd_ref", "user_input", "pass_rule", "notes", "origin", "batch"):
            if not row[field].strip():
                fail(f"{cid}: {field} must not be empty")
        if not row["data_version"].startswith("dv-"):
            fail(f"{cid}: data_version must start with dv-")

        ingredients = [x for x in row["expected_ingredients"].split(";") if x.strip()]
        for key, value in assertion_pairs(row["pass_rule"]):
            if key == "uses_any_user_ingredient" and value == "true" and not ingredients:
                fail(f"{cid}: uses_any_user_ingredient=true but expected_ingredients is empty")
            if key in REGION_KEYS and not row["expected_region"].strip():
                fail(f"{cid}: {key} used but expected_region is empty")

        normalized = row["user_input"].strip()
        if normalized in seen_input:
            print(f"WARN duplicate user_input: {seen_input[normalized]} and {cid}")
        else:
            seen_input[normalized] = cid

    dev = sum(row["split"] == "dev" for row in rows)
    holdout = sum(row["split"] == "holdout" for row in rows)
    if dev < MIN_DEV:
        fail(f"dev split too small: {dev} < {MIN_DEV}")
    if holdout < MIN_HOLDOUT:
        fail(f"holdout split too small: {holdout} < {MIN_HOLDOUT}")

    versions = {row["data_version"] for row in rows}
    if len(versions) != 1:
        fail(f"data_version must be pinned to one value, found {sorted(versions)}")
    pinned = versions.pop()

    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from data_version import version_info
        current = version_info()["data_version"]
    except Exception:
        current = None
    if current and current != pinned:
        message = f"pinned data_version {pinned} != current {current}"
        if strict:
            fail(message + "; re-baseline data_sensitive cases")
        print(f"WARN {message}; run with --strict to fail")

    origins = sorted({row["origin"] for row in rows})
    batches = sorted({row["batch"] for row in rows})
    ratio = dev / max(holdout, 1)
    print(f"PASS eval_set: {len(rows)} rows")
    print(f"PASS splits: dev={dev}, holdout={holdout}, ratio={ratio:.2f}:1")
    print(f"PASS pinned data_version: {pinned}")
    print(f"PASS origins: {', '.join(origins)}")
    print(f"PASS batches: {', '.join(batches)}")
    print("PASS formal schema, enums, capability refs, and assertion/context consistency")


if __name__ == "__main__":
    main()
