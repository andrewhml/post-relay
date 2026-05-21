from pathlib import Path

from typer.testing import CliRunner

from post_relay.cli import app
from post_relay.db import connect_db, initialize_db
from post_relay.recommendations import build_candidate_rankings, render_candidate_rankings
from post_relay.user_goals import upsert_active_user_goal


runner = CliRunner()


def test_build_candidate_rankings_prioritizes_goal_aligned_ready_sets(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    upsert_active_user_goal(
        connection,
        title="Travel account north star",
        goal_statement="Grow with saveable city-guide route carousels.",
        target_audience="Travelers planning city walks.",
        content_pillars=["city guides", "route carousels"],
        desired_cadence="2 posts per week",
        success_metrics=["saves", "shares"],
        strategy_notes="Recommend one best next post with rationale.",
        constraints=["avoid places not pictured"],
        reviewed_by="andrew",
        change_note="initial agreement",
    )
    _seed_candidate_ranking_rows(connection, tmp_path)

    rankings = build_candidate_rankings(connection, limit=3)

    assert [ranking.candidate_id for ranking in rankings] == [1, 3, 2]
    assert rankings[0].rank == 1
    assert rankings[0].title == "Kyoto city route"
    assert rankings[0].score > rankings[1].score > rankings[2].score
    assert rankings[0].media_count == 4
    assert rankings[0].missing_file_count == 0
    assert "Goal alignment: matched active goal language" in rankings[0].score_breakdown
    assert "Readiness: all included source files exist" in rankings[0].score_breakdown
    assert "Content potential: carousel-sized coherent local set" in rankings[0].score_breakdown
    assert rankings[0].next_safe_command == "post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite"
    assert "Large set: narrow before rendering a contact sheet" in rankings[2].warnings
    assert "Readiness: missing local source files" in rankings[2].score_breakdown


def test_render_candidate_rankings_explains_scores_and_safety(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_candidate_ranking_rows(connection, tmp_path)

    rendered = render_candidate_rankings(connection, limit=2)

    assert "Candidate recommendations" in rendered
    assert "#1 Candidate 1: Kyoto city route" in rendered
    assert "Score:" in rendered
    assert "Why this ranks here:" in rendered
    assert "Next safe command: post-relay drafts create --candidate-id 1" in rendered
    assert "Sparse analytics note: performance data is not weighted strongly yet." in rendered
    assert "No Discord, R2, or Meta network calls were made." in rendered
    assert "No posts, approvals, schedules, opportunities, publish attempts, or analytics rows were mutated." in rendered


def test_cli_recommendations_candidates_is_limitable_and_read_only(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_candidate_ranking_rows(connection, tmp_path)
    draft_count_before = connection.execute("select count(*) from drafts").fetchone()[0]
    publish_attempt_count_before = connection.execute("select count(*) from publish_attempts").fetchone()[0]

    result = runner.invoke(app, ["recommendations", "candidates", "--limit", "1", "--db", str(db_path)])

    draft_count_after = connection.execute("select count(*) from drafts").fetchone()[0]
    publish_attempt_count_after = connection.execute("select count(*) from publish_attempts").fetchone()[0]
    assert result.exit_code == 0
    assert "#1 Candidate 1: Kyoto city route" in result.output
    assert "Candidate 3" not in result.output
    assert "No Discord, R2, or Meta network calls were made." in result.output
    assert draft_count_after == draft_count_before
    assert publish_attempt_count_after == publish_attempt_count_before


def _seed_candidate_ranking_rows(connection, tmp_path: Path):
    photo_root = tmp_path / "photos"
    photo_root.mkdir()
    existing_paths = []
    for index in range(1, 6):
        path = photo_root / f"kyoto-route-{index}.jpg"
        path.write_bytes(b"fake image bytes")
        existing_paths.append(path)

    connection.execute(
        "insert into photo_sources (id, name, root, source_type) values (1, 'processed', ?, 'local')",
        (str(photo_root),),
    )
    # Candidate 1: goal-aligned, existing carousel-sized set.
    connection.execute(
        """
        insert into candidate_groups (id, title, source_name, source_folder, source_year, post_type_recommendation, reason)
        values (1, 'Kyoto city route', 'processed', '2026/kyoto-city-route', 2026, 'carousel', '4 indexed photos from a city walk route folder.')
        """
    )
    for order, path in enumerate(existing_paths[:4], start=1):
        photo_id = order
        connection.execute(
            """
            insert into photos (id, source_id, source_name, local_file_path, source_type, inferred_year, width, height)
            values (?, 1, 'processed', ?, 'local', 2026, 1080, 1440)
            """,
            (photo_id, str(path)),
        )
        connection.execute(
            """
            insert into candidate_group_items (group_id, photo_id, sort_order, include_status)
            values (1, ?, ?, 'included')
            """,
            (photo_id, order),
        )

    # Candidate 2: huge generic dump with missing files and no dimensions.
    connection.execute(
        """
        insert into candidate_groups (id, title, source_name, source_folder, source_year, post_type_recommendation, reason)
        values (2, 'Random archive dump', 'processed', '2026/random-archive-dump', 2026, 'carousel', '130 indexed photos from a broad folder.')
        """
    )
    for offset in range(130):
        photo_id = 1000 + offset
        connection.execute(
            """
            insert into photos (id, source_id, source_name, local_file_path, source_type, inferred_year)
            values (?, 1, 'processed', ?, 'local', 2026)
            """,
            (photo_id, str(photo_root / f"missing-random-{offset}.jpg")),
        )
        connection.execute(
            """
            insert into candidate_group_items (group_id, photo_id, sort_order, include_status)
            values (2, ?, ?, 'included')
            """,
            (photo_id, offset + 1),
        )

    # Candidate 3: ready, but already scheduled so it should not outrank a fresh strong candidate.
    connection.execute(
        """
        insert into candidate_groups (id, title, source_name, source_folder, source_year, post_type_recommendation, reason)
        values (3, 'Seoul cafe single', 'processed', '2026/seoul-cafe', 2026, 'single_image', '1 indexed photo from the same source folder.')
        """
    )
    connection.execute(
        """
        insert into photos (id, source_id, source_name, local_file_path, source_type, inferred_year, width, height)
        values (5, 1, 'processed', ?, 'local', 2026, 1440, 1080)
        """,
        (str(existing_paths[4]),),
    )
    connection.execute(
        """
        insert into candidate_group_items (group_id, photo_id, sort_order, include_status)
        values (3, 5, 1, 'included')
        """
    )
    connection.execute(
        """
        insert into drafts (id, candidate_group_id, post_type, status, scheduled_for)
        values (1, 3, 'single_image', 'scheduled', '2026-06-01T09:00:00-07:00')
        """
    )
    connection.commit()
