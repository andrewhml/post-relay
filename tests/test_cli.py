from pathlib import Path

from typer.testing import CliRunner

from post_relay.cli import app


runner = CliRunner()


def test_cli_db_init_creates_database(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"

    result = runner.invoke(app, ["db", "init", "--db", str(db_path)])

    assert result.exit_code == 0
    assert db_path.exists()
    assert "Initialized database" in result.output


def test_cli_index_scan_and_library_stats(tmp_path: Path):
    root = tmp_path / "processed"
    (root / "2023").mkdir(parents=True)
    (root / "2023" / "kyoto.jpg").write_bytes(b"fake image")
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
""".strip()
    )
    db_path = tmp_path / "post_relay.sqlite"

    scan_result = runner.invoke(
        app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)]
    )
    stats_result = runner.invoke(app, ["library", "stats", "--db", str(db_path)])

    assert scan_result.exit_code == 0
    assert "Indexed 1 photos from 1 source" in scan_result.output
    assert stats_result.exit_code == 0
    assert "Total photos: 1" in stats_result.output
    assert "processed: 1" in stats_result.output
    assert "2023: 1" in stats_result.output


def test_cli_candidate_build_and_list(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    (folder / "garden.jpg").write_bytes(b"fake image")
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        f"""
photo_sources:
  - name: processed
    root: {root.as_posix()}
    source_type: processed_folder
""".strip()
    )
    db_path = tmp_path / "post_relay.sqlite"

    runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])
    build_result = runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    list_result = runner.invoke(app, ["candidates", "list", "--db", str(db_path)])

    assert build_result.exit_code == 0
    assert "Created 1 candidate group" in build_result.output
    assert list_result.exit_code == 0
    assert "2023 / kyoto" in list_result.output
    assert "carousel" in list_result.output
    assert "2 photos" in list_result.output
