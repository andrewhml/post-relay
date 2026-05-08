from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from post_relay.repository import (
    DraftRecord,
    get_draft,
    list_candidate_group_photo_items,
    update_draft_content,
    upsert_guided_draft_package,
)


class DraftNotFound(ValueError):
    pass


class InvalidGuidedDraftPackage(ValueError):
    pass


@dataclass(frozen=True)
class GuidedDraftPackage:
    draft_id: int
    post_type_recommendation: str
    post_type_rationale: str
    caption_options: list[str]
    hashtag_suggestions: list[str]
    location_text: Optional[str]
    alt_text: str
    growth_rationale: str
    context_questions: list[str]

    def to_text(self) -> str:
        lines = [
            "Guided Draft Package",
            f"Draft ID: {self.draft_id}",
            f"Post type recommendation: {self.post_type_recommendation}",
            f"Rationale: {self.post_type_rationale}",
            "Caption options:",
        ]
        lines.extend(f"  {index}. {caption}" for index, caption in enumerate(self.caption_options, start=1))
        lines.extend(
            [
                "Hashtag suggestions:",
                "  " + " ".join(self.hashtag_suggestions),
                "Location:",
                f"  {self.location_text or 'Needs Andrew confirmation'}",
                "Alt text / accessibility notes:",
                f"  {self.alt_text}",
                "Growth rationale:",
                f"  {self.growth_rationale}",
                "Questions for Andrew:",
            ]
        )
        if self.context_questions:
            lines.extend(f"  - {question}" for question in self.context_questions)
        else:
            lines.append("  - <none>")
        lines.append("Safety: Do not fabricate exact location, date, people, event, or route facts.")
        return "\n".join(lines)


@dataclass(frozen=True)
class AcceptedGuidedDraftPackage:
    draft_id: int
    caption: str
    hashtags: list[str]
    location_text: Optional[str]
    alt_text: str
    growth_rationale: str

    def to_text(self) -> str:
        return "\n".join(
            [
                f"Accepted guided draft package for draft #{self.draft_id}",
                f"Caption: {self.caption}",
                "Hashtags: " + " ".join(self.hashtags),
                f"Location: {self.location_text or '<unconfirmed>'}",
                f"Alt text: {self.alt_text}",
                f"Growth rationale: {self.growth_rationale}",
            ]
        )


def build_guided_draft_package(
    connection,
    draft_id: int,
    *,
    location_text: Optional[str] = None,
    story_angle: Optional[str] = None,
    mood: Optional[str] = None,
    audience_hook: Optional[str] = None,
    include: Optional[str] = None,
    avoid: Optional[str] = None,
) -> GuidedDraftPackage:
    draft = _require_draft(connection, draft_id)
    items = list_candidate_group_photo_items(connection, draft.candidate_group_id, included_only=True)
    selected_count = len(items)
    post_type = _recommend_post_type(draft, selected_count)
    story = story_angle or "the feeling of this travel moment"
    hook = audience_hook or "the detail that makes this place worth saving"
    tone = mood or "cinematic and personal"
    include_clause = f" Include: {include}." if include else ""
    captions = [
        f"Hidden in plain sight: {story}.{include_clause}",
        f"A {tone} look at {story} — the kind of scene you save for later.{include_clause}",
        f"What makes this frame work is {hook}; the rest is the story around it.{include_clause}",
    ]
    hashtags = _hashtag_suggestions(story, location_text)
    context_questions = _context_questions(location_text, story_angle, mood, audience_hook, include, avoid)
    alt_text = _alt_text(selected_count, story, location_text)
    return GuidedDraftPackage(
        draft_id=draft.id,
        post_type_recommendation=post_type,
        post_type_rationale=_post_type_rationale(post_type, selected_count),
        caption_options=captions,
        hashtag_suggestions=hashtags,
        location_text=location_text,
        alt_text=alt_text,
        growth_rationale=(
            "Hook-first caption options, a clear lead image, and specific travel context are intended "
            "to increase saves, shares, profile visits, followers, and follower conversion."
        ),
        context_questions=context_questions,
    )


