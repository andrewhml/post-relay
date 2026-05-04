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
    UnsafeArtifactRoot,
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



def test_render_review_artifacts_raises_for_missing_draft(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        render_review_artifacts_for_draft(connection, 999, ReviewArtifactsConfig(root=tmp_path))
