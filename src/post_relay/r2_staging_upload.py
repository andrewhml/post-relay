from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from post_relay.config import R2StagingConfig
from post_relay.repository import (
    R2StagedObjectRecord,
    create_r2_staged_object_record,
    list_r2_staged_objects,
    mark_r2_staged_object_deleted,
)
from post_relay.r2_staging import R2StagingPlan, plan_r2_staging_for_draft


class R2StagingUploadError(ValueError):
    pass


class R2CleanupSafetyError(ValueError):
    pass


class R2StorageClient(Protocol):
    def upload_file(self, source_path: str, bucket: str, object_key: str) -> None:
        ...

    def delete_object(self, bucket: str, object_key: str) -> None:
        ...


@dataclass(frozen=True)
class R2StagingUploadResult:
    draft_id: int
    executed: bool
    planned_count: int
    uploaded_count: int
    object_keys: list[str]

    def to_text(self) -> str:
        mode = "executed" if self.executed else "dry run"
        lines = [
            f"R2 Staging Upload ({mode})",
            f"Draft ID: {self.draft_id}",
            f"Planned objects: {self.planned_count}",
            f"Uploaded objects: {self.uploaded_count}",
            "Object keys:",
        ]
        lines.extend(f"  - {key}" for key in self.object_keys) if self.object_keys else lines.append("  <none>")
        if self.executed:
            lines.append("Uploaded objects were recorded in SQLite.")
        else:
            lines.append("No network calls were made.")
            lines.append("Use --execute to upload and record staged objects.")
        return "\n".join(lines)


@dataclass(frozen=True)
class R2StagingCleanupResult:
    draft_id: int
    executed: bool
    planned_count: int
    deleted_count: int
    object_keys: list[str]

    def to_text(self) -> str:
        mode = "executed" if self.executed else "dry run"
        lines = [
            f"R2 Staging Cleanup ({mode})",
            f"Draft ID: {self.draft_id}",
            f"Recorded uploaded objects: {self.planned_count}",
            f"Deleted objects: {self.deleted_count}",
            "Object keys:",
        ]
        lines.extend(f"  - {key}" for key in self.object_keys) if self.object_keys else lines.append("  <none>")
        if self.executed:
            lines.append("Deleted objects were marked in SQLite.")
        else:
            lines.append("No objects were deleted.")
            lines.append("Use --execute to delete recorded staged objects.")
        return "\n".join(lines)


def upload_r2_staging_for_draft(
    connection,
    draft_id: int,
    config: R2StagingConfig,
    *,
    review_artifact_root: Optional[Path] = None,
    publish_export_root: Optional[Path] = None,
    include_review_artifacts: bool = False,
    execute: bool = False,
    client: Optional[R2StorageClient] = None,
) -> R2StagingUploadResult:
    plan = plan_r2_staging_for_draft(
        connection,
        draft_id,
        config,
        review_artifact_root=review_artifact_root,
        publish_export_root=publish_export_root,
    )
    items = plan.media_items + (plan.artifact_items if include_review_artifacts else [])
    object_keys = [item.object_key for item in items]
    missing_source_paths = [item.source_path for item in items if not item.exists]
    if not execute:
        return R2StagingUploadResult(
            draft_id=draft_id,
            executed=False,
            planned_count=len(items),
            uploaded_count=0,
            object_keys=object_keys,
        )
    if missing_source_paths:
        raise R2StagingUploadError(
            "Cannot upload R2 staging plan while source files are missing: "
            + ", ".join(missing_source_paths)
        )
    storage_client = client or build_boto3_r2_client(config)
    uploaded_count = 0
    for item in items:
        storage_client.upload_file(item.source_path, plan.bucket, item.object_key)
        create_r2_staged_object_record(
            connection,
            draft_id=draft_id,
            kind=item.kind,
            source_path=item.source_path,
            bucket=plan.bucket,
            object_key=item.object_key,
            public_url=item.public_url,
        )
        uploaded_count += 1
    connection.commit()
    return R2StagingUploadResult(
        draft_id=draft_id,
        executed=True,
        planned_count=len(items),
        uploaded_count=uploaded_count,
        object_keys=object_keys,
    )


def cleanup_r2_staged_objects_for_draft(
    connection,
    draft_id: int,
    config: R2StagingConfig,
    *,
    execute: bool = False,
    client: Optional[R2StorageClient] = None,
    reason: Optional[str] = None,
) -> R2StagingCleanupResult:
    records = list_r2_staged_objects(connection, draft_id, status="uploaded")
    _validate_cleanup_records(records, config)
    object_keys = [record.object_key for record in records]
    if not execute:
        return R2StagingCleanupResult(
            draft_id=draft_id,
            executed=False,
            planned_count=len(records),
            deleted_count=0,
            object_keys=object_keys,
        )
    storage_client = client or build_boto3_r2_client(config)
    deleted_count = 0
    for record in records:
        storage_client.delete_object(record.bucket, record.object_key)
        mark_r2_staged_object_deleted(connection, record.id, reason=reason)
        deleted_count += 1
    connection.commit()
    return R2StagingCleanupResult(
        draft_id=draft_id,
        executed=True,
        planned_count=len(records),
        deleted_count=deleted_count,
        object_keys=object_keys,
    )


def build_boto3_r2_client(config: R2StagingConfig) -> R2StorageClient:
    if not config.endpoint_url:
        raise R2StagingUploadError("R2 endpoint_url is required for execute mode.")
    access_key_id = os.environ.get(config.access_key_id_env)
    secret_access_key = os.environ.get(config.secret_access_key_env)
    if not access_key_id or not secret_access_key:
        raise R2StagingUploadError(
            f"R2 credentials are required for execute mode via {config.access_key_id_env} and {config.secret_access_key_env}."
        )
    try:
        import boto3  # type: ignore
    except ImportError as error:
        raise R2StagingUploadError("boto3 is required for live R2 upload/cleanup execute mode.") from error
    s3_client = boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )
    return _Boto3R2StorageClient(s3_client)


class _Boto3R2StorageClient:
    def __init__(self, s3_client):
        self._s3_client = s3_client

    def upload_file(self, source_path: str, bucket: str, object_key: str) -> None:
        self._s3_client.upload_file(source_path, bucket, object_key)

    def delete_object(self, bucket: str, object_key: str) -> None:
        self._s3_client.delete_object(Bucket=bucket, Key=object_key)


def _validate_cleanup_records(records: list[R2StagedObjectRecord], config: R2StagingConfig) -> None:
    normalized_prefix = _normalize_prefix(config.prefix)
    expected_prefix = f"{normalized_prefix}/"
    for record in records:
        if record.bucket != config.bucket:
            raise R2CleanupSafetyError(
                f"Refusing cleanup for staged object #{record.id}: bucket {record.bucket!r} does not match configured bucket."
            )
        if not record.object_key.startswith(expected_prefix):
            raise R2CleanupSafetyError(
                f"Refusing cleanup for staged object #{record.id}: object key is outside configured prefix {normalized_prefix!r}."
            )


def _normalize_prefix(prefix: str) -> str:
    normalized = "/".join(part for part in prefix.strip("/").split("/") if part)
    return normalized or "post-relay/staging"
