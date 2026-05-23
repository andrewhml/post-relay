from pathlib import Path

from typer.testing import CliRunner

from post_relay.cli import app
from post_relay.db import connect_db, initialize_db
from post_relay.media_awareness import mark_media_used, list_media_usage, summarize_media_usage
from post_relay.recommendations import build_candidate_rankings, render_candidate_rankings


runner = CliRunner()


def test_mark_media_used_persists_user_scoped_usage_without_moving_source_file(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    source_path = tmp_path / "processed" / "kyoto" / "posted.jpg"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"already posted")
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_photo(connection, photo_id=1, path=source_path)

    result = mark_media_used(
        connection,
        local_file_path=source_path.as_posix(),
        user_key="andrew",
        usage_status="posted",
        note="posted before Post Relay",
    )

    assert result.photo_id == 1
    assert result.user_key == "andrew"
    assert result.usage_status == "posted"
    assert result.local_file_path == source_path.as_posix()
    assert source_path.exists()
    usage = list_media_usage(connection, user_key="andrew")
    assert [record.local_file_path for record in usage] == [source_path.as_posix()]
    assert usage[0].note == "posted before Post Relay"


def test_cli_media_mark_used_and_summary_are_local_user_memory(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    source_path = tmp_path / "processed" / "seoul" / "posted.jpg"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"already posted")
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_photo(connection, photo_id=1, path=source_path)

    result = runner.invoke(
        app,
        [
            "media",
            "mark-used",
            "--path",
            source_path.as_posix(),
            "--user-key",
            "andrew",
            "--reason",
            "already on IG",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Media usage recorded" in result.output
    assert "User: andrew" in result.output
    assert "Status: posted" in result.output
    assert "Source media was not moved or modified." in result.output

    summary = runner.invoke(app, ["media", "used-summary", "--user-key", "andrew", "--db", str(db_path)])
    assert summary.exit_code == 0
    assert "Media awareness summary" in summary.output
    assert "posted: 1" in summary.output
    assert "No Discord, R2, or Meta network calls were made." in summary.output


def test_candidate_rankings_warn_and_penalize_previously_used_media_by_default(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    fresh_path = tmp_path / "processed" / "fresh" / "unused.jpg"
    used_path = tmp_path / "processed" / "used" / "posted.jpg"
    fresh_path.parent.mkdir(parents=True)
    used_path.parent.mkdir(parents=True)
    fresh_path.write_bytes(b"fresh")
    used_path.write_bytes(b"used")
    _seed_candidate(connection, candidate_id=1, title="Already posted set", path=used_path)
    _seed_candidate(connection, candidate_id=2, title="Fresh set", path=fresh_path)
    mark_media_used(connection, local_file_path=used_path.as_posix(), user_key="default", usage_status="posted")

    rankings = build_candidate_rankings(connection, limit=2)

    assert [ranking.candidate_id for ranking in rankings] == [2, 1]
    used_ranking = rankings[1]
    assert used_ranking.used_media_count == 1
    assert used_ranking.fresh_media_count == 0
    assert "Media awareness: all included media already marked used for this user" in used_ranking.score_breakdown
    assert "All included media are already marked used; use --include-used only for audits or intentional reuse." in used_ranking.warnings


def test_candidate_rankings_can_include_used_media_for_audit_copy(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    used_path = tmp_path / "processed" / "used" / "posted.jpg"
    used_path.parent.mkdir(parents=True)
    used_path.write_bytes(b"used")
    _seed_candidate(connection, candidate_id=1, title="Already posted set", path=used_path)
    mark_media_used(connection, local_file_path=used_path.as_posix(), user_key="default", usage_status="posted")

    rendered = render_candidate_rankings(connection, limit=1, include_used=True)

    assert "Used media: 1 used / 1 included; fresh: 0" in rendered
    assert "Include-used mode: previously used media are visible for audit or intentional reuse." in rendered


def test_recording_usage_from_post_marks_selected_original_media(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    first_path = tmp_path / "processed" / "trip" / "one.jpg"
    second_path = tmp_path / "processed" / "trip" / "two.jpg"
    first_path.parent.mkdir(parents=True)
    first_path.write_bytes(b"one")
    second_path.write_bytes(b"two")
    _seed_candidate(connection, candidate_id=1, title="Trip carousel", path=first_path)
    _add_candidate_photo(connection, candidate_id=1, photo_id=2, path=second_path, sort_order=2)
    connection.execute("insert into drafts (id, candidate_group_id, post_type, status) values (42, 1, 'carousel', 'posted')")
    connection.commit()

    result = summarize_media_usage(connection, user_key="default", post_id=42)

    assert result.total == 2
    assert result.by_status == {"posted": 2}
    usage_paths = [record.local_file_path for record in list_media_usage(connection)]
    assert usage_paths == [first_path.as_posix(), second_path.as_posix()]


def _seed_photo(connection, *, photo_id: int, path: Path):
    connection.execute(
        "insert into photo_sources (id, name, root, source_type) values (1, 'processed', ?, 'local')",
        (str(path.parent),),
    )
    connection.execute(
        """
        insert into photos (id, source_id, source_name, local_file_path, source_type, inferred_year, width, height)
        values (?, 1, 'processed', ?, 'local', 2026, 1080, 1440)
        """,
        (photo_id, path.as_posix()),
    )
    connection.commit()


def _seed_candidate(connection, *, candidate_id: int, title: str, path: Path):
    if connection.execute("select 1 from photo_sources where id = 1").fetchone() is None:
        connection.execute(
            "insert into photo_sources (id, name, root, source_type) values (1, 'processed', ?, 'local')",
            (str(path.parent.parent),),
        )
    connection.execute(
        """
        insert into candidate_groups (id, title, source_name, source_folder, source_year, post_type_recommendation, reason)
        values (?, ?, 'processed', ?, 2026, 'single_image', 'test candidate')
        """,
        (candidate_id, title, f"2026/{title.lower().replace(' ', '-')}",),
    )
    _add_candidate_photo(connection, candidate_id=candidate_id, photo_id=candidate_id, path=path, sort_order=1)
    connection.commit()


def _add_candidate_photo(connection, *, candidate_id: int, photo_id: int, path: Path, sort_order: int):
    connection.execute(
        """
        insert into photos (id, source_id, source_name, local_file_path, source_type, inferred_year, width, height)
        values (?, 1, 'processed', ?, 'local', 2026, 1080, 1440)
        """,
        (photo_id, path.as_posix()),
    )
    connection.execute(
        """
        insert into candidate_group_items (group_id, photo_id, sort_order, include_status)
        values (?, ?, ?, 'included')
        """,
        (candidate_id, photo_id, sort_order),
    )
