import pytest

from post_relay.state import DraftState, ApprovalType, InvalidStateTransition, transition_draft_state


def test_draft_state_progresses_through_double_approval_path():
    state = DraftState.DRAFTING

    state = transition_draft_state(state, DraftState.AWAITING_REVIEW)
    state = transition_draft_state(state, DraftState.APPROVED_FOR_QUEUE)
    state = transition_draft_state(state, DraftState.SCHEDULED)
    state = transition_draft_state(state, DraftState.AWAITING_PUBLISH_APPROVAL)
    state = transition_draft_state(state, DraftState.READY_TO_PUBLISH)

    assert state is DraftState.READY_TO_PUBLISH


def test_material_edit_after_approval_invalidates_back_to_needs_edits():
    state = transition_draft_state(DraftState.APPROVED_FOR_QUEUE, DraftState.NEEDS_EDITS)

    assert state is DraftState.NEEDS_EDITS


def test_posting_requires_publish_approval_ready_state():
    with pytest.raises(InvalidStateTransition):
        transition_draft_state(DraftState.APPROVED_FOR_QUEUE, DraftState.POSTING)


def test_approval_types_distinguish_draft_from_publish_authorization():
    assert ApprovalType.DRAFT.value == "draft"
    assert ApprovalType.PUBLISH.value == "publish"
