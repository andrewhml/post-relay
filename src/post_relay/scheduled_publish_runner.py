from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from shlex import quote
from typing import Optional
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from post_relay.config import R2StagingConfig
from post_relay.meta_graph import MetaGraphClient
from post_relay.publish_metadata import compose_final_meta_caption
from post_relay.publishing import (
    DraftNotFound,
    DraftNotReadyForImagePublish,
    PublishValidationError,
    UnsupportedPublishDraft,
    execute_carousel_publish_validation,
    execute_single_image_publish_validation,
    resolve_staged_r2_publish_image_urls,
)
from post_relay.repository import (
    get_draft,
    get_draft_location_tag,
    list_active_approvals,
    list_candidate_group_photo_paths,
)
from post_relay.state import ApprovalType, DraftState


class ScheduledPublishNotReady(ValueError):
    """Raised when a scheduled publish runner preflight should refuse/no-op."""


@dataclass(frozen=True)
class ScheduledPublishPreflightResult:
    draft_id: int
    ready: bool
    post_type: str
    scheduled_for: str
    image_urls: list[str]
    caption: str
    location_status: str
    location_text: Optional[str]
    location_tag_name: Optional[str]
    location_skip_reason: Optional[str]

    def to_text(self) -> str:
        lines = [
            "Scheduled publish preflight",
            f"Post ID: {self.draft_id}",
            f"Ready: {'yes' if self.ready else 'no'}",
            f"Post type: {self.post_type}",
            f"Scheduled for: {self.scheduled_for}",
            "Image URLs:",
        ]
        lines.extend(f"  - {url}" for url in self.image_urls)
        lines.extend(
            [
                f"Caption: {self.caption}",
                _location_status_text(
                    self.location_status,
                    location_text=self.location_text,
                    location_tag_name=self.location_tag_name,
                    location_skip_reason=self.location_skip_reason,
                ),
                "No Discord network calls were made.",
                "No R2 upload or cleanup calls were made.",
                "No Meta publishing endpoints were called.",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class ScriptlessScheduledPublishPlan:
    draft_id: int
    ready: bool
    post_type: str
    scheduled_for: str
    image_urls: list[str]
    publish_command: str
    hermes_cron_prompt: str
    location_status: str
    location_text: Optional[str]
    location_tag_name: Optional[str]
    location_skip_reason: Optional[str]

    def to_text(self) -> str:
        lines = [
            "Unattended scheduled publish plan",
            f"Post ID: {self.draft_id}",
            f"Ready: {'yes' if self.ready else 'no'}",
            f"Post type: {self.post_type}",
            f"Scheduled for: {self.scheduled_for}",
            "Staged media URLs in Meta order:",
        ]
        lines.extend(f"  - {url}" for url in self.image_urls)
        lines.extend(
            [
                "Publish command for the scheduled job:",
                self.publish_command,
                _location_status_text(
                    self.location_status,
                    location_text=self.location_text,
                    location_tag_name=self.location_tag_name,
                    location_skip_reason=self.location_skip_reason,
                ),
                "Hermes cron prompt:",
                self.hermes_cron_prompt,
                "No per-post script is required.",
                f"Approved assets have been staged, and this post will publish automatically at {self.scheduled_for}.",
                "You can still make changes any time before publishing; if you do, Post Relay will remove the publish approval, update the post, and ask you to approve it again before it goes live.",
                "No Discord network calls were made.",
                "No R2 upload or cleanup calls were made.",
                "No Meta publishing endpoints were called.",
            ]
        )
        return "\n".join(lines)


def preflight_due_scheduled_publish(
    connection,
    draft_id: int,
    *,
    r2_config: R2StagingConfig,
    now: Optional[str] = None,
) -> ScheduledPublishPreflightResult:
    draft, image_urls, caption = _validate_scheduled_publish_readiness(
        connection,
        draft_id,
        r2_config=r2_config,
        now=now,
        require_due=True,
    )
    location_status, location_text, location_tag_name, location_skip_reason = _location_decision_summary(
        connection,
        draft.id,
    )
    return ScheduledPublishPreflightResult(
        draft_id=draft.id,
        ready=True,
        post_type=draft.post_type,
        scheduled_for=draft.scheduled_for or "",
        image_urls=[_sanitize_url(url) for url in image_urls],
        caption=caption,
        location_status=location_status,
        location_text=location_text,
        location_tag_name=location_tag_name,
        location_skip_reason=location_skip_reason,
    )


def build_scriptless_scheduled_publish_plan(
    connection,
    draft_id: int,
    *,
    r2_config: R2StagingConfig,
    config_path: Path,
    db_path: Path,
    env_file: Path,
) -> ScriptlessScheduledPublishPlan:
    draft, image_urls, _caption = _validate_scheduled_publish_readiness(
        connection,
        draft_id,
        r2_config=r2_config,
        require_due=False,
    )
    location_status, location_text, location_tag_name, location_skip_reason = _location_decision_summary(
        connection,
        draft.id,
    )
    publish_command = _build_publish_command(
        draft.id,
        config_path=config_path,
        db_path=db_path,
        env_file=env_file,
    )
    hermes_cron_prompt = (
        "At the scheduled time, run this exact Post Relay command from the repo and report the result: "
        f"{publish_command}"
    )
    return ScriptlessScheduledPublishPlan(
        draft_id=draft.id,
        ready=True,
        post_type=draft.post_type,
        scheduled_for=draft.scheduled_for or "",
        image_urls=[_sanitize_url(url) for url in image_urls],
        publish_command=publish_command,
        hermes_cron_prompt=hermes_cron_prompt,
        location_status=location_status,
        location_text=location_text,
        location_tag_name=location_tag_name,
        location_skip_reason=location_skip_reason,
    )


def _validate_scheduled_publish_readiness(
    connection,
    draft_id: int,
    *,
    r2_config: R2StagingConfig,
    now: Optional[str] = None,
    require_due: bool,
):
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise ScheduledPublishNotReady(f"Post {draft_id} was not found")
    if draft.status != DraftState.READY_TO_PUBLISH.value:
        raise ScheduledPublishNotReady(
            f"Post {draft_id} must be {DraftState.READY_TO_PUBLISH.value} before scheduled publish execution; current status is {draft.status}"
        )
    if not draft.scheduled_for:
        raise ScheduledPublishNotReady(f"Post {draft_id} must have scheduled_for before scheduled publish execution")
    scheduled_for = draft.scheduled_for

    scheduled_at = _parse_runner_timestamp(scheduled_for, label="scheduled_for")
    if require_due:
        current_time = _parse_runner_timestamp(now, label="current time") if now else datetime.now().astimezone()
        if current_time < scheduled_at:
            raise ScheduledPublishNotReady(
                f"Post {draft_id} is scheduled for {draft.scheduled_for}; not due until {_format_timestamp(scheduled_at)}. "
                f"Current time: {_format_timestamp(current_time)}. No publish attempt was created."
            )

    _require_active_double_approval(connection, draft_id)
    image_urls = _resolve_staged_urls(connection, draft_id, r2_config)
    selected_count = len(list_candidate_group_photo_paths(connection, draft.candidate_group_id))
    caption = compose_final_meta_caption(draft)
    if not caption:
        raise ScheduledPublishNotReady("Scheduled publish requires a non-empty approved caption")
    if draft.post_type == "single_image":
        if selected_count != 1 or len(image_urls) != 1:
            raise ScheduledPublishNotReady("Scheduled single_image publish requires exactly one staged R2 media URL")
    elif draft.post_type == "carousel":
        if selected_count < 2 or len(image_urls) != selected_count:
            raise ScheduledPublishNotReady("Scheduled carousel publish requires complete staged R2 media for each selected image")
        if len(image_urls) > 10:
            raise ScheduledPublishNotReady("Scheduled carousel publish supports at most ten images")
    else:
        raise ScheduledPublishNotReady(f"Unsupported scheduled publish post type: {draft.post_type}")
    return draft, image_urls, caption


def execute_due_scheduled_publish(
    connection,
    draft_id: int,
    *,
    r2_config: R2StagingConfig,
    client: MetaGraphClient,
    now: Optional[str] = None,
):
    preflight_due_scheduled_publish(connection, draft_id, r2_config=r2_config, now=now)
    draft = get_draft(connection, draft_id)
    image_urls = _resolve_staged_urls(connection, draft_id, r2_config)
    try:
        if draft.post_type == "single_image":
            return execute_single_image_publish_validation(
                connection,
                draft_id,
                image_url=image_urls[0],
                client=client,
                now=now,
            )
        return execute_carousel_publish_validation(
            connection,
            draft_id,
            image_urls=image_urls,
            client=client,
            now=now,
        )
    except (DraftNotFound, DraftNotReadyForImagePublish, UnsupportedPublishDraft, PublishValidationError) as error:
        raise ScheduledPublishNotReady(str(error)) from error


def _require_active_double_approval(connection, draft_id: int) -> None:
    approval_types = {approval.approval_type for approval in list_active_approvals(connection, draft_id)}
    if {ApprovalType.DRAFT.value, ApprovalType.PUBLISH.value} - approval_types:
        raise ScheduledPublishNotReady(
            f"Post {draft_id} requires active content and publish approvals before scheduled publish execution"
        )


def _resolve_staged_urls(connection, draft_id: int, r2_config: R2StagingConfig) -> list[str]:
    try:
        return resolve_staged_r2_publish_image_urls(connection, draft_id, r2_config)
    except (DraftNotFound, UnsupportedPublishDraft) as error:
        raise ScheduledPublishNotReady(str(error)) from error


def _location_decision_summary(connection, draft_id: int):
    draft = get_draft(connection, draft_id)
    tag = get_draft_location_tag(connection, draft_id)
    if tag and tag.status == "resolved":
        return "resolved", None, tag.name, None
    if tag and tag.status == "skipped":
        return "skipped", draft.location_text if draft else None, None, tag.skip_reason
    if draft and draft.location_text:
        return "unresolved", draft.location_text, None, None
    return "none", None, None, None


def _location_status_text(
    status: str,
    *,
    location_text: Optional[str],
    location_tag_name: Optional[str],
    location_skip_reason: Optional[str],
) -> str:
    if status == "resolved":
        return f"Meta location tag: resolved ({location_tag_name})"
    if status == "skipped":
        return (
            "Meta location tag: intentionally skipped. "
            f"Reason: {location_skip_reason or '<none>'}. "
            "No Meta location_id will be sent; the user can add a location manually after publishing."
        )
    if status == "unresolved":
        return (
            "Meta location tag: unresolved. "
            f"Location context: {location_text}. "
            "Next safe action: search Meta Pages for a publishable location tag or run drafts location-tag-skip."
        )
    return "Meta location tag: none; no location context found."


def _build_publish_command(
    draft_id: int,
    *,
    config_path: Path,
    db_path: Path,
    env_file: Path,
) -> str:
    return " ".join(
        [
            ".venv/bin/post-relay",
            "meta",
            "publish-scheduled",
            "--post-id",
            str(draft_id),
            "--from-staged-r2",
            "--config",
            quote(config_path.as_posix()),
            "--db",
            quote(db_path.as_posix()),
            "--env-file",
            quote(env_file.as_posix()),
            "--execute",
        ]
    )


def _parse_runner_timestamp(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ScheduledPublishNotReady(f"Invalid {label} timestamp: {value}") from error
    if parsed.tzinfo is None:
        raise ScheduledPublishNotReady(f"Invalid {label} timestamp: {value}; timezone offset is required")
    return parsed


def _format_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    sanitized_query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if any(secretish in key.lower() for secretish in ("token", "secret", "signature", "sig", "key")):
            sanitized_query_pairs.append((key, "<redacted>"))
        else:
            sanitized_query_pairs.append((key, value))
    sanitized_query = "&".join(f"{key}={value}" if value else key for key, value in sanitized_query_pairs)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, sanitized_query, parts.fragment))
