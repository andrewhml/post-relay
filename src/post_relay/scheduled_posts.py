from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from post_relay.repository import DraftRecord, list_drafts
from post_relay.state import DraftState

SCHEDULE_AWARE_STATUSES = {
    DraftState.SCHEDULED.value,
    DraftState.AWAITING_PUBLISH_APPROVAL.value,
    DraftState.READY_TO_PUBLISH.value,
    DraftState.POSTING.value,
}


@dataclass(frozen=True)
class ScheduledPostItem:
    draft_id: int
    status: str
    post_type: str
    scheduled_for: str

    def to_line(self) -> str:
        return f"#{self.draft_id} {self.status} {self.post_type} at {self.scheduled_for}"


@dataclass(frozen=True)
class ScheduledPostFeedback:
    items: list[ScheduledPostItem]

    def to_text(self) -> str:
        if not self.items:
            return "No scheduled posts are currently in the local queue."
        lines = ["Scheduled posts:"]
        lines.extend(f"  - {item.to_line()}" for item in self.items)
        lines.append("Use this queue before recommending another slot.")
        return "\n".join(lines)


def build_scheduled_post_feedback(
    connection,
    *,
    exclude_draft_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> ScheduledPostFeedback:
    items = [
        _item_from_draft(draft)
        for draft in list_drafts(connection)
        if draft.scheduled_for
        and draft.status in SCHEDULE_AWARE_STATUSES
        and draft.id != exclude_draft_id
    ]
    items.sort(key=lambda item: (item.scheduled_for, item.draft_id))
    if limit is not None:
        items = items[: max(limit, 0)]
    return ScheduledPostFeedback(items=items)


def _item_from_draft(draft: DraftRecord) -> ScheduledPostItem:
    return ScheduledPostItem(
        draft_id=draft.id,
        status=draft.status,
        post_type=draft.post_type,
        scheduled_for=draft.scheduled_for or "<unset>",
    )
