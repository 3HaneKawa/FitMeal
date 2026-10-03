import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from recommend import recommend


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


def dry_run():
    cases = load_cases()
    results = []
    for case in cases:
        output = None
        error = None
        if case["expected_intent"] == "cook":
            user_input = {
                "intent": "cook",
                "ingredients": [
                    item for item in case["expected_ingredients"].split(";") if item
                ],
                "goal": case["expected_goal"],
                "meal_type": "dinner",
                "time_limit": int(case["expected_time"]) if case["expected_time"] else None,
                "region": case["expected_region"],
                "allergies": [],
            }
            try:
                output = recommend(user_input)
            except Exception as exc:
                error = str(exc)

        results.append({
            "run_id": "DRY_RUN",
            "case_id": case["case_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actual_output": json.dumps(output, ensure_ascii=False) if output is not None else "",
            "hit": expected_hit(case, output) if output is not None else False,
            "error": error or "",
        })

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RUNS_DIR / "dry_run.csv"
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(f"Wrote {len(results)} dry-run results to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        dry_run()
    else:
        print("Only --dry-run is supported before Dify API integration.")
