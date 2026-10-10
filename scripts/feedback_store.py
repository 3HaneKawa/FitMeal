"""FitMeal 最小用户反馈事件存储。

范围：
- 记录用户对某次推荐和某道菜的操作（采纳 / 不喜欢 / 太麻烦 / 换一批）。
- 事件只用于本地 Demo 复盘，不自动写入推荐排序。
- 运行时 CSV 被 .gitignore 排除，公开仓库不提交真实反馈。
"""

from __future__ import annotations

import csv
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_PATH = ROOT / "runtime" / "feedback_events.csv"

ALLOWED_ACTIONS = {"accept", "reject", "too_much", "regenerate"}
ACTION_LABELS = {
    "accept": "采纳",
    "reject": "不喜欢",
    "too_much": "太麻烦",
    "regenerate": "换一批",
}
FIELDS = (
    "event_id",
    "request_id",
    "recipe_id",
    "action",
    "reason",
    "note",
    "created_at",
)


class FeedbackError(ValueError):
    """反馈字段不合法时由接口层转换为 400。"""


def _clean_text(value: Any, max_length: int) -> str:
    text = "" if value is None else str(value).strip()
    text = re.sub(r"[\r\n\t]+", " ", text)
    return text[:max_length]


def record_feedback(payload: dict[str, Any], path: Path | None = None) -> dict[str, str]:
    """校验并追加一条反馈事件，返回写入结果。"""
    request_id = _clean_text(payload.get("request_id"), 64)
    recipe_id = _clean_text(payload.get("recipe_id"), 80)
    action = _clean_text(payload.get("action"), 24).lower()
    reason = _clean_text(payload.get("reason"), 120)
    note = _clean_text(payload.get("note"), 500)

    if not request_id:
        raise FeedbackError("request_id 不能为空")
    if action not in ALLOWED_ACTIONS:
        raise FeedbackError("action 必须是 accept、reject、too_much 或 regenerate")
    if action in {"accept", "reject", "too_much", "regenerate"} and not recipe_id:
        raise FeedbackError("recipe_id 不能为空")
    if reason and reason not in ACTION_LABELS.values():
        raise FeedbackError("reason 不是支持的反馈原因")

    event = {
        "event_id": uuid.uuid4().hex,
        "request_id": request_id,
        "recipe_id": recipe_id,
        "action": action,
        "reason": reason or ACTION_LABELS[action],
        "note": note,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    target = path or FEEDBACK_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    new_file = not target.exists() or target.stat().st_size == 0
    with target.open("a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(event)
    return event