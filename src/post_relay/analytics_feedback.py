from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping, Optional, Sequence

from PIL import Image

from post_relay.repository import (
    MediaInsightSnapshotRecord,
    PublishedPostSnapshotRecord,
    create_media_insight_snapshot,
    get_draft,
    get_draft_location_tag,
    get_latest_published_attempt,
    get_published_post_snapshot_for_draft,
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
