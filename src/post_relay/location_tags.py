from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from post_relay.repository import (
    DraftLocationTagRecord,
    get_candidate_group,
    get_draft,
    invalidate_active_approvals,
    list_active_approvals,
    upsert_draft_location_tag,
    update_draft_status,
)
from post_relay.state import DraftState, transition_draft_state


class DraftNotFound(ValueError):
    """Raised when a location tag action targets a missing draft."""


@dataclass(frozen=True)
class LocationPageCandidate:
    page_id: str
    name: str
    location: Mapping[str, Any]
    link: Optional[str]


@dataclass(frozen=True)
class LocationPageSearchResult:
    query: str
    candidates: list[LocationPageCandidate]

    def to_text(self) -> str:
        lines = [
            "Meta location page search",
            f"Query: {self.query}",
            "Official read route: GET /pages/search",
        ]
        if not self.candidates:
            lines.append("Candidates: <none>")
        else:
            lines.append("Candidates:")
            for index, candidate in enumerate(self.candidates, start=1):
                location_bits = []
                for field_name in ("city", "region", "state", "country"):
                    value = candidate.location.get(field_name)
                    if value:
                        location_bits.append(str(value))
                location_label = ", ".join(location_bits) or "<no structured location>"
                lines.append(f"  {index}. {candidate.name} ({candidate.page_id}) — {location_label}")
        lines.extend(
            [
                "No Meta publishing endpoints were called.",
                "Select a candidate explicitly before Post Relay can send a location_id.",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class DraftLocationCandidateReview:
    draft_id: int
    query: str
    status: str
    candidates: list[LocationPageCandidate]
    context: str

    def to_text(self) -> str:
        if self.status == "needs_clarification":
            return "\n".join(
                [
                    f"Need a more specific location before searching Meta Pages for draft #{self.draft_id}.",
                    f"Current location context: {self.context or '<none>'}",
                    "Please confirm the specific market/venue/landmark, choose a general city tag, or say to skip the Meta location tag.",
                    "No Meta network calls were made.",
                    "No location tag was set.",
                ]
            )
        lines = [
            f"Possible Meta location tags for draft #{self.draft_id}",
            f"Query: {self.query}",
            "Official read route: GET /pages/search",
        ]
        if self.status == "search_planned":
            lines.extend(
                [
                    "Search planned only; no Meta network calls were made.",
                    "Run without --dry-run after confirming the query to fetch candidates.",
                    "No location tag was set.",
                ]
            )
            return "\n".join(lines)
        if not self.candidates:
            lines.append("Candidates: <none>")
        else:
            lines.append("Candidates:")
            for index, candidate in enumerate(self.candidates, start=1):
                location_label = _location_label(candidate.location)
                lines.append(f"  {index}. {candidate.name} ({candidate.page_id}) — {location_label}")
                if candidate.link:
                    lines.append(f"     Link: {candidate.link}")
        lines.extend(
            [
                "Reply with `use 1`, `use 2`, etc. only after confirming the correct place.",
                "No location tag was set.",
            ]
        )
        return "\n".join(lines)


def build_location_candidate_review(
    connection,
    draft_id: int,
    *,
    query: Optional[str] = None,
    client=None,
    max_candidates: int = 5,
) -> DraftLocationCandidateReview:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Draft #{draft_id} was not found")
    context = _location_context(connection, draft)
    resolved_query = (query or "").strip() or context
    if not query and _needs_location_clarification(context):
        return DraftLocationCandidateReview(
            draft_id=draft.id,
            query=resolved_query,
            status="needs_clarification",
            candidates=[],
            context=context,
        )
    if client is None:
        return DraftLocationCandidateReview(
            draft_id=draft.id,
            query=resolved_query,
            status="search_planned",
            candidates=[],
            context=context,
        )
    search_result = search_location_pages(client, resolved_query)
    ranked = _rank_candidates(search_result.candidates, resolved_query)[:max_candidates]
    return DraftLocationCandidateReview(
        draft_id=draft.id,
        query=resolved_query,
        status="candidates_found" if ranked else "no_candidates",
        candidates=ranked,
        context=context,
    )


def _location_context(connection, draft) -> str:
    if draft.location_text:
        return draft.location_text.strip()
    candidate = get_candidate_group(connection, draft.candidate_group_id)
    parts = []
    if candidate:
        parts.extend([candidate.title, candidate.source_folder])
        if candidate.source_year:
            parts.append(str(candidate.source_year))
    if draft.caption:
        parts.append(draft.caption)
    return " ".join(part for part in parts if part).strip()


def _needs_location_clarification(context: str) -> bool:
    normalized = context.strip().lower()
    if not normalized:
        return True
    words = [word.strip(",.;:!?()[]{}") for word in normalized.replace("/", " ").split()]
    words = [word for word in words if word]
    if len(words) <= 3:
        return True
    broad_terms = {
        "seoul",
        "tokyo",
        "kyoto",
        "japan",
        "korea",
        "south",
        "thailand",
        "bangkok",
        "city",
        "market",
        "beach",
        "temple",
    }
    meaningful = [word for word in words if word not in broad_terms]
    return len(meaningful) < 2


def _rank_candidates(candidates: list[LocationPageCandidate], query: str) -> list[LocationPageCandidate]:
    query_tokens = _tokens(query)

    def score(candidate: LocationPageCandidate) -> tuple[int, str]:
        name_tokens = _tokens(candidate.name)
        location_tokens = _tokens(" ".join(str(value) for value in candidate.location.values()))
        name_overlap = len(query_tokens & name_tokens)
        location_overlap = len(query_tokens & location_tokens)
        exact_bonus = 5 if candidate.name.lower() in query.lower() or query.lower() in candidate.name.lower() else 0
        structured_bonus = 1 if candidate.location else 0
        return (exact_bonus + name_overlap * 3 + location_overlap + structured_bonus, candidate.name.lower())

    return sorted(candidates, key=score, reverse=True)


def _tokens(text: str) -> set[str]:
    return {part.strip(",.;:!?()[]{}").lower() for part in text.split() if part.strip(",.;:!?()[]{}")}


def _location_label(location: Mapping[str, Any]) -> str:
    location_bits = []
    for field_name in ("city", "region", "state", "country"):
        value = location.get(field_name)
        if value:
            location_bits.append(str(value))
    return ", ".join(location_bits) or "<no structured location>"


def search_location_pages(client, query: str) -> LocationPageSearchResult:
    payload = client.search_pages(query=query, fields="id,name,location,link")
    candidates: list[LocationPageCandidate] = []
    for item in payload.get("data") or []:
        if not isinstance(item, Mapping):
            continue
        page_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not page_id or not name:
            continue
        raw_location = item.get("location")
        location = raw_location if isinstance(raw_location, Mapping) else {}
        link = item.get("link") if isinstance(item.get("link"), str) else None
        candidates.append(
            LocationPageCandidate(
                page_id=page_id,
                name=name,
                location=location,
                link=link,
            )
        )
    return LocationPageSearchResult(query=query, candidates=candidates)


def set_draft_location_tag(
    connection,
    draft_id: int,
    *,
    page_id: str,
    name: str,
    source: str,
) -> DraftLocationTagRecord:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Draft #{draft_id} was not found")
    tag = upsert_draft_location_tag(
        connection,
        draft_id=draft.id,
        page_id=page_id,
        name=name,
        source=source,
        status="resolved",
    )
    if list_active_approvals(connection, draft.id):
        invalidate_active_approvals(
            connection,
            draft.id,
            reason="resolved Meta location tag edit",
        )
        update_draft_status(
            connection,
            draft.id,
            transition_draft_state(DraftState(draft.status), DraftState.NEEDS_EDITS).value,
        )
    connection.commit()
    return tag
