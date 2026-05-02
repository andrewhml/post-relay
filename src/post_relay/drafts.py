from __future__ import annotations

from post_relay.repository import create_draft_record, get_candidate_group
from post_relay.state import DraftState


class CandidateNotFound(ValueError):
    """Raised when a draft cannot be created because the candidate is missing."""


def create_draft_from_candidate(connection, candidate_group_id: int):
    candidate = get_candidate_group(connection, candidate_group_id)
    if candidate is None:
        raise CandidateNotFound(f"Candidate group #{candidate_group_id} was not found")

    draft = create_draft_record(
        connection,
        candidate_group_id=candidate.id,
        post_type=candidate.post_type_recommendation,
        status=DraftState.DRAFTING.value,
    )
    connection.commit()
    return draft
