from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from post_relay.config import R2StagingConfig
from post_relay.publish_metadata import compose_final_meta_caption, parse_hashtags
from post_relay.publishing import DraftNotFound, UnsupportedPublishDraft, resolve_staged_r2_publish_image_urls
from post_relay.repository import get_draft, get_guided_draft_package


@dataclass(frozen=True)
class FinalPublishPreview:
    draft_id: int
    post_type: str
    scheduled_for: Optional[str]
    image_urls: list[str]
    meta_caption: str
    hashtags_embedded_in_caption: list[str]
    location_handling: str
    location_text: Optional[str]
    review_only_fields: dict[str, str]

    def to_text(self) -> str:
        lines = [
            "Final publish preview",
            f"Draft ID: {self.draft_id}",
            f"Post type: {self.post_type}",
            f"Scheduled for: {self.scheduled_for or '<not scheduled>'}",
            "Selected media URLs in Meta order:",
        ]
        if self.image_urls:
            lines.extend(f"  {index}. {url}" for index, url in enumerate(self.image_urls, start=1))
        else:
            lines.append("  <none>")
        lines.extend(
            [
                "Exact Meta-bound caption:",
                self.meta_caption or "<empty>",
                "Publishable fields sent to Meta:",
                "  - media_urls",
                "  - caption",
                "  - hashtags embedded in caption" if self.hashtags_embedded_in_caption else "  - hashtags embedded in caption: <none>",
                "Hashtags embedded in caption: " + (" ".join(self.hashtags_embedded_in_caption) or "<none>"),
                f"Location handling: {self.location_handling}",
            ]
        )
        if self.location_text:
            lines.append(f"Location text: {self.location_text} (local/review-only; not sent as a Meta location tag)")
        else:
            lines.append("Location text: <none>")
        lines.append("Review-only fields:")
        if self.review_only_fields:
            for field_name in sorted(self.review_only_fields):
                lines.append(f"  - {field_name}: {self.review_only_fields[field_name]}")
        else:
            lines.append("  - <none>")
        lines.extend(
            [
                "No Discord network calls were made.",
                "No R2 upload or cleanup calls were made.",
                "No Meta publishing endpoints were called.",
            ]
        )
        return "\n".join(lines)


def build_final_publish_preview(
    connection,
    draft_id: int,
    *,
    r2_config: R2StagingConfig,
) -> FinalPublishPreview:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Draft {draft_id} was not found")
    image_urls = resolve_staged_r2_publish_image_urls(connection, draft_id, r2_config)
    hashtags = parse_hashtags(draft.hashtags_json)
    review_only_fields: dict[str, str] = {}
    if draft.alt_text:
        review_only_fields["alt_text"] = draft.alt_text
    if draft.location_text:
        review_only_fields["location_text"] = draft.location_text
    guided_package = get_guided_draft_package(connection, draft_id)
    if guided_package and guided_package.growth_rationale:
        review_only_fields["growth_rationale"] = guided_package.growth_rationale
    location_handling = "local/review-only" if draft.location_text else "local/review-only (unconfirmed)"
    return FinalPublishPreview(
        draft_id=draft.id,
        post_type=draft.post_type,
        scheduled_for=draft.scheduled_for,
        image_urls=[_sanitize_url(url) for url in image_urls],
        meta_caption=compose_final_meta_caption(draft),
        hashtags_embedded_in_caption=hashtags,
        location_handling=location_handling,
        location_text=draft.location_text,
        review_only_fields=review_only_fields,
    )


def _sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise UnsupportedPublishDraft("Final publish preview requires public https staged media URLs")
    sanitized_query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if any(secretish in key.lower() for secretish in ("token", "secret", "signature", "sig", "key")):
            sanitized_query_pairs.append((key, "<redacted>"))
        else:
            sanitized_query_pairs.append((key, value))
    sanitized_query = "&".join(f"{key}={value}" if value else key for key, value in sanitized_query_pairs)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, sanitized_query, parts.fragment))
