from pathlib import Path

from post_relay.db import connect_db, initialize_db


def test_initialize_db_creates_core_tables(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"

    connection = connect_db(db_path)
    initialize_db(connection)

    table_names = {
        row[0]
        for row in connection.execute(
            "select name from sqlite_master where type = 'table' order by name"
        )
    }

    assert "photo_sources" in table_names
    assert "photos" in table_names
    assert "candidate_groups" in table_names
    assert "candidate_group_items" in table_names
    assert "drafts" in table_names
    assert "approvals" in table_names
