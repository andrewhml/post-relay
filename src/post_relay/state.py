from __future__ import annotations

from enum import Enum


class InvalidStateTransition(ValueError):
    """Raised when a draft state transition would violate workflow safety."""


class DraftState(str, Enum):
    INGESTING = "ingesting"
    NEEDS_CONTEXT = "needs_context"
    DRAFTING = "drafting"
    AWAITING_REVIEW = "awaiting_review"
    NEEDS_EDITS = "needs_edits"
    APPROVED_FOR_QUEUE = "approved_for_queue"
    SCHEDULED = "scheduled"
    AWAITING_PUBLISH_APPROVAL = "awaiting_publish_approval"
    READY_TO_PUBLISH = "ready_to_publish"
    POSTING = "posting"
    POSTED = "posted"
    FAILED = "failed"
    ARCHIVED = "archived"


class ApprovalType(str, Enum):
    DRAFT = "draft"
    PUBLISH = "publish"


_ALLOWED_DRAFT_TRANSITIONS: dict[DraftState, set[DraftState]] = {
    DraftState.INGESTING: {DraftState.NEEDS_CONTEXT, DraftState.DRAFTING, DraftState.FAILED},
    DraftState.NEEDS_CONTEXT: {DraftState.DRAFTING, DraftState.ARCHIVED},
    DraftState.DRAFTING: {DraftState.AWAITING_REVIEW, DraftState.NEEDS_CONTEXT, DraftState.ARCHIVED},
    DraftState.AWAITING_REVIEW: {DraftState.NEEDS_EDITS, DraftState.APPROVED_FOR_QUEUE, DraftState.ARCHIVED},
    DraftState.NEEDS_EDITS: {DraftState.DRAFTING, DraftState.AWAITING_REVIEW, DraftState.ARCHIVED},
    DraftState.APPROVED_FOR_QUEUE: {DraftState.SCHEDULED, DraftState.NEEDS_EDITS, DraftState.ARCHIVED},
    DraftState.SCHEDULED: {DraftState.AWAITING_PUBLISH_APPROVAL, DraftState.NEEDS_EDITS, DraftState.ARCHIVED},
    DraftState.AWAITING_PUBLISH_APPROVAL: {DraftState.READY_TO_PUBLISH, DraftState.NEEDS_EDITS, DraftState.ARCHIVED},
    DraftState.READY_TO_PUBLISH: {DraftState.POSTING, DraftState.NEEDS_EDITS, DraftState.ARCHIVED},
    DraftState.POSTING: {DraftState.POSTED, DraftState.FAILED},
    DraftState.FAILED: {DraftState.READY_TO_PUBLISH, DraftState.ARCHIVED},
    DraftState.POSTED: {DraftState.ARCHIVED},
    DraftState.ARCHIVED: set(),
}


def transition_draft_state(current: DraftState, target: DraftState) -> DraftState:
    """Return target if the state transition is allowed, otherwise raise."""
    if target in _ALLOWED_DRAFT_TRANSITIONS[current]:
        return target
    raise InvalidStateTransition(f"Cannot transition post from {current.value} to {target.value}")
