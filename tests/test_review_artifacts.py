from pathlib import Path

import pytest
from PIL import Image

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig, ReviewArtifactsConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.media_selection import apply_draft_media_selection
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


def _build_image_fixture_draft(tmp_path: Path, *, image_count: int = 2):
    root = tmp_path / "processed"
    folder = root / "2025" / "tokyo"
    palette = ["red", "blue", "green", "yellow", "purple"]
    sizes = [(400, 300), (300, 500), (500, 300), (320, 480), (480, 320)]
    paths = []
    for index in range(1, image_count + 1):
        path = folder / f"{index:02d}-tokyo.jpg"
        _write_image(path, sizes[(index - 1) % len(sizes)], palette[(index - 1) % len(palette)])
        paths.append(path)

    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    return connection, draft, paths


def _count_near_white_pixels(image: Image.Image, rect: tuple[int, int, int, int]) -> int:
    x0, y0, x1, y1 = rect
    count = 0
    for x in range(x0, x1):
        for y in range(y0, y1):
            pixel = image.getpixel((x, y))
            if not isinstance(pixel, tuple):
                continue
            r, g, b = pixel[:3]
            if r > 220 and g > 220 and b > 210:
                count += 1
    return count


def test_render_review_artifacts_creates_ordered_thumbnails_and_contact_sheet(tmp_path: Path):
    connection, draft, source_paths = _build_image_fixture_draft(tmp_path)
    original_bytes = {path: path.read_bytes() for path in source_paths}
    artifact_config = ReviewArtifactsConfig(
        root=tmp_path / "review_artifacts",
        thumbnail_max_px=160,
        contact_sheet_columns=2,
        mode="local",
    )

    render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="select")
    apply_draft_media_selection(connection, draft.id, lead=1, keep=[1, 2], post_type="carousel")
    package = render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="all")

    assert package.draft_id == draft.id
    assert package.candidate_title == "2025 / tokyo"
    assert package.artifact_root == artifact_config.root / f"draft-{draft.id}"
    assert [artifact.source_path for artifact in package.thumbnails] == [
        path.as_posix() for path in source_paths
    ]
    assert [Path(artifact.local_path).name for artifact in package.thumbnails] == [
        "01-01-tokyo.jpg",
        "02-02-tokyo.jpg",
    ]
    assert Path(package.select_contact_sheet_path).is_file()
    assert Path(package.crop_contact_sheet_path).is_file()
    assert Path(package.contact_sheet_path) == Path(package.crop_contact_sheet_path)
    assert package.select_contact_sheet_path.endswith("contact-sheet-select.png")
    assert package.crop_contact_sheet_path.endswith("contact-sheet-crop.png")

    for artifact in package.thumbnails:
        thumbnail_path = Path(artifact.local_path)
        assert thumbnail_path.is_file()
        with Image.open(thumbnail_path) as image:
            assert max(image.size) <= 160
            assert artifact.width == image.width
            assert artifact.height == image.height

    with Image.open(package.select_contact_sheet_path) as select_sheet:
        assert select_sheet.width == 1440
        assert select_sheet.format == "PNG"
        assert select_sheet.info.get("dpi", (0, 0))[0] >= 190
        # Stage 1 is selection-only: dark paper + amber letter stickers, no
        # bright crop rectangle/grid overlay inside the first photo cell.
        white_overlay_pixels = _count_near_white_pixels(select_sheet, (32, 212, 478, 658))
        assert white_overlay_pixels == 0

    with Image.open(package.crop_contact_sheet_path) as sheet:
        assert sheet.width == 1440
        assert sheet.format == "PNG"
        assert sheet.info.get("dpi", (0, 0))[0] >= 190
        assert sheet.height >= 2 * (88 + 223 + 56 + 44)
        assert sheet.getpixel((16, 16)) != (255, 255, 255)
        assert sheet.getpixel((16, 16))[0] < 40
        # New contact sheets follow the uploaded Discord attachment spec: fixed
        # width, dark paper, and amber letter/crop affordances rather than the
        # older dynamic thumbnail layout.
        assert _count_near_white_pixels(sheet, (32, 212, 478, 658)) > 400
        amber_pixels = 0
        for x in range(sheet.width):
            for y in range(sheet.height):
                pixel = sheet.getpixel((x, y))
                if not isinstance(pixel, tuple):
                    continue
                r, g, b = pixel[:3]
                if r > 180 and g > 110 and b < 80:
                    amber_pixels += 1
                    break
            if amber_pixels:
                break
        assert amber_pixels > 0

    for path in source_paths:
        assert path.read_bytes() == original_bytes[path]


