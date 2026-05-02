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
