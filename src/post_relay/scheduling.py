from __future__ import annotations

from typing import Optional

from post_relay.repository import (
    ApprovalRecord,
    DraftRecord,
    create_approval_record,
    get_draft,
    update_draft_schedule,
    update_draft_status,
)
from post_relay.state import ApprovalType, DraftState, transition_draft_state


class DraftNotFound(ValueError):
    """Raised when a scheduling action targets a missing draft."""


class DraftNotReadyForScheduling(ValueError):
    """Raised when a draft is scheduled before content approval."""


class DraftNotReadyForPublishApproval(ValueError):
    """Raised when publish approval is attempted too early."""


def schedule_draft(connection, draft_id: int, *, scheduled_for: str) -> DraftRecord:
    draft = _require_draft(connection, draft_id)
    if draft.status != DraftState.APPROVED_FOR_QUEUE.value:
        raise DraftNotReadyForScheduling(
            f"Post #{draft_id} must be approved_for_queue before scheduling; current status is {draft.status}"
        )
    target_state = transition_draft_state(DraftState(draft.status), DraftState.SCHEDULED)
    updated = update_draft_schedule(
        connection,
        draft.id,
        scheduled_for=scheduled_for,
        status=target_state.value,
    )
    connection.commit()
    return updated


def request_publish_approval(connection, draft_id: int) -> DraftRecord:
    draft = _require_draft(connection, draft_id)
    if draft.status != DraftState.SCHEDULED.value:
        raise DraftNotReadyForPublishApproval(
            f"Post #{draft_id} must be scheduled before publish approval is requested; current status is {draft.status}"
        )
    target_state = transition_draft_state(
        DraftState(draft.status), DraftState.AWAITING_PUBLISH_APPROVAL
    )
    updated = update_draft_status(connection, draft.id, target_state.value)
    connection.commit()
    return updated


def approve_draft_for_publishing(
    connection,
    draft_id: int,
    *,
    approved_by: Optional[str] = None,
    source_message_ref: Optional[str] = None,
    notes: Optional[str] = None,
) -> ApprovalRecord:
    draft = _require_draft(connection, draft_id)
    if draft.status != DraftState.AWAITING_PUBLISH_APPROVAL.value:
        raise DraftNotReadyForPublishApproval(
            f"Post #{draft_id} must be awaiting_publish_approval before publish approval; current status is {draft.status}"
        )

    transition_draft_state(DraftState(draft.status), DraftState.READY_TO_PUBLISH)
    approval = create_approval_record(
        connection,
        draft_id=draft.id,
        approval_type=ApprovalType.PUBLISH.value,
        approved_by=approved_by,
        source_message_ref=source_message_ref,
        notes=notes,
    )
    update_draft_status(connection, draft.id, DraftState.READY_TO_PUBLISH.value)
    connection.commit()
    return approval


def _require_draft(connection, draft_id: int) -> DraftRecord:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post #{draft_id} was not found")
    return draft
