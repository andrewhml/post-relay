from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from post_relay.meta_graph import MetaGraphClient, MetaGraphRequestError, redact_secrets
from post_relay.repository import (
    create_publish_attempt,
    get_draft,
    list_candidate_group_photo_paths,
    update_draft_status,
    update_publish_attempt,
)
from post_relay.state import DraftState, transition_draft_state


class DraftNotFound(ValueError):
    """Raised when a publish validation draft id does not exist."""


class DraftNotReadyForImagePublish(ValueError):
    """Raised when a draft has not received explicit publish approval."""


class UnsupportedPublishDraft(ValueError):
    """Raised when a draft cannot use the controlled publish validation path."""

class PublishValidationError(RuntimeError):

    """Raised when the controlled Meta publish validation fails."""


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
            f"Draft ID: {self.draft_id}",
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
            f"Draft ID: {self.draft_id}",
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


def prepare_single_image_publish_validation(
    connection,
    draft_id: int,
    *,
    image_url: str,
) -> SingleImagePublishValidationResult:
    draft = _validate_single_image_ready_draft(connection, draft_id)
    sanitized_image_url = _sanitize_url(image_url)
    caption = (draft.caption or "").strip()
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
) -> SingleImagePublishValidationResult:
    draft = _validate_single_image_ready_draft(connection, draft_id)
    if not client.config.instagram_account_id:
        raise PublishValidationError("POST_RELAY_INSTAGRAM_ACCOUNT_ID is required for publishing")

    sanitized_image_url = _sanitize_url(image_url)
    caption = (draft.caption or "").strip()
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

    try:
        container_payload = client.create_image_container(
            client.config.instagram_account_id,
            image_url=image_url,
            caption=caption,
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

        status_payload = client.get_media_container_status(container_id)
        status_code = str(status_payload.get("status_code") or "")
        if status_code != "FINISHED":
            raise PublishValidationError(
                f"Meta media container {container_id} is not ready: {status_code or '<unknown>'}"
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
        update_publish_attempt(
            connection,
            attempt.id,
            status="failed",
            status_message=safe_message,
        )
        update_draft_status(connection, draft.id, DraftState.FAILED.value)
        connection.commit()
        if isinstance(exc, (MetaGraphRequestError, PublishValidationError)):
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
    caption = (draft.caption or "").strip()
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
) -> CarouselPublishValidationResult:
    draft = _validate_carousel_ready_draft(connection, draft_id, image_urls)
    if not client.config.instagram_account_id:
        raise PublishValidationError("POST_RELAY_INSTAGRAM_ACCOUNT_ID is required for publishing")

    sanitized_image_urls = [_sanitize_url(image_url) for image_url in image_urls]
    caption = (draft.caption or "").strip()
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

    child_container_ids: list[str] = []
    carousel_container_id = ""
    status_code = ""
    try:
        for image_url in image_urls:
            child_payload = client.create_carousel_item_container(
                client.config.instagram_account_id,
                image_url=image_url,
            )
            child_container_id = str(child_payload.get("id") or "")
            if not child_container_id:
                raise PublishValidationError("Meta Graph did not return a carousel child container id")
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

        status_payload = client.get_media_container_status(carousel_container_id)
        status_code = str(status_payload.get("status_code") or "")
        if status_code != "FINISHED":
            raise PublishValidationError(
                f"Meta carousel container {carousel_container_id} is not ready: {status_code or '<unknown>'}"
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
        update_publish_attempt(
            connection,
            attempt.id,
            status="failed",
            container_id=carousel_container_id or None,
            child_container_ids=child_container_ids,
            status_message=safe_message,
        )
        update_draft_status(connection, draft.id, DraftState.FAILED.value)
        connection.commit()
        if isinstance(exc, (MetaGraphRequestError, PublishValidationError)):
            raise PublishValidationError(safe_message) from exc
        raise


def _validate_single_image_ready_draft(connection, draft_id: int):
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Draft {draft_id} was not found")
    if draft.status != DraftState.READY_TO_PUBLISH.value:
        raise DraftNotReadyForImagePublish(
            f"Draft {draft_id} must be {DraftState.READY_TO_PUBLISH.value} before controlled publishing"
        )
    if draft.post_type != "single_image":
        raise UnsupportedPublishDraft("Controlled image publish validation only supports single_image drafts")
    if not (draft.caption or "").strip():
        raise UnsupportedPublishDraft("Controlled image publish validation requires a non-empty caption")
    photo_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    if len(photo_paths) != 1:
        raise UnsupportedPublishDraft("Controlled image publish validation requires exactly one selected draft image")
    return draft


def _validate_carousel_ready_draft(connection, draft_id: int, image_urls: Sequence[str]):
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Draft {draft_id} was not found")
    if draft.status != DraftState.READY_TO_PUBLISH.value:
        raise DraftNotReadyForImagePublish(
            f"Draft {draft_id} must be {DraftState.READY_TO_PUBLISH.value} before controlled publishing"
        )
    if draft.post_type != "carousel":
        raise UnsupportedPublishDraft("Controlled carousel publish validation only supports carousel drafts")
    if not (draft.caption or "").strip():
        raise UnsupportedPublishDraft("Controlled carousel publish validation requires a non-empty caption")
    photo_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    if len(photo_paths) < 2:
        raise UnsupportedPublishDraft("Controlled carousel publish validation requires at least two selected draft images")
    if len(image_urls) != len(photo_paths):
        raise UnsupportedPublishDraft(
            "Controlled carousel publish validation requires one public image URL per selected draft image"
        )
    if len(image_urls) > 10:
        raise UnsupportedPublishDraft("Controlled carousel publish validation supports at most ten images")
    return draft


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
