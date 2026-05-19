from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Mapping, Optional, Sequence

from PIL import Image

from post_relay.repository import (
    MediaInsightSnapshotRecord,
    PublishedPostSnapshotRecord,
    create_media_insight_snapshot,
    get_draft,
    get_draft_location_tag,
    get_latest_media_insight_snapshot,
    get_latest_published_attempt,
    get_published_post_snapshot_for_draft,
    list_published_post_snapshots,
    list_r2_staged_objects,
    upsert_published_post_snapshot,
)


DEFAULT_INSIGHT_METRICS = ["reach", "likes", "comments", "saved", "shares"]


class PublishedPostSnapshotNotReady(ValueError):
    """Raised when a draft has not reached a locally auditable published state."""


@dataclass(frozen=True)
class InsightsCollectionPlan:
    draft_id: int
    published_media_id: str
    read_only: bool
    endpoint: str
    metrics: list[str]

    def to_text(self) -> str:
        return "\n".join(
            [
                "Read-only Instagram insights collection plan",
                f"Draft ID: {self.draft_id}",
                f"Published media ID: {self.published_media_id}",
                f"Endpoint: GET {self.endpoint}",
                "Candidate metrics:",
                *[f"  - {metric}" for metric in self.metrics],
                "Safety: No network calls were made. This plan is read-only and separate from publishing.",
            ]
        )


@dataclass(frozen=True)
class FeedbackSummaryEntry:
    draft_id: int
    published_media_id: str
    post_type: str
    media_count: int
    caption_character_count: int
    hashtag_count: int
    aspect_ratio_class: str
    minutes_from_schedule: Optional[int]
    has_location_tag: bool
    insight_metrics: dict[str, int | float | str | None]
    insight_collected_at: Optional[str]


@dataclass(frozen=True)
class FeedbackSummary:
    entries: list[FeedbackSummaryEntry]
    sample_size: int


def record_published_post_snapshot(
    connection,
    draft_id: int,
    *,
    actual_published_at: Optional[str] = None,
) -> PublishedPostSnapshotRecord:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise PublishedPostSnapshotNotReady(f"Draft {draft_id} was not found")
    attempt = get_latest_published_attempt(connection, draft_id)
    if attempt is None:
        raise PublishedPostSnapshotNotReady(
            f"Draft {draft_id} does not have a successful published attempt to snapshot"
        )
    media_urls = attempt.image_urls or ([attempt.image_url] if attempt.image_url else [])
    if not media_urls:
        raise PublishedPostSnapshotNotReady(
            f"Draft {draft_id} published attempt has no media URLs to snapshot"
        )
    dimensions = _resolve_media_dimensions(connection, draft_id, media_urls)
    location_tag = get_draft_location_tag(connection, draft_id)
    snapshot = upsert_published_post_snapshot(
        connection,
        draft_id=draft_id,
        publish_attempt_id=attempt.id,
        published_media_id=attempt.published_media_id or "",
        post_type=attempt.post_type,
        final_caption=attempt.caption,
        media_urls=media_urls,
        media_dimensions=dimensions,
        scheduled_for=draft.scheduled_for,
        actual_published_at=actual_published_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        location_page_id=location_tag.page_id if location_tag and location_tag.status == "resolved" else None,
        location_name=location_tag.name if location_tag and location_tag.status == "resolved" else None,
    )
    connection.commit()
    return snapshot


def build_insights_collection_plan(connection, draft_id: int) -> InsightsCollectionPlan:
    snapshot = get_published_post_snapshot_for_draft(connection, draft_id)
    if snapshot is None:
        snapshot = record_published_post_snapshot(connection, draft_id)
    return InsightsCollectionPlan(
        draft_id=draft_id,
        published_media_id=snapshot.published_media_id,
        read_only=True,
        endpoint=f"/{snapshot.published_media_id}/insights",
        metrics=DEFAULT_INSIGHT_METRICS,
    )


