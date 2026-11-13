from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Sequence
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from post_relay.config import R2StagingConfig
from post_relay.analytics_feedback import record_published_post_snapshot
from post_relay.meta_graph import MetaGraphClient, MetaGraphRequestError, redact_secrets
from post_relay.publish_metadata import compose_final_meta_caption
from post_relay.repository import (
    create_publish_attempt,
    get_draft,
    get_draft_location_tag,
    list_candidate_group_photo_paths,
    list_publish_attempts,
    list_r2_staged_objects,
    update_draft_status,
    update_publish_attempt,
)
from post_relay.state import DraftState, transition_draft_state


DEFAULT_CONTAINER_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_CONTAINER_POLL_TIMEOUT_SECONDS = 180.0

#: Meta container states that can still become ``FINISHED`` (empty = not reported yet).
NON_TERMINAL_CONTAINER_STATUS_CODES = frozenset({"IN_PROGRESS", ""})
#: Meta container states that can never become ``FINISHED``.
ERROR_CONTAINER_STATUS_CODES = frozenset({"ERROR", "EXPIRED", "PUBLISHED"})
#: Publish-attempt states whose recorded container may be reused by a later run.
RESUMABLE_ATTEMPT_STATUSES = frozenset(
    {"container_created", "container_finished", "container_timeout"}
)


class DraftNotFound(ValueError):
    """Raised when a publish validation draft id does not exist."""


class DraftNotReadyForImagePublish(ValueError):
    """Raised when a draft has not received explicit publish approval."""


class UnsupportedPublishDraft(ValueError):
    """Raised when a draft cannot use the controlled publish validation path."""

class PublishValidationError(RuntimeError):

    """Raised when the controlled Meta publish validation fails."""


class PublishContainerTimeout(PublishValidationError):
    """Raised when a media container never reached a terminal state in time.

    The container id is preserved on the publish attempt so a later run resumes
    the existing container instead of creating a duplicate one.
    """

    def __init__(self, message: str, *, container_id: str, status_code: str = "") -> None:
        super().__init__(message)
        self.container_id = container_id
        self.status_code = status_code


@dataclass(frozen=True)
class SingleImagePublishValidationResult:
    draft_id: int
    status: str
    image_url: str
    caption: str
    container_id: Optional[str] = None
    status_code: Optional[str] = None
    published_media_id: Optional[str] = None
    status_message: Optional[str] = None

    def to_text(self) -> str:
        lines = [
            "Single-image publish validation",
            f"Post ID: {self.draft_id}",
            f"Status: {self.status}",
            f"Image URL: {self.image_url}",
            f"Caption: {self.caption}",
            f"Container ID: {self.container_id or '<not created>'}",
            f"Container status: {self.status_code or '<not checked>'}",
            f"Published media ID: {self.published_media_id or '<not published>'}",
        ]
        if self.status_message:
            lines.append(f"Status message: {self.status_message}")
        return "\n".join(lines)


@dataclass(frozen=True)
class CarouselPublishValidationResult:
    draft_id: int
    status: str
    image_urls: list[str]
    caption: str
    child_container_ids: list[str]
    container_id: Optional[str] = None
    status_code: Optional[str] = None
    published_media_id: Optional[str] = None
    status_message: Optional[str] = None

    def to_text(self) -> str:
        lines = [
            "Carousel publish validation",
            f"Post ID: {self.draft_id}",
            f"Status: {self.status}",
            "Image URLs:",
        ]
        lines.extend(f"  - {image_url}" for image_url in self.image_urls)
        lines.extend([f"Caption: {self.caption}", "Child container IDs:"])
        if self.child_container_ids:
            lines.extend(f"  - {container_id}" for container_id in self.child_container_ids)
        else:
            lines.append("  - <not created>")
        lines.extend(
            [
                f"Carousel container ID: {self.container_id or '<not created>'}",
                f"Carousel container status: {self.status_code or '<not checked>'}",
                f"Published media ID: {self.published_media_id or '<not published>'}",
            ]
        )
        if self.status_message:
            lines.append(f"Status message: {self.status_message}")
        return "\n".join(lines)


