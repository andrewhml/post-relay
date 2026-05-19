from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from post_relay.config import R2StagingConfig
from post_relay.publish_exports import list_publish_export_media_paths
from post_relay.repository import get_candidate_group, get_draft, list_candidate_group_photo_paths


class DraftNotFound(ValueError):
    pass


class R2StagingConfigError(ValueError):
    pass


@dataclass(frozen=True)
class R2StagingPlanItem:
    kind: str
    source_path: str
    object_key: str
    public_url: str
    exists: bool


@dataclass(frozen=True)
class R2StagingPlan:
    draft_id: int
    candidate_title: str
    bucket: str
    prefix: str
    media_items: list[R2StagingPlanItem]
    artifact_items: list[R2StagingPlanItem]
    publish_export_profile: Optional[str] = None

    @property
    def missing_source_paths(self) -> list[str]:
        return [item.source_path for item in self.media_items + self.artifact_items if not item.exists]

    @property
    def ready_to_upload(self) -> bool:
        return not self.missing_source_paths

    def to_text(self) -> str:
        lines = [
            "R2 Staging Plan (dry run)",
            f"Post ID: {self.draft_id}",
            f"Candidate: {self.candidate_title}",
            f"Bucket: {self.bucket}",
            f"Prefix: {self.prefix}",
            f"Publish exports: {self.publish_export_profile or '<none>'}",
            f"Ready to upload: {'yes' if self.ready_to_upload else 'no'}",
            "Media:",
        ]
        lines.extend(_items_to_text(self.media_items))
        lines.append("Review artifacts:")
        lines.extend(_items_to_text(self.artifact_items))
        if self.missing_source_paths:
            lines.append("Missing files:")
            lines.extend(f"  - {path}" for path in self.missing_source_paths)
        else:
            lines.append("Missing files: <none>")
        lines.append("Object keys:")
        for item in self.media_items + self.artifact_items:
            lines.append(f"  - {item.object_key}")
        lines.append("No network calls were made.")
        return "\n".join(lines)


def plan_r2_staging_for_draft(
    connection,
    draft_id: int,
    config: R2StagingConfig,
    *,
    review_artifact_root: Optional[Path] = None,
    publish_export_root: Optional[Path] = None,
    publish_export_profile: str = "feed_portrait_4x5",
) -> R2StagingPlan:
    _validate_r2_staging_config(config)
    draft = get_draft(connection, draft_id)
    if draft is None:
        raise DraftNotFound(f"Post {draft_id} was not found.")

    candidate = get_candidate_group(connection, draft.candidate_group_id)
    candidate_title = candidate.title if candidate is not None else f"candidate #{draft.candidate_group_id}"
    media_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    selected_publish_export_profile: Optional[str] = None
    if publish_export_root is not None:
        export_paths = list_publish_export_media_paths(
            draft.id,
            publish_export_root,
            profile_name=publish_export_profile,
        )
        if export_paths:
            media_paths = export_paths
            selected_publish_export_profile = publish_export_profile
    prefix = _normalize_prefix(config.prefix)
    bucket = config.bucket or "<unconfigured>"
    public_base_url = (config.public_base_url or "").rstrip("/")

    media_items = [
        _plan_item(
            kind="draft_media",
            source=Path(source_path),
            object_key=_media_object_key(
                prefix=prefix,
                draft_id=draft.id,
                index=index,
                source=Path(source_path),
                publish_export_profile=selected_publish_export_profile,
            ),
            public_base_url=public_base_url,
        )
        for index, source_path in enumerate(media_paths, start=1)
    ]

    artifact_items: list[R2StagingPlanItem] = []
    if review_artifact_root is not None:
        artifact_items = _plan_review_artifact_items(
            draft_id=draft.id,
            artifact_root=review_artifact_root,
            prefix=prefix,
            public_base_url=public_base_url,
        )

    return R2StagingPlan(
        draft_id=draft.id,
        candidate_title=candidate_title,
        bucket=bucket,
        prefix=prefix,
        media_items=media_items,
        artifact_items=artifact_items,
        publish_export_profile=selected_publish_export_profile,
    )


def _media_object_key(
    *,
    prefix: str,
    draft_id: int,
    index: int,
    source: Path,
    publish_export_profile: Optional[str],
) -> str:
    name = f"{index:02d}-{_safe_key_stem(source)}{_safe_suffix(source)}"
    if publish_export_profile:
        return f"{prefix}/drafts/{draft_id}/publish-exports/{publish_export_profile}/media/{name}"
    return f"{prefix}/drafts/{draft_id}/media/{name}"


def _validate_r2_staging_config(config: R2StagingConfig) -> None:
    if not config.public_base_url:
        raise R2StagingConfigError("R2 staging public_base_url is required for dry-run URL planning.")
    if not config.bucket:
        raise R2StagingConfigError("R2 staging bucket is required for dry-run planning.")


def _plan_review_artifact_items(
    *,
    draft_id: int,
    artifact_root: Path,
    prefix: str,
    public_base_url: str,
) -> list[R2StagingPlanItem]:
    draft_artifact_root = artifact_root / f"draft-{draft_id}"
    thumbnails = sorted((draft_artifact_root / "thumbnails").glob("*.jpg"))
    items = [
        _plan_item(
            kind="review_thumbnail",
            source=thumbnail,
            object_key=f"{prefix}/drafts/{draft_id}/review-artifacts/thumbnails/{thumbnail.name}",
            public_base_url=public_base_url,
        )
        for thumbnail in thumbnails
    ]
    contact_sheet = draft_artifact_root / "contact-sheet.jpg"
    if contact_sheet.exists() or draft_artifact_root.exists():
        items.append(
            _plan_item(
                kind="contact_sheet",
                source=contact_sheet,
                object_key=f"{prefix}/drafts/{draft_id}/review-artifacts/contact-sheet.jpg",
                public_base_url=public_base_url,
            )
        )
    return items


def _plan_item(*, kind: str, source: Path, object_key: str, public_base_url: str) -> R2StagingPlanItem:
    return R2StagingPlanItem(
        kind=kind,
        source_path=source.as_posix(),
        object_key=object_key,
        public_url=f"{public_base_url}/{object_key}",
        exists=source.is_file(),
    )


def _items_to_text(items: list[R2StagingPlanItem]) -> list[str]:
    if not items:
        return ["  <none>"]
    return [
        f"  {index}. [{item.kind}] {'exists' if item.exists else 'missing'} {item.source_path} -> {item.public_url}"
        for index, item in enumerate(items, start=1)
    ]


def _normalize_prefix(prefix: str) -> str:
    normalized = "/".join(part for part in prefix.strip("/").split("/") if part)
    return normalized or "post-relay/staging"


def _safe_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    safe = "".join(character for character in suffix if character.isalnum() or character == ".")
    return safe or ".jpg"


def _safe_key_stem(path: Path) -> str:
    stem = path.stem.strip().lower()
    safe = "".join(character if character.isalnum() else "-" for character in stem)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe or "image"
