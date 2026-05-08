from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class InstagramCapability:
    field_name: str
    status: str
    publish_note: str
    review_note: str


@dataclass(frozen=True)
class ReviewOnlyMetadata:
    field_name: str
    value: Any
    capability: InstagramCapability


_CAPABILITIES: dict[str, InstagramCapability] = {
    "media_urls": InstagramCapability(
        field_name="media_urls",
        status="publishable",
        publish_note="Public HTTPS image URLs are sent to Meta media container endpoints.",
        review_note="Required for single-image and carousel publish validation.",
    ),
    "carousel_children": InstagramCapability(
        field_name="carousel_children",
        status="publishable",
        publish_note="Ordered carousel child containers are sent to the parent carousel container.",
        review_note="Order must match Andrew's approved draft media order.",
    ),
    "caption": InstagramCapability(
        field_name="caption",
        status="publishable",
        publish_note="Approved caption text is sent to Meta media container creation.",
        review_note="Caption is canonical draft content after approval.",
    ),
    "hashtags_in_caption": InstagramCapability(
        field_name="hashtags_in_caption",
        status="publishable",
        publish_note="Hashtags are publishable only as part of the caption text.",
        review_note="Keep hashtag recommendations concise and human-reviewed.",
    ),
    "alt_text": InstagramCapability(
        field_name="alt_text",
        status="review_only",
        publish_note="Alt text is not sent by Post Relay's validated Meta Graph publish path.",
        review_note="Useful local accessibility metadata for Andrew's review/manual use.",
    ),
    "growth_rationale": InstagramCapability(
        field_name="growth_rationale",
        status="review_only",
        publish_note="Growth rationale is never sent to Instagram publish endpoints.",
        review_note="Audit note explaining recommendation quality and follower-growth intent.",
    ),
    "schedule_rationale": InstagramCapability(
        field_name="schedule_rationale",
        status="review_only",
        publish_note="Scheduling rationale is local queue guidance, not Instagram metadata.",
        review_note="Useful for Discord review and approval context.",
    ),
    "location_tag": InstagramCapability(
        field_name="location_tag",
        status="needs_validation",
        publish_note="Location tags are not sent until official Meta Graph support is validated for this account.",
        review_note="Show as confirmed/review-only location text for manual use.",
    ),
    "collaborators": InstagramCapability(
        field_name="collaborators",
        status="needs_validation",
        publish_note="Collaborators are not sent until official Meta Graph support is validated.",
        review_note="Keep collaborator ideas as manual review notes.",
    ),
    "product_tags": InstagramCapability(
        field_name="product_tags",
        status="needs_validation",
        publish_note="Product tags are outside the validated v1 publish path.",
        review_note="Do not promise product tagging automation yet.",
    ),
    "reel_fields": InstagramCapability(
        field_name="reel_fields",
        status="needs_validation",
        publish_note="Reel-specific publishing is not validated in the feed/carousel v1 path.",
        review_note="Reel intent may be planned locally only.",
    ),
    "story_fields": InstagramCapability(
        field_name="story_fields",
        status="unsupported_v1",
        publish_note="Stories remain manual and are not sent by Post Relay v1.",
        review_note="Show story ideas as manual notes only.",
    ),
    "music": InstagramCapability(
        field_name="music",
        status="unsupported_v1",
        publish_note="Music is not sent by the validated Instagram Graph publish path.",
        review_note="Keep music ideas as manual/reel planning notes only.",
    ),
}

_PUBLISHABLE_STATUSES = {"publishable"}


def get_instagram_publish_capability(field_name: str) -> InstagramCapability:
    return _CAPABILITIES.get(
        field_name,
        InstagramCapability(
            field_name=field_name,
            status="unsupported_v1",
            publish_note="Unknown or future metadata is not sent by Post Relay v1.",
            review_note="Review locally before adding any official capability validation.",
        ),
    )


def filter_publishable_metadata(metadata: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, ReviewOnlyMetadata]]:
    publishable: dict[str, Any] = {}
    review_only: dict[str, ReviewOnlyMetadata] = {}
    for field_name, value in metadata.items():
        capability = get_instagram_publish_capability(field_name)
        if capability.status in _PUBLISHABLE_STATUSES:
            publishable[field_name] = value
        else:
            review_only[field_name] = ReviewOnlyMetadata(
                field_name=field_name,
                value=value,
                capability=capability,
            )
    return publishable, review_only


def capability_matrix_text() -> str:
    lines = [
        "Instagram Capability Matrix",
        "Publishable fields are the only fields Post Relay may send to Meta publish endpoints.",
        "Everything else is review/local only until official capability validation is added.",
    ]
    for field_name in sorted(_CAPABILITIES):
        capability = _CAPABILITIES[field_name]
        lines.append(f"- {field_name}: {capability.status} — {capability.publish_note}")
        if capability.status != "publishable":
            lines.append(f"  review/local only: {capability.review_note}")
    return "\n".join(lines)
