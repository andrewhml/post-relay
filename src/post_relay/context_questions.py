from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from post_relay.repository import (
    CandidateGroupRecord,
    DraftRecord,
    ContextQuestionRecord,
    create_context_question,
    get_candidate_group,
    get_draft,
    list_context_questions,
)


class DraftNotFound(ValueError):
    """Raised when context questions cannot be generated for a missing draft."""


@dataclass(frozen=True)
class QuestionTemplate:
    field_name: str
    question_text: str


def generate_context_questions_for_draft(connection, draft_id: int) -> List[ContextQuestionRecord]:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Draft #{draft_id} was not found")

    candidate = get_candidate_group(connection, draft.candidate_group_id)
    for template in _missing_context_templates(draft, candidate):
        create_context_question(
            connection,
            draft_id=draft.id,
            field_name=template.field_name,
            question_text=template.question_text,
        )
    connection.commit()
    return list_context_questions(connection, draft.id)


def _missing_context_templates(
    draft: DraftRecord, candidate: Optional[CandidateGroupRecord]
) -> List[QuestionTemplate]:
    templates: List[QuestionTemplate] = []
    if not draft.location_text:
        templates.append(
            QuestionTemplate(
                field_name="place",
                question_text="Where exactly was this photo set taken?",
            )
        )
    templates.append(
        QuestionTemplate(
            field_name="trip_name",
            question_text="What trip or collection should this post be associated with?",
        )
    )
    templates.append(
        QuestionTemplate(
            field_name="approximate_date",
            question_text=_approximate_date_question(candidate),
        )
    )
    templates.append(
        QuestionTemplate(
            field_name="mood",
            question_text="What mood should the caption convey?",
        )
    )
    templates.append(
        QuestionTemplate(
            field_name="story_angle",
            question_text="What story or takeaway should this post highlight?",
        )
    )
    return templates


def _approximate_date_question(candidate: Optional[CandidateGroupRecord]) -> str:
    if candidate is not None and candidate.source_year is not None:
        return (
            f"Should this be described as part of the {candidate.source_year} trip, "
            "or is there a more specific date?"
        )
    return "When was this photo set taken?"