def test_render_review_artifacts_omits_excluded_media_after_selection_edit(tmp_path: Path):
    connection, draft, source_paths = _build_image_fixture_draft(tmp_path, image_count=4)
    artifact_config = ReviewArtifactsConfig(
        root=tmp_path / "review_artifacts",
        thumbnail_max_px=160,
        contact_sheet_columns=2,
        mode="local",
    )
    apply_draft_media_selection(connection, draft.id, lead=1, remove=[3, 4], post_type="carousel")

    package = render_review_artifacts_for_draft(connection, draft.id, artifact_config)

    assert [Path(artifact.source_path).name for artifact in package.thumbnails] == [
        source_paths[0].name,
        source_paths[1].name,
    ]
    assert [Path(path).name for path in source_paths[2:]] == ["03-tokyo.jpg", "04-tokyo.jpg"]
    assert not (artifact_config.root / f"draft-{draft.id}" / "thumbnails" / "03-03-tokyo.jpg").exists()
    assert not (artifact_config.root / f"draft-{draft.id}" / "thumbnails" / "04-04-tokyo.jpg").exists()


def test_render_review_artifacts_removes_stale_excluded_thumbnails_on_rerender(tmp_path: Path):
    connection, draft, _source_paths = _build_image_fixture_draft(tmp_path, image_count=4)
    artifact_config = ReviewArtifactsConfig(
        root=tmp_path / "review_artifacts",
        thumbnail_max_px=160,
        contact_sheet_columns=2,
        mode="local",
    )
    render_review_artifacts_for_draft(connection, draft.id, artifact_config)
    stale_thumbnail = artifact_config.root / f"draft-{draft.id}" / "thumbnails" / "03-03-tokyo.jpg"
    assert stale_thumbnail.exists()
    apply_draft_media_selection(connection, draft.id, lead=1, remove=[3, 4], post_type="carousel")

    render_review_artifacts_for_draft(connection, draft.id, artifact_config)

    assert not stale_thumbnail.exists()
    assert not (artifact_config.root / f"draft-{draft.id}" / "thumbnails" / "04-04-tokyo.jpg").exists()


def test_render_review_artifacts_defaults_to_selection_only(tmp_path: Path):
    connection, draft, _source_paths = _build_image_fixture_draft(tmp_path)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts")
    artifact_dir = artifact_config.root / f"draft-{draft.id}"
    artifact_dir.mkdir(parents=True)
    stale_crop = artifact_dir / "contact-sheet-crop.png"
    stale_final = artifact_dir / "final-post-preview.png"
    stale_crop.write_bytes(b"stale crop")
    stale_final.write_bytes(b"stale final preview")

    package = render_review_artifacts_for_draft(connection, draft.id, artifact_config)

    assert Path(package.select_contact_sheet_path).is_file()
    assert package.crop_contact_sheet_path is None
    assert package.contact_sheet_path == package.select_contact_sheet_path
    assert not stale_crop.exists()
    assert not stale_final.exists()
    text = package.to_text()
    assert "Stage 1 · Select:" in text
    assert "Stage 2 · Crop:" not in text


