from pathlib import Path

import pytest
from PIL import Image

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig, ReviewArtifactsConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.repository import list_candidate_groups
from post_relay.review_artifacts import (
    DraftNotFound,
    OversizedReviewArtifactSet,
    UnsafeArtifactRoot,
    plan_bounded_review_artifacts_for_draft,
    render_review_artifacts_for_draft,
)


def _write_image(path: Path, size: tuple[int, int], color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=color).save(path, format="JPEG")


def _build_image_fixture_draft(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    first = folder / "01-shibuya.jpg"
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
    return connection, draft, [first, second]


def test_render_review_artifacts_creates_ordered_thumbnails_and_contact_sheet(tmp_path: Path):
    connection, draft, source_paths = _build_image_fixture_draft(tmp_path)
    original_bytes = {path: path.read_bytes() for path in source_paths}
    artifact_config = ReviewArtifactsConfig(
        root=tmp_path / "review_artifacts",
        thumbnail_max_px=160,
        contact_sheet_columns=2,
        mode="local",
    )

    package = render_review_artifacts_for_draft(connection, draft.id, artifact_config)

    assert package.draft_id == draft.id
    assert package.candidate_title == "2025 / tokyo"
    assert package.artifact_root == artifact_config.root / f"draft-{draft.id}"
    assert [artifact.source_path for artifact in package.thumbnails] == [
        path.as_posix() for path in source_paths
    ]
    assert [Path(artifact.local_path).name for artifact in package.thumbnails] == [
        "01-01-shibuya.jpg",
        "02-02-rooftop.jpg",
    ]
    assert Path(package.contact_sheet_path).is_file()

    for artifact in package.thumbnails:
        thumbnail_path = Path(artifact.local_path)
        assert thumbnail_path.is_file()
        with Image.open(thumbnail_path) as image:
            assert max(image.size) <= 160
            assert artifact.width == image.width
            assert artifact.height == image.height

    with Image.open(package.contact_sheet_path) as sheet:
        assert sheet.width == 320
        assert sheet.height == 184

    for path in source_paths:
        assert path.read_bytes() == original_bytes[path]


def test_render_review_artifacts_text_lists_outputs(tmp_path: Path):
    connection, draft, _source_paths = _build_image_fixture_draft(tmp_path)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts")

    package = render_review_artifacts_for_draft(connection, draft.id, artifact_config)

    text = package.to_text()
    assert "Review Artifacts" in text
    assert f"Draft ID: {draft.id}" in text
    assert "Candidate: 2025 / tokyo" in text
    assert "Thumbnails:" in text
    assert "01-01-shibuya.jpg" in text
    assert "02-02-rooftop.jpg" in text
    assert "Contact sheet:" in text
    assert "contact-sheet.jpg" in text


def test_render_review_artifacts_rejects_artifact_root_inside_source_root(tmp_path: Path):
    connection, draft, source_paths = _build_image_fixture_draft(tmp_path)
    source_root = source_paths[0].parents[2]

    with pytest.raises(UnsafeArtifactRoot):
        render_review_artifacts_for_draft(
            connection,
            draft.id,
            ReviewArtifactsConfig(root=source_root / "review_artifacts"),
            protected_source_roots=[source_root],
        )



def _build_large_image_fixture_draft(tmp_path: Path, *, image_count: int = 130):
    root = tmp_path / "processed"
    folder = root / "2025" / "san-francisco-spring-flowers"
    for index in range(image_count):
        _write_image(folder / f"image-{index:03d}.jpg", (32, 32), "green")

    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    return connection, draft, root


def test_bounded_review_artifact_plan_classifies_large_draft_without_source_paths(tmp_path: Path):
    connection, draft, root = _build_large_image_fixture_draft(tmp_path)

    plan = plan_bounded_review_artifacts_for_draft(connection, draft.id)

    assert plan.draft_id == draft.id
    assert plan.media_count == 130
    assert plan.classification == "large"
    assert plan.full_render_safe is False
    assert plan.sample_count == 24
    text = plan.to_text()
    assert "Bounded Review Artifact Plan" in text
    assert "130 included photos" in text
    assert "capped first-pass review" in text
    assert "drafts media-edit --draft-id" in text
    assert root.as_posix() not in text
    assert "image-000.jpg" not in text
    assert "No Discord, R2, or Meta network calls were made." in text


def test_render_review_artifacts_refuses_large_draft_and_returns_bounded_plan(tmp_path: Path):
    connection, draft, _root = _build_large_image_fixture_draft(tmp_path)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts")

    with pytest.raises(OversizedReviewArtifactSet) as error:
        render_review_artifacts_for_draft(connection, draft.id, artifact_config)

    assert error.value.plan.media_count == 130
    assert error.value.plan.full_render_safe is False
    assert not (artifact_config.root / f"draft-{draft.id}" / "contact-sheet.jpg").exists()


def test_cli_review_artifacts_render_prints_bounded_plan_for_large_draft(tmp_path: Path):
    from typer.testing import CliRunner
    from post_relay.cli import app

    connection, draft, root = _build_large_image_fixture_draft(tmp_path)
    connection.close()
    config_path = tmp_path / "photo_sources.yaml"
    artifact_root = tmp_path / "review_artifacts"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
review_artifacts:
  root: {artifact_root.as_posix()}
  thumbnail_max_px: 160
  contact_sheet_columns: 4
  mode: local
""".strip()
    )

    result = CliRunner().invoke(
        app,
        [
            "drafts",
            "artifacts",
            "render",
            "--draft-id",
            str(draft.id),
            "--config",
            str(config_path),
            "--db",
            str(tmp_path / "post_relay.sqlite"),
        ],
    )

    assert result.exit_code == 0
    assert "Bounded Review Artifact Plan" in result.output
    assert "Full contact sheet render blocked" in result.output
    assert "130 included photos" in result.output
    assert "No Discord, R2, or Meta network calls were made." in result.output
    assert root.as_posix() not in result.output
    assert not (artifact_root / f"draft-{draft.id}" / "contact-sheet.jpg").exists()


def test_render_review_artifacts_raises_for_missing_draft(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        render_review_artifacts_for_draft(connection, 999, ReviewArtifactsConfig(root=tmp_path))