def resolve_staged_r2_publish_image_urls(
    connection,
    draft_id: int,
    config: R2StagingConfig,
) -> list[str]:
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post {draft_id} was not found")
    selected_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    records = [
        record
        for record in list_r2_staged_objects(connection, draft_id, status="uploaded")
        if record.kind == "draft_media"
    ]
    normalized_prefix = _normalize_prefix(config.prefix)
    expected_prefix = f"{normalized_prefix}/"
    expected_public_prefix = f"{config.public_base_url.rstrip('/')}/{normalized_prefix}/"
    by_source_path = {}
    by_media_order = {}
    for record in records:
        if record.bucket != config.bucket:
            continue
        if not record.object_key.startswith(expected_prefix):
            continue
        if not record.public_url.startswith(expected_public_prefix):
            continue
        by_source_path[record.source_path] = record
        media_order = _extract_staged_media_order(record.object_key)
        if media_order is not None:
            by_media_order[media_order] = record
    resolved_urls: list[str] = []
    missing_paths: list[str] = []
    for media_order, source_path in enumerate(selected_paths, start=1):
        record = by_source_path.get(source_path) or by_media_order.get(media_order)
        if record is None:
            missing_paths.append(source_path)
            continue
        _sanitize_url(record.public_url)
        resolved_urls.append(record.public_url)
    if missing_paths:
        raise UnsupportedPublishDraft(
            "Publish from staged R2 requires uploaded staged R2 media for each selected post image: "
            + ", ".join(missing_paths)
        )
    return resolved_urls


def _extract_staged_media_order(object_key: str) -> Optional[int]:
    filename = object_key.rsplit("/", 1)[-1]
    match = re.match(r"^(\d+)-", filename)
    if not match:
        return None
    return int(match.group(1))


def prepare_single_image_publish_validation(
    connection,
    draft_id: int,
    *,
    image_url: str,
) -> SingleImagePublishValidationResult:
    draft = _validate_single_image_ready_draft(connection, draft_id)
    sanitized_image_url = _sanitize_url(image_url)
    caption = compose_final_meta_caption(draft)
    create_publish_attempt(
        connection,
        draft_id=draft.id,
        post_type=draft.post_type,
        image_url=sanitized_image_url,
        caption=caption,
        status="planned",
    )
    connection.commit()
    return SingleImagePublishValidationResult(
        draft_id=draft.id,
        status="planned",
        image_url=sanitized_image_url,
        caption=caption,
    )