def test_render_review_artifacts_blocks_crop_until_media_selection_is_confirmed(tmp_path: Path):
    connection, draft, _source_paths = _build_image_fixture_draft(tmp_path)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts")
    render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="select")

    with pytest.raises(ValueError, match="media selection must be confirmed"):
        render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="crop")

    artifact_dir = artifact_config.root / f"draft-{draft.id}"
    assert not (artifact_dir / "contact-sheet-crop.png").exists()


def test_render_review_artifacts_allows_single_media_crop_without_selection_process(tmp_path: Path):
    connection, draft, _source_paths = _build_image_fixture_draft(tmp_path, image_count=1)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts")

    package = render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="crop")

    assert package.select_contact_sheet_path is None
    assert package.crop_contact_sheet_path is not None
    assert Path(package.crop_contact_sheet_path).is_file()


def test_render_review_artifacts_blocks_all_stage_from_skipping_selection(tmp_path: Path):
    connection, draft, _source_paths = _build_image_fixture_draft(tmp_path)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts")

    with pytest.raises(ValueError, match="Stage 1 selection review sheet must exist"):
        render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="all")

    artifact_dir = artifact_config.root / f"draft-{draft.id}"
    assert not (artifact_dir / "contact-sheet-crop.png").exists()


def test_render_review_artifacts_can_render_crop_after_selection_sheet_exists(tmp_path: Path):
    connection, draft, _source_paths = _build_image_fixture_draft(tmp_path)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts")
    render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="select")

    apply_draft_media_selection(connection, draft.id, lead=1, keep=[1, 2], post_type="carousel")

    package = render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="crop")

    assert package.select_contact_sheet_path is None
    assert package.crop_contact_sheet_path is not None
    assert Path(package.crop_contact_sheet_path).is_file()


def test_crop_stage_keeps_crop_area_overlay_instead_of_export_matte_preview(tmp_path: Path):
    connection, draft, source_paths = _build_image_fixture_draft(tmp_path, image_count=5)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts")
    render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="select")
    apply_draft_media_selection(connection, draft.id, lead=5, keep=[5], post_type="single_image")

    package = render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="crop")

    with Image.open(package.crop_contact_sheet_path) as sheet:
        assert _count_near_white_pixels(sheet, (32, 212, 478, 658)) > 400
        # Stage 2 should be a crop/framing decision sheet, not the final
        # publish-export matte. A landscape source still appears landscape in
        # the crop cell with the crop rectangle/grid overlaid.
        assert sheet.getpixel((360, 224))[:3] != (255, 255, 255)
    assert source_paths[4].name == "05-tokyo.jpg"


def test_render_review_artifacts_text_lists_outputs(tmp_path: Path):
    connection, draft, _source_paths = _build_image_fixture_draft(tmp_path)
    artifact_config = ReviewArtifactsConfig(root=tmp_path / "review_artifacts")
    render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="select")
    apply_draft_media_selection(connection, draft.id, lead=1, keep=[1, 2], post_type="carousel")

    package = render_review_artifacts_for_draft(connection, draft.id, artifact_config, stage="all")

    text = package.to_text()
    assert "Review Artifacts" in text
    assert f"Post ID: {draft.id}" in text
    assert "Candidate: 2025 / tokyo" in text
    assert "Thumbnails:" in text
    assert "01-01-tokyo.jpg" in text
    assert "02-02-tokyo.jpg" in text
    assert "Stage 1 · Select:" in text
    assert "contact-sheet-select.png" in text
    assert "selection only; no crop framing" in text
    assert "Stage 2 · Crop:" in text
    assert "crop/framing only; final export treatment appears in final review" in text
    assert "contact-sheet-crop.png" in text


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
    assert not (artifact_config.root / f"draft-{draft.id}" / "contact-sheet-select.png").exists()


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
    assert not (artifact_root / f"draft-{draft.id}" / "contact-sheet-select.png").exists()


def test_render_review_artifacts_raises_for_missing_draft(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    with pytest.raises(DraftNotFound):
        render_review_artifacts_for_draft(connection, 999, ReviewArtifactsConfig(root=tmp_path))
