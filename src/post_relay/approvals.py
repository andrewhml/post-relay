from __future__ import annotations

from typing import Optional, Sequence

from post_relay.repository import (
    ApprovalRecord,
    DraftRecord,
    create_approval_record,
    get_draft,
    invalidate_active_approvals,
    list_active_approvals,
    update_draft_content as persist_draft_content,
    update_draft_status,
)
from post_relay.state import ApprovalType, DraftState, transition_draft_state


class DraftNotFound(ValueError):
    """Raised when an approval action targets a missing draft."""


class DraftNotReadyForApproval(ValueError):
    """Raised when draft approval is attempted before the draft is in review."""


def submit_draft_for_review(connection, draft_id: int) -> DraftRecord:
    draft = _require_draft(connection, draft_id)
    target_state = transition_draft_state(
        DraftState(draft.status), DraftState.AWAITING_REVIEW
    )
    updated = update_draft_status(connection, draft_id, target_state.value)
    connection.commit()
    return updated


def approve_draft_content(
    connection,
    draft_id: int,
    *,
    approved_by: Optional[str] = None,
    source_message_ref: Optional[str] = None,
    notes: Optional[str] = None,
) -> ApprovalRecord:
    draft = _require_draft(connection, draft_id)
    if draft.status != DraftState.AWAITING_REVIEW.value:
        raise DraftNotReadyForApproval(
            f"Draft #{draft_id} must be awaiting_review before draft approval; current status is {draft.status}"
        )

    transition_draft_state(DraftState(draft.status), DraftState.APPROVED_FOR_QUEUE)
    approval = create_approval_record(
        connection,
        draft_id=draft.id,
        approval_type=ApprovalType.DRAFT.value,
        approved_by=approved_by,
        source_message_ref=source_message_ref,
        notes=notes,
    )
    update_draft_status(connection, draft.id, DraftState.APPROVED_FOR_QUEUE.value)
    connection.commit()
    return approval


def edit_draft_content(
    connection,
    draft_id: int,
    *,
    caption: Optional[str] = None,
    hashtags: Optional[Sequence[str]] = None,
    location_text: Optional[str] = None,
    alt_text: Optional[str] = None,
) -> DraftRecord:
    draft = _require_draft(connection, draft_id)
    changed = _has_material_change(
        draft,
        caption=caption,
        hashtags=hashtags,
        location_text=location_text,
        alt_text=alt_text,
    )
    status = None
    active_approvals = list_active_approvals(connection, draft.id)
    if changed and active_approvals:
        status = transition_draft_state(DraftState(draft.status), DraftState.NEEDS_EDITS).value
        invalidate_active_approvals(
            connection,
            draft.id,
            reason="material draft content edit",
        )

    updated = persist_draft_content(
        connection,
        draft.id,
        caption=caption,
        hashtags=hashtags,
        location_text=location_text,
        alt_text=alt_text,
        status=status,
    )
    connection.commit()
    return updated


def _require_draft(connection, draft_id: int) -> DraftRecord:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Draft #{draft_id} was not found")
    return draft


def _has_material_change(
    draft: DraftRecord,
    *,
    caption: Optional[str],
    hashtags: Optional[Sequence[str]],
    location_text: Optional[str],
    alt_text: Optional[str],
) -> bool:
    if caption is not None and caption != draft.caption:
        return True
    if hashtags is not None:
        import json

        if json.dumps(list(hashtags)) != draft.hashtags_json:
            return True
    if location_text is not None and location_text != draft.location_text:
        return True
    if alt_text is not None and alt_text != draft.alt_text:
        return True
    return False
