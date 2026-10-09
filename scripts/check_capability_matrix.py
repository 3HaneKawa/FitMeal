from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "evals" / "capability_matrix.csv"

REQUIRED_COLUMNS = [
    "matrix_id",
    "group",
    "capability",
    "prd_ref",
    "v1_scope",
    "implementation_status",
    "coverage_values",
    "expected_behavior",
    "hard_constraints",
    "case_target",
    "holdout_target",
    "notes",
]
REQUIRED_IDS = {
    *[f"F{i:02d}" for i in range(1, 16)],
    *[f"S{i:02d}" for i in range(1, 6)],
    *[f"B{i:02d}" for i in range(1, 6)],
    *[f"L{i:02d}" for i in range(1, 5)],
    "X01",
    "O01",
}
ALLOWED_SCOPES = {
    "v1_required",
    "v1_promised_not_ready",
    "v1_out_of_scope",
    "future_post_v1",
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL {message}")


def main() -> None:
    data = MATRIX.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        fail("capability_matrix.csv must not contain a UTF-8 BOM")
    if b"\r\n" in data:
        fail("capability_matrix.csv must use LF line endings")

    with MATRIX.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != REQUIRED_COLUMNS:
            fail(f"unexpected columns: {reader.fieldnames}")
        rows = list(reader)

    ids = [row["matrix_id"] for row in rows]
    if len(ids) != len(set(ids)):
        fail("matrix_id values must be unique")
    missing = sorted(REQUIRED_IDS - set(ids))
    if missing:
        fail(f"missing matrix rows: {', '.join(missing)}")
    extra = sorted(set(ids) - REQUIRED_IDS)
    if extra:
        fail(f"unexpected matrix rows: {', '.join(extra)}")

    for row in rows:
        if row["v1_scope"] not in ALLOWED_SCOPES:
            fail(f"{row['matrix_id']}: invalid v1_scope={row['v1_scope']!r}")
        if not row["expected_behavior"].strip():
            fail(f"{row['matrix_id']}: expected_behavior is empty")
        if not row["hard_constraints"].strip():
            fail(f"{row['matrix_id']}: hard_constraints is empty")
        for field in ("case_target", "holdout_target"):
            value = row[field]
            if not value.isdigit() or int(value) < 0:
                fail(f"{row['matrix_id']}: {field} must be a non-negative integer")

    by_id = {row["matrix_id"]: row for row in rows}
    if by_id["F10"]["v1_scope"] != "v1_promised_not_ready":
        fail("F10 must remain v1_promised_not_ready")
    if by_id["F10"]["implementation_status"] != "not_implemented":
        fail("F10 must keep an explicit not_implemented status until delivered")
    if by_id["S01"]["v1_scope"] != "v1_required":
        fail("S01 must be part of v1")
    if "filter" not in by_id["S01"]["coverage_values"]:
        fail("S01 must describe filtering rather than blanket blocking")
    if by_id["O01"]["v1_scope"] != "future_post_v1":
        fail("knowledge-base retrieval must remain future_post_v1")

    functional = sum(row["group"] == "functional" for row in rows)
    risk = sum(row["group"] == "risk" for row in rows)
    boundary = sum(row["group"] == "boundary" for row in rows)
    language = sum(row["group"] == "language" for row in rows)
    print(f"PASS capability matrix: {len(rows)} rows")
    print(f"PASS groups: functional={functional}, risk={risk}, boundary={boundary}, language={language}")
    print("PASS E1 capability freeze is internally consistent")


if __name__ == "__main__":
    main()
