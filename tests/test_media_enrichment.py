from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.indexer import index_photo_sources

runner = CliRunner()


def test_indexing_persists_local_image_enrichment(tmp_path: Path):
    root = tmp_path / "processed"
    (root / "2025" / "seoul").mkdir(parents=True)
    image_path = root / "2025" / "seoul" / "market.jpg"
    Image.new("RGB", (1200, 1800), color="black").save(image_path)
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )

    result = index_photo_sources(connection, config)

    assert result.scanned_count == 1
    assert result.enriched_count == 1
    row = connection.execute(
        "select width, height from photos where local_file_path = ?",
        (image_path.as_posix(),),
    ).fetchone()
    assert tuple(row) == (1200, 1800)


def test_index_scan_reports_local_metadata_enrichment_without_network(tmp_path: Path):
    root = tmp_path / "processed"
    (root / "2025" / "seoul").mkdir(parents=True)
    Image.new("RGB", (800, 600), color="black").save(root / "2025" / "seoul" / "street.jpg")
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

    result = runner.invoke(app, ["index", "scan", "--config", str(config_path), "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Indexed 1 photos from 1 source." in result.output
    assert "Enriched local metadata for 1 photo." in result.output
    assert "No network calls were made." in result.output
