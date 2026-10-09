from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOAL_RULES = ROOT / "data" / "goal_rules.csv"
RUBRIC = ROOT / "evals" / "rubric.md"
GOALS = {
    "fat_loss": "减脂",
    "muscle_gain": "增肌",
    "maintain": "维持",
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL {message}")


def main() -> None:
    with GOAL_RULES.open(newline="", encoding="utf-8-sig") as f:
        rules = {row["goal"]: row for row in csv.DictReader(f)}
    text = RUBRIC.read_text(encoding="utf-8")

    checked = 0
    for goal, label in GOALS.items():
        if goal not in rules:
            fail(f"goal_rules.csv is missing {goal}")
        rule = rules[goal]
        pattern = re.compile(
            rf"^\|\s*{re.escape(label)}\s+{re.escape(goal)}\s*\|"
            r"\s*(\d+)-(\d+)\s*kcal\s*\|"
            r"\s*≥(\d+)\s*g\s*\|"
            r"\s*≤(\d+)\s*g\s*\|$",
            re.MULTILINE,
        )
        match = pattern.search(text)
        if not match:
            fail(f"rubric.md has no parseable nutrition row for {goal}")
        values = tuple(int(x) for x in match.groups())
        expected = (
            int(rule["calorie_min"]), int(rule["calorie_max"]),
            int(rule["protein_min"]), int(rule["fat_max"]),
        )
        if values != expected:
            fail(f"{goal}: rubric={values}, goal_rules={expected}")
        checked += 1

    if "data/goal_rules.csv" not in text or "pass_rule" not in text:
        fail("rubric.md must state goal_rules.csv as source and pass_rule override semantics")

    print(f"PASS nutrition consistency: {checked} goals match goal_rules.csv")
    print("PASS rubric states scoring-signal vs case-level pass_rule semantics")


if __name__ == "__main__":
    main()