def execute_single_image_publish_validation(
    connection,
    draft_id: int,
    *,
    image_url: str,
    client: MetaGraphClient,
    now: Optional[str] = None,
    publish_now: bool = False,
    poll_interval_seconds: float = DEFAULT_CONTAINER_POLL_INTERVAL_SECONDS,
    poll_timeout_seconds: float = DEFAULT_CONTAINER_POLL_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> SingleImagePublishValidationResult:
    _restore_failed_draft_for_container_resume(
        connection,
        draft_id,
        image_url=_sanitize_url(image_url),
    )
    draft = _validate_single_image_ready_draft(connection, draft_id)
    _enforce_publish_schedule(draft, now=now, publish_now=publish_now)
    if not client.config.instagram_account_id:
        raise PublishValidationError("POST_RELAY_INSTAGRAM_ACCOUNT_ID is required for publishing")

    sanitized_image_url = _sanitize_url(image_url)
    caption = compose_final_meta_caption(draft)
    location_id = _resolved_location_id(connection, draft.id)
    resumable = _find_resumable_attempt(
        connection,
        draft,
        caption=caption,
        image_url=sanitized_image_url,
    )
    container_id = resumable.container_id if resumable is not None else ""
    if resumable is not None:
        attempt = update_publish_attempt(
            connection,
            resumable.id,
            status="started",
            container_id=container_id,
        )
    else:
        attempt = create_publish_attempt(
            connection,
            draft_id=draft.id,
            post_type=draft.post_type,
            image_url=sanitized_image_url,
            caption=caption,
            status="started",
        )
    connection.commit()

    update_draft_status(
        connection,
        draft.id,
        transition_draft_state(DraftState(draft.status), DraftState.POSTING).value,
    )
    connection.commit()

    status_code = ""
    try:
        if not container_id:
            container_payload = client.create_image_container(
                client.config.instagram_account_id,
                image_url=image_url,
                caption=caption,
                location_id=location_id,
            )
            container_id = str(container_payload.get("id") or "")
            if not container_id:
                raise PublishValidationError("Meta Graph did not return a media container id")
            update_publish_attempt(
                connection,
                attempt.id,
                status="container_created",
                container_id=container_id,
            )
            connection.commit()

        status_code = _await_container_finished(
            client,
            container_id,
            label="media",
            poll_interval_seconds=poll_interval_seconds,
            poll_timeout_seconds=poll_timeout_seconds,
            sleep=sleep,
            monotonic=monotonic,
        )
        update_publish_attempt(
            connection,
            attempt.id,
            status="container_finished",
            container_id=container_id,
            status_code=status_code,
        )
        connection.commit()

        publish_payload = client.publish_media(
            client.config.instagram_account_id,
            creation_id=container_id,
        )
        published_media_id = str(publish_payload.get("id") or "")
        if not published_media_id:
            raise PublishValidationError("Meta Graph did not return a published media id")

        update_publish_attempt(
            connection,
            attempt.id,
            status="published",
            container_id=container_id,
            published_media_id=published_media_id,
            status_code=status_code,
        )
        update_draft_status(connection, draft.id, DraftState.POSTED.value)
        connection.commit()
        record_published_post_snapshot(connection, draft.id)
        return SingleImagePublishValidationResult(
            draft_id=draft.id,
            status="published",
            image_url=sanitized_image_url,
            caption=caption,
            container_id=container_id,
            status_code=status_code,
            published_media_id=published_media_id,
        )
    except Exception as exc:
        safe_message = redact_secrets(str(exc), [client.config.access_token, image_url])
        last_status_code = (
            exc.status_code if isinstance(exc, PublishContainerTimeout) else status_code
        )
        update_publish_attempt(
            connection,
            attempt.id,
            status="container_timeout" if isinstance(exc, PublishContainerTimeout) else "failed",
            container_id=container_id or None,
            status_code=last_status_code or None,
            status_message=safe_message,
        )
        update_draft_status(connection, draft.id, DraftState.FAILED.value)
        connection.commit()
        if isinstance(exc, (MetaGraphRequestError, PublishValidationError)):
            if isinstance(exc, PublishContainerTimeout):
                raise PublishContainerTimeout(
                    safe_message,
                    container_id=exc.container_id,
                    status_code=exc.status_code,
                ) from exc
            raise PublishValidationError(safe_message) from exc
        raise


def prepare_carousel_publish_validation(
    connection,
    draft_id: int,
    *,
    image_urls: Sequence[str],
) -> CarouselPublishValidationResult:
    draft = _validate_carousel_ready_draft(connection, draft_id, image_urls)
    sanitized_image_urls = [_sanitize_url(image_url) for image_url in image_urls]
    caption = compose_final_meta_caption(draft)
    create_publish_attempt(
        connection,
        draft_id=draft.id,
        post_type=draft.post_type,
        image_url=sanitized_image_urls[0] if sanitized_image_urls else None,
        image_urls=sanitized_image_urls,
        child_container_ids=[],
        caption=caption,
        status="planned",
    )
    connection.commit()
    return CarouselPublishValidationResult(
        draft_id=draft.id,
        status="planned",
        image_urls=sanitized_image_urls,
        caption=caption,
        child_container_ids=[],
    )


def execute_carousel_publish_validation(
    connection,
    draft_id: int,
    *,
    image_urls: Sequence[str],
    client: MetaGraphClient,
    now: Optional[str] = None,
    publish_now: bool = False,
    poll_interval_seconds: float = DEFAULT_CONTAINER_POLL_INTERVAL_SECONDS,
    poll_timeout_seconds: float = DEFAULT_CONTAINER_POLL_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> CarouselPublishValidationResult:
    _restore_failed_draft_for_container_resume(
        connection,
        draft_id,
        image_urls=[_sanitize_url(url) for url in image_urls],
    )
    draft = _validate_carousel_ready_draft(connection, draft_id, image_urls)
    _enforce_publish_schedule(draft, now=now, publish_now=publish_now)
    if not client.config.instagram_account_id:
        raise PublishValidationError("POST_RELAY_INSTAGRAM_ACCOUNT_ID is required for publishing")

    sanitized_image_urls = [_sanitize_url(image_url) for image_url in image_urls]
    caption = compose_final_meta_caption(draft)
    location_id = _resolved_location_id(connection, draft.id)
    resumable = _find_resumable_attempt(
        connection,
        draft,
        caption=caption,
        image_urls=sanitized_image_urls,
    )
    if resumable is not None:
        attempt = update_publish_attempt(
            connection,
            resumable.id,
            status="started",
            container_id=resumable.container_id,
        )
    else:
        attempt = create_publish_attempt(
            connection,
            draft_id=draft.id,
            post_type=draft.post_type,
            image_url=sanitized_image_urls[0] if sanitized_image_urls else None,
            image_urls=sanitized_image_urls,
            child_container_ids=[],
            caption=caption,
            status="started",
        )
    connection.commit()

    update_draft_status(
        connection,
        draft.id,
        transition_draft_state(DraftState(draft.status), DraftState.POSTING).value,
    )
    connection.commit()

    child_container_ids: list[str] = list(resumable.child_container_ids) if resumable else []
    carousel_container_id = resumable.container_id if resumable else ""
    status_code = ""
    try:
        if not carousel_container_id:
            child_container_ids = []
            for image_url in image_urls:
                child_payload = client.create_carousel_item_container(
                    client.config.instagram_account_id,
                    image_url=image_url,
                )
                child_container_id = str(child_payload.get("id") or "")
                if not child_container_id:
                    raise PublishValidationError(
                        "Meta Graph did not return a carousel child container id"
                    )
                child_container_ids.append(child_container_id)
                update_publish_attempt(
                    connection,
                    attempt.id,
                    status="child_container_created",
                    child_container_ids=child_container_ids,
                )
                connection.commit()

            carousel_payload = client.create_carousel_container(
                client.config.instagram_account_id,
                child_container_ids=child_container_ids,
                caption=caption,
                location_id=location_id,
            )
            carousel_container_id = str(carousel_payload.get("id") or "")
            if not carousel_container_id:
                raise PublishValidationError("Meta Graph did not return a carousel container id")
            update_publish_attempt(
                connection,
                attempt.id,
                status="container_created",
                container_id=carousel_container_id,
                child_container_ids=child_container_ids,
            )
            connection.commit()

        status_code = _await_container_finished(
            client,
            carousel_container_id,
            label="carousel",
            poll_interval_seconds=poll_interval_seconds,
            poll_timeout_seconds=poll_timeout_seconds,
            sleep=sleep,
            monotonic=monotonic,
        )
        update_publish_attempt(
            connection,
            attempt.id,
            status="container_finished",
            container_id=carousel_container_id,
            child_container_ids=child_container_ids,
            status_code=status_code,
        )
        connection.commit()

        publish_payload = client.publish_media(
            client.config.instagram_account_id,
            creation_id=carousel_container_id,
        )
        published_media_id = str(publish_payload.get("id") or "")
        if not published_media_id:
            raise PublishValidationError("Meta Graph did not return a published media id")

        update_publish_attempt(
            connection,
            attempt.id,
            status="published",
            container_id=carousel_container_id,
            child_container_ids=child_container_ids,
            published_media_id=published_media_id,
            status_code=status_code,
        )
        update_draft_status(connection, draft.id, DraftState.POSTED.value)
        connection.commit()
        record_published_post_snapshot(connection, draft.id)
        return CarouselPublishValidationResult(
            draft_id=draft.id,
            status="published",
            image_urls=sanitized_image_urls,
            caption=caption,
            child_container_ids=child_container_ids,
            container_id=carousel_container_id,
            status_code=status_code,
            published_media_id=published_media_id,
        )
    except Exception as exc:
        safe_message = redact_secrets(str(exc), [client.config.access_token, *image_urls])
        last_status_code = (
            exc.status_code if isinstance(exc, PublishContainerTimeout) else status_code
        )
        update_publish_attempt(
            connection,
            attempt.id,
            status="container_timeout" if isinstance(exc, PublishContainerTimeout) else "failed",
            container_id=carousel_container_id or None,
            child_container_ids=child_container_ids,
            status_code=last_status_code or None,
            status_message=safe_message,
        )
        update_draft_status(connection, draft.id, DraftState.FAILED.value)
        connection.commit()
        if isinstance(exc, (MetaGraphRequestError, PublishValidationError)):
            if isinstance(exc, PublishContainerTimeout):
                raise PublishContainerTimeout(
                    safe_message,
                    container_id=exc.container_id,
                    status_code=exc.status_code,
                ) from exc
            raise PublishValidationError(safe_message) from exc
        raise


def _resolved_location_id(connection, draft_id: int) -> Optional[str]:
    tag = get_draft_location_tag(connection, draft_id)
    if tag is None or tag.status != "resolved":
        return None
    return tag.page_id


def _await_container_finished(
    client: MetaGraphClient,
    container_id: str,
    *,
    label: str,
    poll_interval_seconds: float,
    poll_timeout_seconds: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> str:
    """Poll a Meta media container until it is FINISHED, errored, or times out."""
    deadline = monotonic() + max(poll_timeout_seconds, 0.0)
    status_code = ""
    while True:
        status_payload = client.get_media_container_status(container_id)
        status_code = str(status_payload.get("status_code") or "")
        if status_code == "FINISHED":
            return status_code
        if status_code in ERROR_CONTAINER_STATUS_CODES:
            raise PublishValidationError(
                f"Meta {label} container {container_id} failed with status {status_code}"
            )
        if status_code not in NON_TERMINAL_CONTAINER_STATUS_CODES:
            raise PublishValidationError(
                f"Meta {label} container {container_id} returned an unknown status: {status_code}"
            )
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise PublishContainerTimeout(
                f"Meta {label} container {container_id} did not reach FINISHED within "
                f"{poll_timeout_seconds:g}s (last status: {status_code or '<unknown>'}). "
                "The container id is recorded on the publish attempt; rerun to resume it "
                "instead of creating a duplicate container.",
                container_id=container_id,
                status_code=status_code,
            )
        sleep(min(poll_interval_seconds, remaining))


def _find_resumable_attempt(
    connection,
    draft,
    *,
    caption: str,
    image_url: Optional[str] = None,
    image_urls: Optional[Sequence[str]] = None,
):
    """Return the newest publish attempt whose container can be safely resumed.

    A container is only resumable when it belongs to the same post, post type,
    caption, and image URL set, has not been published, and is not in an error
    state. Anything else is treated as a fresh publish.
    """
    for attempt in reversed(list_publish_attempts(connection, draft.id)):
        if not attempt.container_id:
            continue
        if attempt.published_media_id:
            continue
        if attempt.post_type != draft.post_type:
            continue
        if attempt.status not in RESUMABLE_ATTEMPT_STATUSES:
            continue
        if (attempt.status_code or "") in ERROR_CONTAINER_STATUS_CODES:
            continue
        if (attempt.caption or "") != caption:
            continue
        if image_urls is not None:
            if list(attempt.image_urls) != list(image_urls):
                continue
        elif (attempt.image_url or "") != (image_url or ""):
            continue
        return attempt
    return None


def _restore_failed_draft_for_container_resume(
    connection,
    draft_id: int,
    *,
    image_url: Optional[str] = None,
    image_urls: Optional[Sequence[str]] = None,
) -> None:
    """Return a timed-out publish to the queue so its container can be resumed.

    A container poll that times out leaves the post in ``failed``. When the
    recorded container still matches the current caption and image URLs, the
    next run may resume it; anything else (material edits, errored containers)
    stays failed and needs an explicit decision.
    """
    draft = get_draft(connection, draft_id)
    if draft is None or draft.status != DraftState.FAILED.value:
        return
    caption = compose_final_meta_caption(draft)
    resumable = _find_resumable_attempt(
        connection,
        draft,
        caption=caption,
        image_url=image_url,
        image_urls=image_urls,
    )
    if resumable is None or resumable.status != "container_timeout":
        return
    update_draft_status(
        connection,
        draft.id,
        transition_draft_state(DraftState.FAILED, DraftState.READY_TO_PUBLISH).value,
    )
    connection.commit()


def _enforce_publish_schedule(draft, *, now: Optional[str], publish_now: bool) -> None:
    if publish_now or not draft.scheduled_for:
        return
    scheduled_at = _parse_publish_timestamp(
        draft.scheduled_for,
        label="scheduled_for",
    )
    current_time = _parse_publish_timestamp(now, label="current time") if now else datetime.now().astimezone()
    if current_time < scheduled_at:
        raise PublishValidationError(
            f"Post {draft.id} is scheduled for {draft.scheduled_for}; refusing to publish before the scheduled time. "
            f"Current time: {_format_timestamp(current_time)}. "
            "Next safe action: wait until the scheduled time and rerun the command, or use --publish-now only with explicit active-session authorization."
        )


def _parse_publish_timestamp(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise PublishValidationError(f"Invalid {label} timestamp: {value}") from error
    if parsed.tzinfo is None:
        raise PublishValidationError(f"Invalid {label} timestamp: {value}; timezone offset is required")
    return parsed


def _format_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _validate_single_image_ready_draft(connection, draft_id: int):
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post {draft_id} was not found")
    if draft.status != DraftState.READY_TO_PUBLISH.value:
        raise DraftNotReadyForImagePublish(
            f"Post {draft_id} must be {DraftState.READY_TO_PUBLISH.value} before controlled publishing"
        )
    if draft.post_type != "single_image":
        raise UnsupportedPublishDraft("Controlled image publish validation only supports single_image drafts")
    if not (draft.caption or "").strip():
        raise UnsupportedPublishDraft("Controlled image publish validation requires a non-empty caption")
    photo_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    if len(photo_paths) != 1:
        raise UnsupportedPublishDraft("Controlled image publish validation requires exactly one selected post image")
    return draft


def _validate_carousel_ready_draft(connection, draft_id: int, image_urls: Sequence[str]):
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post {draft_id} was not found")
    if draft.status != DraftState.READY_TO_PUBLISH.value:
        raise DraftNotReadyForImagePublish(
            f"Post {draft_id} must be {DraftState.READY_TO_PUBLISH.value} before controlled publishing"
        )
    if draft.post_type != "carousel":
        raise UnsupportedPublishDraft("Controlled carousel publish validation only supports carousel drafts")
    if not (draft.caption or "").strip():
        raise UnsupportedPublishDraft("Controlled carousel publish validation requires a non-empty caption")
    photo_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    if len(photo_paths) < 2:
        raise UnsupportedPublishDraft("Controlled carousel publish validation requires at least two selected post images")
    if len(image_urls) != len(photo_paths):
        raise UnsupportedPublishDraft(
            "Controlled carousel publish validation requires one public image URL per selected post image"
        )
    if len(image_urls) > 10:
        raise UnsupportedPublishDraft("Controlled carousel publish validation supports at most ten images")
    return draft


def _normalize_prefix(prefix: str) -> str:
    normalized = "/".join(part for part in prefix.strip("/").split("/") if part)
    return normalized or "post-relay/staging"


def _sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise UnsupportedPublishDraft("Controlled image publish validation requires a public https image URL")
    sanitized_query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if any(secretish in key.lower() for secretish in ("token", "secret", "signature", "sig", "key")):
            sanitized_query_pairs.append((key, "<redacted>"))
        else:
            sanitized_query_pairs.append((key, value))
    sanitized_query = "&".join(
        f"{key}={value}" if value else key for key, value in sanitized_query_pairs
    )
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            sanitized_query,
            parts.fragment,
        )
    )
