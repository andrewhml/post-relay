from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig, PublishExportsConfig, R2StagingConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.publish_exports import render_publish_exports_for_draft
from post_relay.repository import list_candidate_groups
from post_relay.r2_staging import plan_r2_staging_for_draft


def _write_image(path: Path, size: tuple[int, int], color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=color).save(path, format="JPEG")


def _build_mixed_carousel_draft(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "mt-cook"
    portrait = folder / "01-portrait.jpg"
    landscape = folder / "02-landscape.jpg"
    _write_image(portrait, (467, 700), "red")
    _write_image(landscape, (700, 467), "blue")

    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    return connection, draft, root, [portrait, landscape]


def test_render_publish_exports_creates_4x5_assets_without_extra_contact_sheet_and_preserves_sources(tmp_path: Path):
    connection, draft, source_root, source_paths = _build_mixed_carousel_draft(tmp_path)
    original_bytes = {path: path.read_bytes() for path in source_paths}
    config = PublishExportsConfig(root=tmp_path / "publish_exports")
    stale_sheet = config.root / f"draft-{draft.id}" / "feed_portrait_4x5" / "publish-contact-sheet.jpg"
    stale_sheet.parent.mkdir(parents=True, exist_ok=True)
    stale_sheet.write_bytes(b"stale publish sheet")

    package = render_publish_exports_for_draft(
        connection,
        draft.id,
        config,
        profile_name="feed_portrait_4x5",
        landscape_treatment="clean_mat",
        protected_source_roots=[source_root],
    )

    assert package.profile_name == "feed_portrait_4x5"
    assert package.width == 1080
    assert package.height == 1350
    assert [Path(item.local_path).name for item in package.media_items] == [
        "01-01-portrait.jpg",
        "02-02-landscape.jpg",
    ]
    assert [item.treatment for item in package.media_items] == ["center_crop", "clean_mat"]
    assert package.warnings == ["Mixed media orientations detected: landscape, portrait"]
    for item in package.media_items:
        with Image.open(item.local_path) as exported:
            assert exported.size == (1080, 1350)
    assert package.contact_sheet_path is None
    assert not (config.root / f"draft-{draft.id}" / "feed_portrait_4x5" / "publish-contact-sheet.jpg").exists()
    for path in source_paths:
        assert path.read_bytes() == original_bytes[path]
    assert source_root.as_posix() not in "\n".join(item.object_key_hint for item in package.media_items)
    assert "No Discord, R2, or Meta network calls were made." in package.to_text()


def test_render_publish_exports_creates_3x4_feed_profile_assets(tmp_path: Path):
    connection, draft, source_root, _source_paths = _build_mixed_carousel_draft(tmp_path)
    config = PublishExportsConfig(root=tmp_path / "publish_exports")

    package = render_publish_exports_for_draft(
        connection,
        draft.id,
        config,
        profile_name="feed_portrait_3x4",
        landscape_treatment="clean_mat",
        protected_source_roots=[source_root],
    )

    assert package.profile_name == "feed_portrait_3x4"
    assert package.width == 1080
    assert package.height == 1440
    assert [item.treatment for item in package.media_items] == ["center_crop", "clean_mat"]
    for item in package.media_items:
        with Image.open(item.local_path) as exported:
            assert exported.size == (1080, 1440)
    assert package.contact_sheet_path is None
    assert "Profile: feed_portrait_3x4 (1080x1440)" in package.to_text()
    assert "Publish preview contact sheet" not in package.to_text()


def test_render_publish_exports_can_crop_landscape_into_portrait_profile(tmp_path: Path):
    connection, draft, source_root, _source_paths = _build_mixed_carousel_draft(tmp_path)
    config = PublishExportsConfig(root=tmp_path / "publish_exports")

    package = render_publish_exports_for_draft(
        connection,
        draft.id,
        config,
        profile_name="feed_portrait_3x4",
        landscape_treatment="center_crop",
        protected_source_roots=[source_root],
    )

    assert [item.treatment for item in package.media_items] == ["center_crop", "center_crop"]
    landscape_export = Path(package.media_items[1].local_path)
    with Image.open(landscape_export) as exported:
        assert exported.size == (1080, 1440)
        assert exported.getpixel((20, 20))[:3] != (255, 255, 255)
        assert exported.getpixel((exported.width - 21, exported.height - 21))[:3] != (255, 255, 255)


def test_r2_staging_prefers_publish_exports_when_available(tmp_path: Path):
    connection, draft, _source_root, source_paths = _build_mixed_carousel_draft(tmp_path)
    export_config = PublishExportsConfig(root=tmp_path / "publish_exports")
    package = render_publish_exports_for_draft(connection, draft.id, export_config)
    r2_config = R2StagingConfig(
        bucket="post-relay-publish",
        public_base_url="https://peddocks.net",
        prefix="post-relay/staging",
    )

    plan = plan_r2_staging_for_draft(
        connection,
        draft.id,
        r2_config,
        publish_export_root=export_config.root,
        publish_export_profile="feed_portrait_3x4",
    )

    assert [item.source_path for item in plan.media_items] == [item.local_path for item in package.media_items]
    assert all("publish-exports/feed_portrait_3x4/media" in item.object_key for item in plan.media_items)
    assert all(item.kind == "draft_media" for item in plan.media_items)
    assert all(Path(item.source_path).is_file() for item in plan.media_items)
    assert all(path.as_posix() not in [item.source_path for item in plan.media_items] for path in source_paths)
    assert "Publish exports: feed_portrait_3x4" in plan.to_text()


def test_cli_publish_exports_render_prints_exported_dimensions_and_warnings(tmp_path: Path):
    from post_relay.cli import app

    connection, draft, source_root, _source_paths = _build_mixed_carousel_draft(tmp_path)
    connection.close()
    config_path = tmp_path / "photo_sources.yaml"
    export_root = tmp_path / "publish_exports"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {source_root.as_posix()}
    source_type: processed_folder
publish_exports:
  root: {export_root.as_posix()}
""".strip()
    )

    result = CliRunner().invoke(
        app,
        [
            "drafts",
            "publish-exports",
            "render",
            "--post-id",
            str(draft.id),
            "--profile",
            "feed_portrait_4x5",
            "--config",
            str(config_path),
            "--db",
            str(tmp_path / "post_relay.sqlite"),
        ],
    )

    assert result.exit_code == 0
    assert "Publish Exports" in result.output
    assert "Profile: feed_portrait_4x5 (1080x1350)" in result.output
    assert "01-01-portrait.jpg (1080x1350, center_crop)" in result.output
    assert "02-02-landscape.jpg (1080x1350, clean_mat)" in result.output
    assert "Mixed media orientations detected" in result.output
    assert "No Discord, R2, or Meta network calls were made." in result.output
    assert "Publish preview contact sheet" not in result.output
    assert not (export_root / f"draft-{draft.id}" / "feed_portrait_4x5" / "publish-contact-sheet.jpg").exists()
