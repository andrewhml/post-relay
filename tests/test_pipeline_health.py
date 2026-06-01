from pathlib import Path

from typer.testing import CliRunner

from post_relay.account_preferences import upsert_account_preferences
from post_relay.cli import app
from post_relay.db import connect_db, initialize_db
from post_relay.pipeline_health import build_pipeline_health, render_pipeline_health


runner = CliRunner()


def test_build_pipeline_health_counts_stages_and_next_work(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_pipeline_rows(connection)
    upsert_account_preferences(
        connection,
        account_key="default",
        target_weekly_posts=3,
        target_monthly_reels=10,
        growth_mode="growth_push",
    )

    health = build_pipeline_health(connection)

    assert health.stage_counts["drafting"] == 1
    assert health.stage_counts["awaiting_review"] == 1
    assert health.stage_counts["scheduled"] == 1
    assert health.stage_counts["posted"] == 1
    assert health.candidate_groups_without_posts == 1
    assert "cadence risk: target 3 posts/week, scheduled queue has 1" in health.cadence_risk
    assert any("Post 2 needs user content review" in item for item in health.user_needed_reviews)
    assert any("Candidate 3 can become a draft" in item for item in health.agent_preparable_work)
    assert health.mutation_statement == (
        "No Discord, R2, or Meta network calls were made. No posts, approvals, "
        "schedules, opportunities, publish attempts, or analytics rows were mutated."
    )


def test_render_pipeline_health_is_local_advisory(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_pipeline_rows(connection)

    rendered = render_pipeline_health(connection)

    assert "Pipeline health" in rendered
    assert "Counts by stage:" in rendered
    assert "User-needed reviews:" in rendered
    assert "Agent-preparable next work:" in rendered
    assert "Cadence risk:" in rendered
    assert "No automatic posting, scheduling, approval, messaging, upload, or analytics collection was performed." in rendered
    assert "No Discord, R2, or Meta network calls were made." in rendered


def test_cli_pipeline_health_is_local_advisory_only(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_pipeline_rows(connection)
    before_posts = connection.execute("select count(*) from drafts").fetchone()[0]
    before_approvals = connection.execute("select count(*) from approvals").fetchone()[0]
    before_scheduled = connection.execute("select count(*) from drafts where scheduled_for is not null").fetchone()[0]

    result = runner.invoke(app, ["pipeline", "health", "--db", str(db_path)])

    after_posts = connection.execute("select count(*) from drafts").fetchone()[0]
    after_approvals = connection.execute("select count(*) from approvals").fetchone()[0]
    after_scheduled = connection.execute("select count(*) from drafts where scheduled_for is not null").fetchone()[0]
    assert result.exit_code == 0
    assert before_posts == after_posts == 4
    assert before_approvals == after_approvals == 1
    assert before_scheduled == after_scheduled == 1
    assert "Pipeline health" in result.output
    assert "No automatic posting, scheduling, approval, messaging, upload, or analytics collection was performed." in result.output


def test_pipeline_health_ignores_invalidated_approvals_on_posted_drafts(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    connection.execute(
        """
        insert into drafts (id, post_type, status)
        values (1, 'carousel', 'posted')
        """
    )
    connection.execute(
        """
        insert into approvals (draft_id, approval_type, approved_by, invalidated_at, invalidation_reason)
        values (1, 'draft', 'andrew', '2026-06-01T09:00:00-07:00', 'old correction')
        """
    )
    connection.commit()

    health = build_pipeline_health(connection)

    assert health.blocked_posts == []


def _seed_pipeline_rows(connection):
    connection.execute(
        "insert into photo_sources (id, name, root, source_type) values (1, 'processed', '/tmp/photos', 'local')"
    )
    for candidate_id, title in [(1, "Kyoto temples"), (2, "Lisbon overlooks"), (3, "Seoul cafes")]:
        connection.execute(
            """
            insert into candidate_groups (id, title, source_name, source_folder, post_type_recommendation)
            values (?, ?, 'processed', ?, 'carousel')
            """,
            (candidate_id, title, f"/tmp/photos/{candidate_id}"),
        )
    for draft_id, candidate_id, status, scheduled_for in [
        (1, 1, "drafting", None),
        (2, 2, "awaiting_review", None),
        (3, None, "scheduled", "2026-06-03T09:00:00-07:00"),
        (4, None, "posted", None),
    ]:
        connection.execute(
            """
            insert into drafts (id, candidate_group_id, post_type, status, scheduled_for)
            values (?, ?, 'carousel', ?, ?)
            """,
            (draft_id, candidate_id, status, scheduled_for),
        )
    connection.execute(
        """
        insert into approvals (draft_id, approval_type, approved_by, invalidated_at, invalidation_reason)
        values (1, 'draft', 'andrew', '2026-06-01T09:00:00-07:00', 'media changed')
        """
    )
    connection.commit()