def collect_and_store_media_insights(
    connection,
    draft_id: int,
    *,
    client,
    metrics: Sequence[str] = DEFAULT_INSIGHT_METRICS,
    collected_at: Optional[str] = None,
) -> MediaInsightSnapshotRecord:
    snapshot = get_published_post_snapshot_for_draft(connection, draft_id)
    if snapshot is None:
        snapshot = record_published_post_snapshot(connection, draft_id)
    payload = client.get_media_insights(snapshot.published_media_id, metrics=metrics)
    parsed_metrics = _parse_insight_metrics(payload)
    record = create_media_insight_snapshot(
        connection,
        draft_id=draft_id,
        published_post_snapshot_id=snapshot.id,
        published_media_id=snapshot.published_media_id,
        metrics=parsed_metrics,
        raw_payload=dict(payload),
        collected_at=collected_at or datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    connection.commit()
    return record


def render_media_insight_snapshot(record: MediaInsightSnapshotRecord) -> str:
    lines = [
        "Read-only Instagram insights fetched",
        f"Draft ID: {record.draft_id}",
        f"Published media ID: {record.published_media_id}",
        f"Collected at: {record.collected_at}",
        "Metrics:",
    ]
    for name in sorted(record.metrics):
        lines.append(f"  {name}: {record.metrics[name]}")
    lines.append("Publishing endpoints called: no")
    lines.append("Safety: Read-only insights were stored locally and did not mutate draft or publish state.")
    return "\n".join(lines)


def build_feedback_summary(
    connection,
    *,
    draft_id: Optional[int] = None,
    limit: int = 10,
) -> FeedbackSummary:
    if draft_id is not None:
        snapshot = get_published_post_snapshot_for_draft(connection, draft_id)
        snapshots = [snapshot] if snapshot is not None else []
    else:
        snapshots = list_published_post_snapshots(connection, limit=limit)
    entries = [_build_feedback_entry(connection, snapshot) for snapshot in snapshots]
    return FeedbackSummary(entries=entries, sample_size=len(entries))


def render_feedback_summary(summary: FeedbackSummary) -> str:
    lines = [
        "Recommendation feedback summary",
        f"Sample size: {summary.sample_size} published post(s)",
        "Caution: These suggestions are advisory, not causal, especially with small samples.",
    ]
    if not summary.entries:
        lines.extend(
            [
                "Observed signals: <none>",
                "Next-post suggestions:",
                "  - Publish and snapshot at least one reviewed post before drawing feedback.",
                "Safety: No Discord, R2, or Meta calls were made. No draft state was changed.",
            ]
        )
        return "\n".join(lines)

    for entry in summary.entries:
        lines.extend(
            [
                "",
                f"Draft {entry.draft_id} / media {entry.published_media_id}",
                "Observed signals:",
                f"  - Post type: {entry.post_type}",
                f"  - Media count: {entry.media_count}",
                f"  - Caption length: {entry.caption_character_count} characters",
                f"  - Hashtag count in final caption: {entry.hashtag_count}",
                f"  - Export/aspect ratio: {entry.aspect_ratio_class}",
                f"  - Schedule timing delta: {_format_timing_delta(entry.minutes_from_schedule)}",
                f"  - Resolved location tag: {'yes' if entry.has_location_tag else 'no'}",
            ]
        )
        if entry.insight_metrics:
            lines.append("  - Latest stored insights:")
            for name in sorted(entry.insight_metrics):
                lines.append(f"      {name}: {entry.insight_metrics[name]}")
            if entry.insight_collected_at:
                lines.append(f"      collected_at: {entry.insight_collected_at}")
        else:
            lines.append("  - No stored insight metrics yet; this is a payload-only summary.")
            lines.append(
                f"  - To collect later: analytics insights-fetch --draft-id {entry.draft_id} --db data/post_relay.sqlite"
            )
        lines.extend(
            [
                "Next-post suggestions:",
                *_suggestions_for_entry(entry),
            ]
        )
    lines.append("Safety: No Discord, R2, or Meta calls were made. No drafts, approvals, schedules, or publish records were changed.")
    return "\n".join(lines)


def render_insights_fetch_dry_run(plan: InsightsCollectionPlan) -> str:
    lines = [
        "Dry run only: read-only Instagram insights fetch",
        f"Draft ID: {plan.draft_id}",
        f"Published media ID: {plan.published_media_id}",
        f"Endpoint: GET {plan.endpoint}",
        "Metrics:",
        *[f"  - {metric}" for metric in plan.metrics],
        "No Meta network calls were made.",
        "Rerun with --execute to collect and store these read-only metrics.",
    ]
    return "\n".join(lines)


def render_insights_fetch_error(error: Exception, *, token: Optional[str] = None) -> str:
    message = str(error)
    if token:
        message = message.replace(token, "<redacted>")
    return f"Read-only Instagram insights fetch failed: {message}"


def render_published_post_snapshot(snapshot: PublishedPostSnapshotRecord) -> str:
    lines = [
        "Post-publish analytics snapshot",
        f"Draft ID: {snapshot.draft_id}",
        f"Published media ID: {snapshot.published_media_id}",
        f"Post type: {snapshot.post_type}",
        f"Scheduled for: {snapshot.scheduled_for or '<not scheduled>'}",
        f"Actual published at: {snapshot.actual_published_at}",
        "Final caption:",
        snapshot.final_caption or "<empty>",
        "Media URLs:",
    ]
    lines.extend(f"  {index}. {url}" for index, url in enumerate(snapshot.media_urls, start=1))
    lines.append("Media dimensions:")
    for index, dimensions in enumerate(snapshot.media_dimensions, start=1):
        width = dimensions.get("width")
        height = dimensions.get("height")
        if width and height:
            lines.append(f"  {index}. {width}x{height}")
        else:
            lines.append(f"  {index}. <unknown>")
    if snapshot.location_page_id:
        lines.append(
            f"Resolved location tag: location_id={snapshot.location_page_id} ({snapshot.location_name})"
        )
    else:
        lines.append("Resolved location tag: <none>")
    lines.append("Safety: No network calls were made. Snapshot uses local publish attempt and staged media records only.")
    return "\n".join(lines)


def _build_feedback_entry(connection, snapshot: PublishedPostSnapshotRecord) -> FeedbackSummaryEntry:
    insight = get_latest_media_insight_snapshot(connection, snapshot.draft_id)
    return FeedbackSummaryEntry(
        draft_id=snapshot.draft_id,
        published_media_id=snapshot.published_media_id,
        post_type=snapshot.post_type,
        media_count=len(snapshot.media_urls),
        caption_character_count=len(snapshot.final_caption or ""),
        hashtag_count=len(re.findall(r"(?<!\w)#\w+", snapshot.final_caption or "")),
        aspect_ratio_class=_classify_aspect_ratios(snapshot.media_dimensions),
        minutes_from_schedule=_minutes_from_schedule(snapshot.scheduled_for, snapshot.actual_published_at),
        has_location_tag=bool(snapshot.location_page_id),
        insight_metrics=dict(insight.metrics) if insight else {},
        insight_collected_at=insight.collected_at if insight else None,
    )


def _classify_aspect_ratios(dimensions: Sequence[dict[str, Optional[int]]]) -> str:
    ratios = [
        item["width"] / item["height"]
        for item in dimensions
        if item.get("width") and item.get("height")
    ]
    if not ratios:
        return "unknown"
    average = sum(ratios) / len(ratios)
    if abs(average - 0.8) <= 0.03:
        return "portrait_4x5"
    if abs(average - 1.0) <= 0.03:
        return "square"
    if average < 0.8:
        return "portrait_tall"
    if average > 1.05:
        return "landscape"
    return "mixed_or_custom"


def _minutes_from_schedule(scheduled_for: Optional[str], actual_published_at: str) -> Optional[int]:
    if not scheduled_for:
        return None
    try:
        scheduled = datetime.fromisoformat(scheduled_for)
        actual = datetime.fromisoformat(actual_published_at)
    except ValueError:
        return None
    return round((actual - scheduled).total_seconds() / 60)


def _format_timing_delta(minutes: Optional[int]) -> str:
    if minutes is None:
        return "<not available>"
    if minutes == 0:
        return "on schedule"
    if minutes > 0:
        return f"{minutes} minute(s) after scheduled time"
    return f"{abs(minutes)} minute(s) before scheduled time"


def _suggestions_for_entry(entry: FeedbackSummaryEntry) -> list[str]:
    suggestions = [
        "  - Keep comparing hook/caption length, media count, timing, location tags, and export format as more posts collect insights."
    ]
    if entry.media_count > 1:
        suggestions.append("  - Review whether the carousel count and lead image correlate with stronger reach/saves over future posts.")
    if entry.aspect_ratio_class != "portrait_4x5":
        suggestions.append("  - Consider a 4:5 feed export when the source crop supports it, then compare retention/reach later.")
    if not entry.has_location_tag:
        suggestions.append("  - If there is a real place tag, test a reviewed Meta location_id on a future approved draft.")
    if not entry.insight_metrics:
        suggestions.append("  - Collect read-only insights after Meta has populated them before changing recommendations.")
    return suggestions


def _resolve_media_dimensions(connection, draft_id: int, media_urls: list[str]) -> list[dict[str, Optional[int]]]:
    staged_by_url = {
        record.public_url: record
        for record in list_r2_staged_objects(connection, draft_id, status="uploaded")
        if record.kind == "draft_media"
    }
    dimensions: list[dict[str, Optional[int]]] = []
    for media_url in media_urls:
        record = staged_by_url.get(media_url)
        if record is None:
            dimensions.append({"width": None, "height": None})
            continue
        dimensions.append(_image_dimensions(Path(record.source_path)))
    return dimensions


def _parse_insight_metrics(payload: Mapping) -> dict[str, int | float | str | None]:
    metrics: dict[str, int | float | str | None] = {}
    for item in payload.get("data") or []:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        if not name:
            continue
        values = item.get("values") or []
        value = None
        if values and isinstance(values[-1], Mapping):
            value = values[-1].get("value")
        metrics[str(name)] = value
    return metrics


def _image_dimensions(path: Path) -> dict[str, Optional[int]]:
    if not path.exists():
        return {"width": None, "height": None}
    try:
        with Image.open(path) as image:
            return {"width": int(image.width), "height": int(image.height)}
    except Exception:
        return {"width": None, "height": None}
