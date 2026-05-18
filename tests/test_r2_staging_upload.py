from pathlib import Path

import pytest
from PIL import Image

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig, R2StagingConfig, ReviewArtifactsConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import create_r2_staged_object_record, list_candidate_groups, list_r2_staged_objects
from post_relay.review_artifacts import render_review_artifacts_for_draft
from post_relay.r2_staging_upload import (
    R2CleanupSafetyError,
    R2StagingUploadError,
    cleanup_r2_staged_objects_for_draft,
    upload_r2_staging_for_draft,
)


class FakeR2Client:
    def __init__(self):
        self.uploads = []
        self.deletes = []

    def upload_file(self, source_path: str, bucket: str, object_key: str) -> None:
        self.uploads.append((source_path, bucket, object_key))

    def delete_object(self, bucket: str, object_key: str) -> None:
        self.deletes.append((bucket, object_key))


def _write_image(path: Path, size: tuple[int, int], color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=color).save(path, format="JPEG")


def _build_draft_with_artifacts(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    first = folder / "01-shibuya crossing.jpg"
    second = folder / "02-rooftop.jpg"
    _write_image(first, (400, 300), "red")
    _write_image(second, (300, 500), "blue")

    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts", thumbnail_max_px=120)
    render_review_artifacts_for_draft(connection, draft.id, artifact_config)
    r2_config = R2StagingConfig(
        enabled=True,
        bucket="post-relay-publish",
        endpoint_url="https://example-account.r2.cloudflarestorage.com",
        public_base_url="https://peddocks.net",
        prefix="post-relay/staging",
    )
    return connection, draft, artifact_config, r2_config, [first, second]


def test_upload_r2_staging_dry_run_defaults_to_selected_draft_media_only(tmp_path: Path):
    connection, draft, artifact_config, r2_config, _source_paths = _build_draft_with_artifacts(tmp_path)
    client = FakeR2Client()

    result = upload_r2_staging_for_draft(
        connection,
        draft.id,
        r2_config,
        review_artifact_root=artifact_config.root,
        execute=False,
        client=client,
    )

    assert result.executed is False
    assert result.uploaded_count == 0
    assert result.planned_count == 2
    assert result.object_keys == [
        "post-relay/staging/drafts/1/media/01-01-shibuya-crossing.jpg",
        "post-relay/staging/drafts/1/media/02-02-rooftop.jpg",
    ]
    assert client.uploads == []
    assert list_r2_staged_objects(connection, draft.id) == []
    assert "contact-sheet.jpg" not in result.to_text()
    assert "No network calls were made." in result.to_text()


def test_upload_r2_staging_execute_records_selected_draft_media_only_by_default(tmp_path: Path):
    connection, draft, artifact_config, r2_config, _source_paths = _build_draft_with_artifacts(tmp_path)
    client = FakeR2Client()

    result = upload_r2_staging_for_draft(
        connection,
        draft.id,
        r2_config,
        review_artifact_root=artifact_config.root,
        execute=True,
        client=client,
    )

    records = list_r2_staged_objects(connection, draft.id)
    assert result.executed is True
    assert result.uploaded_count == 2
    assert len(client.uploads) == 2
    assert [upload[1] for upload in client.uploads] == ["post-relay-publish"] * 2
    assert [record.object_key for record in records] == [upload[2] for upload in client.uploads]
    assert [record.kind for record in records] == ["draft_media", "draft_media"]
    assert all(record.status == "uploaded" for record in records)
    assert all(record.public_url.startswith("https://peddocks.net/post-relay/staging/") for record in records)


def test_upload_r2_staging_can_include_review_artifacts_when_requested(tmp_path: Path):
    connection, draft, artifact_config, r2_config, _source_paths = _build_draft_with_artifacts(tmp_path)
    client = FakeR2Client()

    result = upload_r2_staging_for_draft(
        connection,
        draft.id,
        r2_config,
        review_artifact_root=artifact_config.root,
        include_review_artifacts=True,
        execute=True,
        client=client,
    )

    records = list_r2_staged_objects(connection, draft.id)
    assert result.executed is True
    assert result.uploaded_count == 5
    assert len(client.uploads) == 5
    assert records[0].kind == "draft_media"
    assert records[-1].kind == "contact_sheet"


def test_upload_r2_staging_execute_blocks_missing_source_before_any_upload(tmp_path: Path):
    connection, draft, artifact_config, r2_config, source_paths = _build_draft_with_artifacts(tmp_path)
    source_paths[1].unlink()
    client = FakeR2Client()

    with pytest.raises(R2StagingUploadError):
        upload_r2_staging_for_draft(
            connection,
            draft.id,
            r2_config,
            review_artifact_root=artifact_config.root,
            execute=True,
            client=client,
        )

    assert client.uploads == []
    assert list_r2_staged_objects(connection, draft.id) == []


def test_cleanup_r2_staged_objects_dry_run_does_not_delete_or_mark_records(tmp_path: Path):
    connection, draft, artifact_config, r2_config, _source_paths = _build_draft_with_artifacts(tmp_path)
    upload_r2_staging_for_draft(
        connection,
        draft.id,
        r2_config,
        review_artifact_root=artifact_config.root,
        execute=True,
        client=FakeR2Client(),
    )
    client = FakeR2Client()

    result = cleanup_r2_staged_objects_for_draft(
        connection,
        draft.id,
        r2_config,
        execute=False,
        client=client,
        reason="test dry run",
    )

    assert result.executed is False
    assert result.deleted_count == 0
    assert result.planned_count == 2
    assert client.deletes == []
    assert all(record.status == "uploaded" for record in list_r2_staged_objects(connection, draft.id))
    assert "No objects were deleted." in result.to_text()


def test_cleanup_r2_staged_objects_execute_deletes_only_recorded_uploaded_objects(tmp_path: Path):
    connection, draft, artifact_config, r2_config, _source_paths = _build_draft_with_artifacts(tmp_path)
    upload_r2_staging_for_draft(
        connection,
        draft.id,
        r2_config,
        review_artifact_root=artifact_config.root,
        execute=True,
        client=FakeR2Client(),
    )
    client = FakeR2Client()

    result = cleanup_r2_staged_objects_for_draft(
        connection,
        draft.id,
        r2_config,
        execute=True,
        client=client,
        reason="publish complete",
    )

    records = list_r2_staged_objects(connection, draft.id)
    assert result.executed is True
    assert result.deleted_count == 2
    assert len(client.deletes) == 2
    assert [delete[1] for delete in client.deletes] == [record.object_key for record in records]
    assert all(record.status == "deleted" for record in records)
    assert all(record.deleted_at is not None for record in records)
    assert all(record.cleanup_reason == "publish complete" for record in records)


def test_cleanup_r2_staged_objects_refuses_record_outside_configured_prefix(tmp_path: Path):
    connection, draft, _artifact_config, r2_config, _source_paths = _build_draft_with_artifacts(tmp_path)
    create_r2_staged_object_record(
        connection,
        draft_id=draft.id,
        kind="draft_media",
        source_path="/tmp/source.jpg",
        bucket="post-relay-publish",
        object_key="other-prefix/drafts/1/media/01-source.jpg",
        public_url="https://peddocks.net/other-prefix/drafts/1/media/01-source.jpg",
    )
    client = FakeR2Client()

    with pytest.raises(R2CleanupSafetyError):
        cleanup_r2_staged_objects_for_draft(
            connection,
            draft.id,
            r2_config,
            execute=True,
            client=client,
        )

    assert client.deletes == []
    assert list_r2_staged_objects(connection, draft.id)[0].status == "uploaded"
