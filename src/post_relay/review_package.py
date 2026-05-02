from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional

from post_relay.repository import (
    get_candidate_group,
    get_draft,
    list_candidate_group_photo_paths,
)


class DraftNotFound(ValueError):
    """Raised when a draft review package cannot be built for a missing draft."""


@dataclass(frozen=True)
class DraftReviewPackage:
    draft_id: int
    status: str
    candidate_title: str
    post_type: str
    photo_file_paths: List[str]
    caption: str
    location: str
    hashtags: List[str]
    alt_text: str
    unresolved_context_notes: List[str]
    allowed_next_actions: List[str]

    def to_text(self) -> str:
        lines = [
            "Draft Review Package",
            f"Draft ID: {self.draft_id}",
            f"Status: {self.status}",
            f"Candidate: {self.candidate_title}",
            f"Post type: {self.post_type}",
            "Photos:",
        ]
        if self.photo_file_paths:
            lines.extend(
                f"  {index}. {path}"
                for index, path in enumerate(self.photo_file_paths, start=1)
            )
        else:
            lines.append("  <none>")
        lines.extend(
            [
                f"Caption: {self.caption or '<empty>'}",
                f"Location: {self.location or '<empty>'}",
                f"Hashtags: {_format_hashtags(self.hashtags)}",
                f"Alt text: {self.alt_text or '<empty>'}",
                "Unresolved context notes:",
            ]
        )
        lines.extend(_format_bullets(self.unresolved_context_notes))
        lines.append("Allowed next actions:")
        lines.extend(_format_bullets(self.allowed_next_actions))
        return "\n".join(lines)


def build_draft_review_package(connection, draft_id: int) -> DraftReviewPackage:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Draft #{draft_id} was not found")

    candidate = get_candidate_group(connection, draft.candidate_group_id)
    candidate_title = candidate.title if candidate is not None else "<missing candidate>"
    photo_file_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    hashtags = _parse_hashtags(draft.hashtags_json)
    caption = draft.caption or ""
    location = draft.location_text or ""
    alt_text = draft.alt_text or ""

    return DraftReviewPackage(
        draft_id=draft.id,
        status=draft.status,
        candidate_title=candidate_title,
        post_type=draft.post_type,
        photo_file_paths=photo_file_paths,
        caption=caption,
        location=location,
        hashtags=hashtags,
        alt_text=alt_text,
        unresolved_context_notes=_unresolved_context_notes(
            caption=caption,
            location=location,
            hashtags=hashtags,
            alt_text=alt_text,
        ),
        allowed_next_actions=[
            "add caption/context",
            "answer unresolved context notes",
            "request edits",
            "approve draft",
        ],
    )


def _parse_hashtags(hashtags_json: Optional[str]) -> List[str]:
    if not hashtags_json:
        return []
    parsed = json.loads(hashtags_json)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _unresolved_context_notes(
    *, caption: str, location: str, hashtags: List[str], alt_text: str
) -> List[str]:
    notes: List[str] = []
    if not caption:
        notes.append("Caption is empty.")
    if not location:
        notes.append("Location is empty.")
    if not hashtags:
        notes.append("Hashtags are empty.")
    if not alt_text:
        notes.append("Alt text is empty.")
    return notes


def _format_hashtags(hashtags: List[str]) -> str:
    if not hashtags:
        return "<empty>"
    return " ".join(hashtags)


def _format_bullets(items: List[str]) -> List[str]:
    if not items:
        return ["  - <none>"]
    return [f"  - {item}" for item in items]
