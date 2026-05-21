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
    get_draft_location_tag,
    get_guided_draft_package,
    list_context_questions,
)


class DraftNotFound(ValueError):
    """Raised when context questions cannot be generated for a missing draft."""


@dataclass(frozen=True)
class QuestionTemplate:
    field_name: str
    question_text: str


def generate_context_questions_for_draft(
    connection, draft_id: int
) -> List[ContextQuestionRecord]:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post #{draft_id} was not found")

    candidate = get_candidate_group(connection, draft.candidate_group_id)
    accepted_package = get_guided_draft_package(connection, draft.id)
    location_tag = get_draft_location_tag(connection, draft.id)
    has_accepted_package = (
        accepted_package is not None and accepted_package.accepted_at is not None
    )
    has_reviewed_location_tag = (
        location_tag is not None and location_tag.status == "resolved"
    )
    for template in _missing_context_templates(
        draft,
        candidate,
        has_accepted_guided_package=has_accepted_package,
        has_reviewed_location_tag=has_reviewed_location_tag,
    ):
        create_context_question(
            connection,
            draft_id=draft.id,
            field_name=template.field_name,
            question_text=template.question_text,
        )
    connection.commit()
    return list_context_questions(connection, draft.id)


def _missing_context_templates(
    draft: DraftRecord,
    candidate: Optional[CandidateGroupRecord],
    *,
    has_accepted_guided_package: bool = False,
    has_reviewed_location_tag: bool = False,
) -> List[QuestionTemplate]:
    templates: List[QuestionTemplate] = []
    if not draft.location_text:
        templates.append(
            QuestionTemplate(
                field_name="place",
                question_text="Where exactly was this photo set taken?",
            )
        )
    elif has_accepted_guided_package and not has_reviewed_location_tag:
        templates.append(
            QuestionTemplate(
                field_name="location_tag",
                question_text=(
                    "Freeform location text is local-only; should I search Meta Pages "
                    f"for a publishable location tag for {draft.location_text}?"
                ),
            )
        )
    if not _candidate_has_folder_context(candidate):
        templates.append(
            QuestionTemplate(
                field_name="trip_name",
                question_text="What trip or collection should this post be associated with?",
            )
        )
    if not _candidate_has_date_context(candidate):
        templates.append(
            QuestionTemplate(
                field_name="approximate_date",
                question_text=_approximate_date_question(candidate),
            )
        )
    if not draft.caption:
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


def _candidate_has_folder_context(candidate: Optional[CandidateGroupRecord]) -> bool:
    return candidate is not None and bool(candidate.source_folder)


def _candidate_has_date_context(candidate: Optional[CandidateGroupRecord]) -> bool:
    return candidate is not None and candidate.source_year is not None


def _approximate_date_question(candidate: Optional[CandidateGroupRecord]) -> str:
    if candidate is not None and candidate.source_year is not None:
        return (
            f"Should this be described as part of the {candidate.source_year} trip, "
            "or is there a more specific date?"
        )
    return "When was this photo set taken?"
