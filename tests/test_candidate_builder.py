from pathlib import Path

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.indexer import index_photo_sources
from post_relay.repository import list_candidate_groups


def _index_fixture_library(tmp_path: Path):
    root = tmp_path / "processed"
    kyoto = root / "2023" / "kyoto"
    tokyo = root / "2023" / "tokyo"
    single = root / "2024" / "iceland"
    kyoto.mkdir(parents=True)
    tokyo.mkdir(parents=True)
    single.mkdir(parents=True)
    (kyoto / "temple.jpg").write_bytes(b"fake image")
    (kyoto / "garden.jpg").write_bytes(b"fake image")
    (tokyo / "street.jpg").write_bytes(b"fake image")
    (single / "waterfall.jpg").write_bytes(b"fake image")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    return connection


def test_build_candidate_groups_groups_photos_by_parent_folder(tmp_path: Path):
    connection = _index_fixture_library(tmp_path)

    result = build_candidate_groups(connection)

    groups = list_candidate_groups(connection)
    assert result.created_count == 3
    assert [group.title for group in groups] == [
        "2023 / kyoto",
        "2023 / tokyo",
        "2024 / iceland",
    ]
    kyoto = groups[0]
    assert kyoto.photo_count == 2
    assert kyoto.post_type_recommendation == "carousel"
    assert kyoto.reason == "2 indexed photos from the same source folder."


def test_build_candidate_groups_is_idempotent(tmp_path: Path):
    connection = _index_fixture_library(tmp_path)

    first = build_candidate_groups(connection)
    second = build_candidate_groups(connection)

    assert first.created_count == 3
    assert second.created_count == 0
    assert len(list_candidate_groups(connection)) == 3


def test_single_photo_candidate_recommends_single_image(tmp_path: Path):
    connection = _index_fixture_library(tmp_path)

    build_candidate_groups(connection)

    groups = list_candidate_groups(connection)
    iceland = groups[2]
    assert iceland.photo_count == 1
    assert iceland.post_type_recommendation == "single_image"