def accept_guided_draft_package(
    connection,
    package: GuidedDraftPackage,
    *,
    caption_index: int = 1,
) -> AcceptedGuidedDraftPackage:
    if not 1 <= caption_index <= len(package.caption_options):
        raise InvalidGuidedDraftPackage("Caption index must reference one generated caption option")
    caption = package.caption_options[caption_index - 1]
    updated = update_draft_content(
        connection,
        package.draft_id,
        caption=caption,
        hashtags=package.hashtag_suggestions,
        location_text=package.location_text,
        alt_text=package.alt_text,
    )
    if package.location_text is None:
        connection.execute(
            "update drafts set location_text = null, updated_at = current_timestamp where id = ?",
            (package.draft_id,),
        )
    if updated is None:
        raise DraftNotFound(f"Draft {package.draft_id} was not found.")
    upsert_guided_draft_package(
        connection,
        draft_id=package.draft_id,
        post_type_recommendation=package.post_type_recommendation,
        post_type_rationale=package.post_type_rationale,
        caption_options=package.caption_options,
        hashtag_suggestions=package.hashtag_suggestions,
        location_text=package.location_text,
        alt_text=package.alt_text,
        growth_rationale=package.growth_rationale,
        context_questions=package.context_questions,
        accepted_caption_index=caption_index,
        mark_accepted=True,
    )
    connection.commit()
    return AcceptedGuidedDraftPackage(
        draft_id=package.draft_id,
        caption=caption,
        hashtags=package.hashtag_suggestions,
        location_text=package.location_text,
        alt_text=package.alt_text,
        growth_rationale=package.growth_rationale,
    )


def _require_draft(connection, draft_id: int) -> DraftRecord:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Draft {draft_id} was not found.")
    return draft


def _recommend_post_type(draft: DraftRecord, selected_count: int) -> str:
    if draft.post_type == "single_image" or selected_count == 1:
        return "single_image"
    if draft.post_type == "reel":
        return "reel-planning-only"
    return "carousel"


def _post_type_rationale(post_type: str, selected_count: int) -> str:
    if post_type == "single_image":
        return "One selected photo is strongest as a focused single-image post."
    if post_type == "reel-planning-only":
        return "Reel intent is recorded locally, but live reel publishing is not validated yet."
    return f"{selected_count} selected photos can create a stronger carousel story arc than one standalone frame."


def _hashtag_suggestions(story: str, location_text: Optional[str]) -> list[str]:
    tags = ["#travelphotography", "#travelgram", "#sonyalpha", "#visualstorytelling"]
    if location_text:
        first_place = location_text.split(",")[0].strip().lower().replace(" ", "")
        if first_place:
            tags.insert(1, f"#{first_place}")
    if "food" in story.lower():
        tags.append("#foodtravel")
    if "night" in story.lower() or "neon" in story.lower():
        tags.append("#nightphotography")
    return tags


def _context_questions(
    location_text: Optional[str],
    story_angle: Optional[str],
    mood: Optional[str],
    audience_hook: Optional[str],
    include: Optional[str],
    avoid: Optional[str],
) -> list[str]:
    questions: list[str] = []
    if not location_text:
        questions.append("Confirm the exact location/place before publishing or tagging.")
        questions.append("Confirm the trip name or broader travel context if it should appear in the caption.")
        questions.append("Confirm the date or season if timing matters to the story.")
    if not story_angle:
        questions.append("What story, moment, or travel memory should this post center on?")
    if not mood:
        questions.append("Should the tone feel personal, cinematic, useful, funny, or aspirational?")
    if not audience_hook:
        questions.append("What should make someone stop scrolling in the first line?")
    if not include:
        questions.append("Any details, route tips, or observations Andrew wants included?")
    if not avoid:
        questions.append("Anything to avoid mentioning or implying?")
    return questions


def _alt_text(selected_count: int, story: str, location_text: Optional[str]) -> str:
    place = f" in {location_text}" if location_text else ""
    return f"Travel photo set of {selected_count} image(s){place}, centered on {story}."
