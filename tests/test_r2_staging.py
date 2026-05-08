from pathlib import Path

import pytest
from PIL import Image

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig, R2StagingConfig, ReviewArtifactsConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import list_candidate_groups
from post_relay.review_artifacts import render_review_artifacts_for_draft
from post_relay.r2_staging import DraftNotFound, R2StagingConfigError, plan_r2_staging_for_draft


def _write_image(path: Path, size: tuple[int, int], color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=color).save(path, format="JPEG")


def _build_carousel_draft(tmp_path: Path):
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
    return connection, draft, root, [first, second]


def test_plan_r2_staging_for_draft_preserves_media_and_artifact_order_without_absolute_keys(
    tmp_path: Path,
):
    connection, draft, _root, source_paths = _build_carousel_draft(tmp_path)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts", thumbnail_max_px=120)
    artifacts = render_review_artifacts_for_draft(connection, draft.id, artifact_config)
    r2_config = R2StagingConfig(
        enabled=False,
        bucket="post-relay-publish",
        public_base_url="https://peddocks.net",
        prefix="post-relay/staging",
    )

    plan = plan_r2_staging_for_draft(
        connection,
        draft.id,
        r2_config,
        review_artifact_root=artifact_config.root,
    )

    assert plan.draft_id == draft.id
    assert plan.ready_to_upload is True
    assert [item.source_path for item in plan.media_items] == [path.as_posix() for path in source_paths]
    assert [Path(item.object_key).name for item in plan.media_items] == [
        "01-01-shibuya-crossing.jpg",
        "02-02-rooftop.jpg",
    ]
    assert [item.kind for item in plan.artifact_items] == ["review_thumbnail", "review_thumbnail", "contact_sheet"]
    assert [Path(item.source_path).name for item in plan.artifact_items] == [
        "01-01-shibuya-crossing.jpg",
        "02-02-rooftop.jpg",
        "contact-sheet.jpg",
    ]
    all_items = plan.media_items + plan.artifact_items
    assert all(item.exists for item in all_items)
    assert all(item.public_url.startswith("https://peddocks.net/post-relay/staging/drafts/") for item in all_items)
    assert all(tmp_path.as_posix() not in item.object_key for item in all_items)
    assert all(" " not in item.object_key for item in all_items)
    assert "No network calls were made." in plan.to_text()
    assert artifacts.contact_sheet_path in plan.to_text()


def test_plan_r2_staging_reports_missing_files_before_upload(tmp_path: Path):
    connection, draft, _root, source_paths = _build_carousel_draft(tmp_path)
    source_paths[1].unlink()
    r2_config = R2StagingConfig(
        bucket="post-relay-publish",
        public_base_url="https://peddocks.net",
        prefix="post-relay/staging",
    )

    plan = plan_r2_staging_for_draft(connection, draft.id, r2_config)

    assert plan.ready_to_upload is False
    assert [item.exists for item in plan.media_items] == [True, False]
    assert plan.missing_source_paths == [source_paths[1].as_posix()]
    assert "Ready to upload: no" in plan.to_text()
    assert "Missing files:" in plan.to_text()


def test_plan_r2_staging_requires_public_base_url(tmp_path: Path):
    connection, draft, _root, _source_paths = _build_carousel_draft(tmp_path)

    with pytest.raises(R2StagingConfigError):
        plan_r2_staging_for_draft(connection, draft.id, R2StagingConfig(bucket="post-relay-publish"))


def test_plan_r2_staging_raises_for_missing_draft(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        plan_r2_staging_for_draft(
            connection,
            999,
            R2StagingConfig(bucket="post-relay-publish", public_base_url="https://peddocks.net"),
        )
