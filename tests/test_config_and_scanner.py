from pathlib import Path

from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.media.scanner import scan_photo_sources


def test_photo_source_discovers_supported_files_by_year(tmp_path: Path):
    root = tmp_path / "processed"
    (root / "2023").mkdir(parents=True)
    (root / "2024").mkdir(parents=True)
    (root / "2023" / "kyoto.jpg").write_bytes(b"fake image")
    (root / "2023" / "notes.txt").write_text("ignore me")
    (root / "2024" / "tokyo.JPEG").write_bytes(b"fake image")

    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )

    results = scan_photo_sources(config)

    relative_paths = sorted(item.path.relative_to(root).as_posix() for item in results)
    assert relative_paths == ["2023/kyoto.jpg", "2024/tokyo.JPEG"]
    assert {item.source_name for item in results} == {"processed"}
    assert {item.inferred_year for item in results} == {2023, 2024}


def test_scanner_marks_non_year_folder_with_unknown_year(tmp_path: Path):
    root = tmp_path / "exports"
    root.mkdir()
    (root / "morocco.png").write_bytes(b"fake image")

    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="exports", root=root, source_type="processed_folder")]
    )

    results = scan_photo_sources(config)

    assert len(results) == 1
    assert results[0].path == root / "morocco.png"
    assert results[0].inferred_year is None
