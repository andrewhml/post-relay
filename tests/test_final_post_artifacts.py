from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig, ReviewArtifactsConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.media_selection import apply_draft_crop_feedback, apply_draft_media_selection
from post_relay.repository import list_candidate_groups, update_draft_content
from post_relay.final_post_artifacts import render_final_post_preview_artifact


runner = CliRunner()


def _build_carousel_draft(tmp_path: Path):
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
    update_draft_content(connection, draft.id, caption="Night market glow.", hashtags=["#Seoul"])
    apply_draft_media_selection(connection, draft.id, lead=2, keep=[2, 1], post_type="carousel")
    apply_draft_crop_feedback(connection, draft.id, crop_edits={2: {"anchor": "B2", "ratio": "4:5"}})
    return connection, draft, folder


def test_render_final_post_preview_artifact_uses_selected_order_and_dark_design(tmp_path: Path):
    connection, draft, _folder = _build_carousel_draft(tmp_path)
    config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts", thumbnail_max_px=160, contact_sheet_columns=2)

    package = render_final_post_preview_artifact(connection, draft.id, config)

    assert package.draft_id == draft.id
    assert package.preview_path.endswith("final-post-preview.jpg")
    assert Path(package.preview_path).is_file()
    assert package.ordered_files == ["02-lanterns.jpg", "01-market.jpg"]
    assert package.ratio_label == "4:5"
    assert "Final Post Preview Artifact" in package.to_text()
    assert "02-lanterns.jpg" in package.to_text()
    assert "No Discord, R2, or Meta network calls were made." in package.to_text()
    with Image.open(package.preview_path) as image:
        assert image.width >= 320
        assert image.height >= 300
        assert image.getpixel((8, 8))[0] < 40


def test_cli_final_preview_artifact_render_outputs_local_path(tmp_path: Path):
    connection, draft, folder = _build_carousel_draft(tmp_path)
    connection.close()
    artifact_root = tmp_path / "review_artifacts"
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
    assert "final-post-preview.jpg" in result.output
    assert (artifact_root / f"draft-{draft.id}" / "final-post-preview.jpg").is_file()
