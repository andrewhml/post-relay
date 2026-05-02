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


def test_cli_draft_create_and_list(tmp_path: Path):
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
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    create_result = runner.invoke(
        app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)]
    )
    list_result = runner.invoke(app, ["drafts", "list", "--db", str(db_path)])

    assert create_result.exit_code == 0
    assert "Created draft #1 from candidate #1" in create_result.output
    assert list_result.exit_code == 0
    assert "#1 candidate #1" in list_result.output
    assert "carousel" in list_result.output
    assert "drafting" in list_result.output


def test_cli_draft_preview_outputs_review_package(tmp_path: Path):
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
    runner.invoke(app, ["candidates", "build", "--db", str(db_path)])
    runner.invoke(app, ["drafts", "create", "--candidate-id", "1", "--db", str(db_path)])
    preview_result = runner.invoke(app, ["drafts", "preview", "--draft-id", "1", "--db", str(db_path)])

    assert preview_result.exit_code == 0
    assert "Draft Review Package" in preview_result.output
    assert "Draft ID: 1" in preview_result.output
    assert "Status: drafting" in preview_result.output
    assert "Candidate: 2023 / kyoto" in preview_result.output
    assert "Post type: carousel" in preview_result.output
    assert (folder / "garden.jpg").as_posix() in preview_result.output
    assert (folder / "temple.jpg").as_posix() in preview_result.output
    assert "Caption: <empty>" in preview_result.output
    assert "Unresolved context notes:" in preview_result.output
    assert "Allowed next actions:" in preview_result.output
