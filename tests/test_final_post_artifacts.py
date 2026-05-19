from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig, ReviewArtifactsConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.guided_draft import accept_guided_draft_package, build_guided_draft_package
from post_relay.indexer import index_photo_sources
from post_relay.media_selection import apply_draft_crop_feedback, apply_draft_media_selection
from post_relay.repository import list_candidate_groups, update_draft_content
from post_relay.final_post_artifacts import render_final_post_preview_artifact
from post_relay.review_artifacts import render_review_artifacts_for_draft


runner = CliRunner()


def _build_carousel_draft(tmp_path: Path, *, accept_guided_package: bool = True):
    root = tmp_path / "processed"
    folder = root / "2025" / "seoul"
    folder.mkdir(parents=True)
    Image.new("RGB", (400, 300), color="red").save(folder / "01-market.jpg", format="JPEG")
    Image.new("RGB", (300, 500), color="blue").save(folder / "02-lanterns.jpg", format="JPEG")
    Image.new("RGB", (500, 400), color="green").save(folder / "03-alley.jpg", format="JPEG")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")])
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    update_draft_content(
        connection,
        draft.id,
        caption="Night market glow.",
        hashtags=["#Seoul"],
        location_text="Gwangjang Market, Seoul",
    )
    apply_draft_media_selection(connection, draft.id, lead=2, keep=[2, 1], post_type="carousel")
    apply_draft_crop_feedback(connection, draft.id, crop_edits={2: {"anchor": "B2", "ratio": "4:5"}})
    if accept_guided_package:
        package = build_guided_draft_package(
            connection,
            draft.id,
            location_text="Gwangjang Market, Seoul",
            story_angle="night market glow",
            mood="cinematic",
            audience_hook="lantern light",
        )
        accept_guided_draft_package(connection, package, caption_index=1)
    return connection, draft, folder


def test_render_final_post_preview_artifact_uses_selected_order_and_dark_design(tmp_path: Path):
    connection, draft, _folder = _build_carousel_draft(tmp_path)
    config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts", thumbnail_max_px=160, contact_sheet_columns=2)
    render_review_artifacts_for_draft(connection, draft.id, config, stage="select")
    render_review_artifacts_for_draft(connection, draft.id, config, stage="crop")

    package = render_final_post_preview_artifact(connection, draft.id, config)

    assert package.draft_id == draft.id
    assert package.preview_path.endswith("final-post-preview.png")
    assert Path(package.preview_path).is_file()
    assert package.ordered_files == ["02-lanterns.jpg", "01-market.jpg"]
    assert package.ratio_label == "4:5"
    assert package.metadata_tags == ["LOCATION · Gwangjang Market, Seoul", "TYPE · CAROUSEL", "RATIO · 4:5"]
    assert "Final Post Preview Artifact" in package.to_text()
    assert "02-lanterns.jpg" in package.to_text()
    assert "Metadata:" in package.to_text()
    assert "LOCATION · Gwangjang Market, Seoul" in package.to_text()
    assert "No Discord, R2, or Meta network calls were made." in package.to_text()
    with Image.open(package.preview_path) as image:
        assert image.width == 1440
        assert image.height >= 800
        assert image.info.get("dpi", (0, 0))[0] >= 190
        assert image.getpixel((16, 16))[0] < 40


def test_render_final_post_preview_artifact_blocks_until_crop_sheet_exists(tmp_path: Path):
    connection, draft, _folder = _build_carousel_draft(tmp_path)
    config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts", thumbnail_max_px=160, contact_sheet_columns=2)
    render_review_artifacts_for_draft(connection, draft.id, config, stage="select")

    with pytest.raises(ValueError, match="Stage 2 crop review must be completed"):
        render_final_post_preview_artifact(connection, draft.id, config)

    assert not (config.root / f"draft-{draft.id}" / "final-post-preview.png").exists()


def test_render_final_post_preview_artifact_blocks_until_guided_package_is_accepted(tmp_path: Path):
    connection, draft, _folder = _build_carousel_draft(tmp_path, accept_guided_package=False)
    config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts", thumbnail_max_px=160, contact_sheet_columns=2)
    render_review_artifacts_for_draft(connection, draft.id, config, stage="select")
    render_review_artifacts_for_draft(connection, draft.id, config, stage="crop")

    with pytest.raises(ValueError, match="accepted guided post package"):
        render_final_post_preview_artifact(connection, draft.id, config)

    assert not (config.root / f"draft-{draft.id}" / "final-post-preview.png").exists()


def test_cli_final_preview_artifact_render_outputs_local_path(tmp_path: Path):
    connection, draft, folder = _build_carousel_draft(tmp_path)
    artifact_root = tmp_path / "review_artifacts"
    config = ReviewArtifactsConfig(root=artifact_root, thumbnail_max_px=160, contact_sheet_columns=2)
    render_review_artifacts_for_draft(connection, draft.id, config, stage="select")
    render_review_artifacts_for_draft(connection, draft.id, config, stage="crop")
    connection.close()
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {folder.parents[1].as_posix()}
    source_type: processed_folder
review_artifacts:
  root: {artifact_root.as_posix()}
  thumbnail_max_px: 160
  contact_sheet_columns: 2
  mode: local
""".strip()
    )

    result = runner.invoke(
        app,
        [
            "drafts",
            "final-preview-artifact",
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
    assert "Final Post Preview Artifact" in result.output
    assert "final-post-preview.png" in result.output
    assert (artifact_root / f"draft-{draft.id}" / "final-post-preview.png").is_file()
