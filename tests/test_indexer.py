from pathlib import Path

from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.indexer import index_photo_sources
from post_relay.repository import get_library_stats


def test_index_photo_sources_persists_photos_and_is_idempotent(tmp_path: Path):
    root = tmp_path / "processed"
    (root / "2023").mkdir(parents=True)
    (root / "2023" / "kyoto.jpg").write_bytes(b"fake image")
    (root / "2023" / "tokyo.jpeg").write_bytes(b"fake image")
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )

    first_result = index_photo_sources(connection, config)
    second_result = index_photo_sources(connection, config)

    assert first_result.scanned_count == 2
    assert first_result.inserted_or_updated_count == 2
    assert second_result.scanned_count == 2
    assert second_result.inserted_or_updated_count == 2
    photo_count = connection.execute("select count(*) from photos").fetchone()[0]
    source_count = connection.execute("select count(*) from photo_sources").fetchone()[0]
    assert photo_count == 2
    assert source_count == 1


def test_get_library_stats_groups_by_source_and_year(tmp_path: Path):
    root = tmp_path / "processed"
    (root / "2023").mkdir(parents=True)
    (root / "2024").mkdir(parents=True)
    (root / "2023" / "kyoto.jpg").write_bytes(b"fake image")
    (root / "2024" / "tokyo.jpg").write_bytes(b"fake image")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)

    stats = get_library_stats(connection)

    assert stats.total_photos == 2
    assert stats.by_source == {"processed": 2}
    assert stats.by_year == {2023: 1, 2024: 1}
