from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional


LARGE_CANDIDATE_PHOTO_COUNT = 120

from post_relay.drafts import CandidateNotFound, create_draft_from_candidate
from post_relay.repository import (
    CandidateGroupRecord,
    ConversationContextNoteRecord,
    ConversationThreadRecord,
    create_conversation_context_note,
    create_conversation_thread,
    get_active_conversation_thread_for_channel,
    get_draft,
    list_candidate_groups,
    update_conversation_thread,
)


class DmIntakeError(ValueError):
    pass


@dataclass(frozen=True)
class DmIntakeResult:
    thread: ConversationThreadRecord
    suggested_candidates: list[CandidateGroupRecord]
    context_note: Optional[ConversationContextNoteRecord]
    continuing_existing_thread: bool
    next_safe_step: str
    narrowing_question: Optional[str] = None

    def to_text(self) -> str:
        lines = [
            "Post Relay DM intake",
            "Private DM mode: user-initiated",
            f"Conversation thread: #{self.thread.id} ({self.thread.status})",
        ]
        if self.continuing_existing_thread:
            lines.append("Continuing active thread for this DM channel.")
        if self.thread.draft_id is not None:
            lines.append(f"Linked draft: #{self.thread.draft_id}")
        if self.context_note is not None:
            lines.append(f"Recorded context note: {self.context_note.summary}")
        if self.narrowing_question is not None:
            lines.append(f"Narrowing needed: {self.narrowing_question}")
        if self.suggested_candidates:
            lines.append("Suggested candidate groups:")
            for candidate in self.suggested_candidates:
                photo_label = "photo" if candidate.photo_count == 1 else "photos"
                large_set_note = (
                    " Large set: narrow before rendering a contact sheet. Run drafts artifacts render after choosing this candidate to get a bounded first-pass plan."
                    if candidate.photo_count >= LARGE_CANDIDATE_PHOTO_COUNT
                    else ""
                )
                lines.append(
                    f"  - #{candidate.id} {candidate.title} — {candidate.post_type_recommendation}, "
                    f"{candidate.photo_count} {photo_label}.{large_set_note}"
                )
            lines.append("Next options: choose candidate #<id>, ask for a different set, or add more context.")
        lines.append(f"Next safe step: {self.next_safe_step}")
        lines.append("No Discord or Meta network calls were made.")
        return "\n".join(lines)


def handle_dm_intake(
    connection,
    message: str,
    *,
    discord_channel_id: Optional[str] = None,
    draft_id: Optional[int] = None,
) -> DmIntakeResult:
    sanitized_message = _sanitize_text(message)
    if not sanitized_message:
        raise DmIntakeError("DM message must not be empty")

    if draft_id is not None and get_draft(connection, draft_id) is None:
        raise DmIntakeError(f"Draft #{draft_id} was not found")

    chosen_candidate_id = _chosen_candidate_id(sanitized_message)
    if draft_id is None and chosen_candidate_id is not None:
        try:
            draft = create_draft_from_candidate(connection, chosen_candidate_id)
        except CandidateNotFound as error:
            raise DmIntakeError(str(error)) from error
        draft_id = draft.id

    active_thread = (
        get_active_conversation_thread_for_channel(connection, discord_channel_id)
        if discord_channel_id is not None
        else None
    )
    continuing = active_thread is not None
    if active_thread is None:
        thread = create_conversation_thread(
            connection,
            draft_id=draft_id,
            discord_channel_id=discord_channel_id,
            status="waiting_for_user",
            last_prompt_summary=_prompt_summary_for_message(sanitized_message),
        )
    else:
        thread = update_conversation_thread(
            connection,
            active_thread.id,
            draft_id=draft_id,
            status="waiting_for_user",
            last_prompt_summary=_prompt_summary_for_message(sanitized_message),
        )

    context_note = None
    if draft_id is not None:
        context_note = create_conversation_context_note(
            connection,
            thread_id=thread.id,
            draft_id=draft_id,
            summary=_context_summary(sanitized_message),
        )

    narrowing_question = None
    if draft_id is None:
        suggested_candidates, narrowing_question = _candidate_suggestions_or_narrowing(
            connection, sanitized_message
        )
    else:
        suggested_candidates = []
    next_safe_step = "media selection" if draft_id is not None else "candidate selection"
    if narrowing_question is not None:
        next_safe_step = "candidate narrowing"
    return DmIntakeResult(
        thread=thread,
        suggested_candidates=suggested_candidates,
        context_note=context_note,
        continuing_existing_thread=continuing,
        next_safe_step=next_safe_step,
        narrowing_question=narrowing_question,
    )


@dataclass(frozen=True)
class _ScoredCandidate:
    score: int
    candidate: CandidateGroupRecord


def _candidate_suggestions_or_narrowing(
    connection, message: str, limit: int = 3
) -> tuple[list[CandidateGroupRecord], Optional[str]]:
    scored = _rank_scored_candidates(connection, message)
    if not scored:
        return [], _narrowing_question(message)
    top = scored[0]
    if top.score == 0 and top.candidate.photo_count >= LARGE_CANDIDATE_PHOTO_COUNT:
        return [], _narrowing_question(message)
    return [item.candidate for item in scored[:limit]], None


def _rank_candidate_suggestions(connection, message: str, limit: int = 3) -> list[CandidateGroupRecord]:
    return [item.candidate for item in _rank_scored_candidates(connection, message)[:limit]]


def _rank_scored_candidates(connection, message: str) -> list[_ScoredCandidate]:
    terms = _keywords(message)
    candidates = list_candidate_groups(connection)
    scored = []
    for candidate in candidates:
        haystack = " ".join(
            [candidate.title, candidate.source_folder, candidate.reason or "", candidate.post_type_recommendation or ""]
        ).lower()
        score = sum(1 for term in terms if term in haystack)
        scored.append((score, candidate.id, candidate))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [_ScoredCandidate(score=score, candidate=candidate) for score, _id, candidate in scored]


def _narrowing_question(message: str) -> str:
    return (
        f"'{_context_summary(message)}' could match a very broad photo set. "
        "Please add a date, neighborhood, folder name, or 5-10 filenames before I render a contact sheet."
    )


def _chosen_candidate_id(message: str) -> Optional[int]:
    match = re.search(r"(?i)\b(?:choose|use|select)\s+(?:candidate\s*)?#?\s*(\d+)\b", message)
    if match:
        return int(match.group(1))
    match = re.search(r"(?i)\bcandidate\s*#?\s*(\d+)\b", message)
    if match:
        return int(match.group(1))
    return None


def _keywords(message: str) -> list[str]:
    stop_words = {
        "about",
        "and",
        "from",
        "make",
        "my",
        "photos",
        "post",
        "start",
        "the",
        "this",
        "with",
    }
    words = [word.lower() for word in re.findall(r"[a-zA-Z0-9]+", message)]
    return [word for word in words if len(word) > 2 and word not in stop_words]


def _sanitize_text(value: str) -> str:
    sanitized = re.sub(r"(?i)(token|secret|password|key)\s*=\s*\S+", r"\1=[redacted]", value)
    sanitized = re.sub(r"https?://\S+", "[redacted-url]", sanitized)
    return " ".join(sanitized.split()).strip()


def _prompt_summary_for_message(message: str) -> str:
    return _truncate(f"User-initiated DM: {_context_summary(message)}", 180)


def _context_summary(message: str) -> str:
    return _truncate(message, 220)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"
