"""最小反馈事件存储的离线自测。

只使用临时目录，不读取或写入 runtime/feedback_events.csv。
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from feedback_store import ALLOWED_ACTIONS, ACTION_LABELS, FeedbackError, record_feedback


def expect_error(payload: dict[str, str], expected_text: str) -> None:
    try:
        record_feedback(payload)
    except FeedbackError as exc:
        if expected_text not in str(exc):
            raise AssertionError(f"unexpected error: {exc}") from exc
        return
    raise AssertionError(f"expected FeedbackError containing {expected_text!r}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="fitmeal-feedback-") as temp_dir:
        path = Path(temp_dir) / "feedback_events.csv"
        for action in sorted(ALLOWED_ACTIONS):
            event = record_feedback(
                {
                    "request_id": "req-test-001",
                    "recipe_id": "R001",
                    "action": action,
                    "reason": ACTION_LABELS[action],
                    "note": "离线自测",
                },
                path,
            )
            expected = {
                "request_id": "req-test-001",
                "recipe_id": "R001",
                "action": action,
                "reason": ACTION_LABELS[action],
                "note": "离线自测",
            }
            for key, value in expected.items():
                if event[key] != value:
                    raise AssertionError(f"{action}: {key} mismatch")
            if not event["event_id"] or not event["created_at"]:
                raise AssertionError(f"{action}: event_id/created_at missing")

        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != len(ALLOWED_ACTIONS):
            raise AssertionError("feedback row count mismatch")
        if {row["action"] for row in rows} != ALLOWED_ACTIONS:
            raise AssertionError("feedback actions were not persisted")

        expect_error(
            {"request_id": "req-test-001", "recipe_id": "R001", "action": "unknown"},
            "action 必须是",
        )
        expect_error(
            {"request_id": "req-test-001", "action": "accept"},
            "recipe_id 不能为空",
        )
        expect_error(
            {"request_id": "", "recipe_id": "R001", "action": "accept"},
            "request_id 不能为空",
        )
        expect_error(
            {
                "request_id": "req-test-001",
                "recipe_id": "R001",
                "action": "reject",
                "reason": "另一个原因",
            },
            "reason 不是支持的反馈原因",
        )

    print("PASS feedback store: four actions persisted and invalid input rejected")


if __name__ == "__main__":
    main()
