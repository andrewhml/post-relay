from pathlib import Path
from typing import Optional

from typer.testing import CliRunner

from post_relay.account_preferences import upsert_account_preferences
from post_relay.agent_checkins import (
    build_scheduled_checkin_delivery,
    render_scheduled_checkin_delivery,
)
from post_relay.cli import app
from post_relay.db import connect_db, initialize_db


runner = CliRunner()


def test_scheduled_checkin_delivery_sends_meaningful_trigger_in_working_hours(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_preferences(connection)
    _seed_meaningful_trigger(connection)
    _seed_progress_and_performance(connection)

    delivery = build_scheduled_checkin_delivery(
        connection,
        now_iso="2026-06-01T10:00:00-04:00",
        weekly_checkin=False,
    )

    assert delivery.should_send is True
    assert delivery.destination == "discord_dm"
    assert delivery.reason == "meaningful_trigger"
    assert "cadence risk:" in delivery.message
    assert "Progress:" in delivery.message
    assert "Performance:" in delivery.message
    assert "No automatic posting" in delivery.safety_note

    rendered = render_scheduled_checkin_delivery(delivery, cron_output=True)
    assert "Post Relay check-in" in rendered
    assert "Destination preference: discord_dm" in rendered
    assert "Progress:" in rendered
    assert "Performance:" in rendered


def test_scheduled_checkin_delivery_is_silent_when_no_meaningful_trigger_and_not_weekly(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_preferences(connection)
    _seed_scheduled_queue(connection)

    delivery = build_scheduled_checkin_delivery(
        connection,
        now_iso="2026-06-03T10:00:00-04:00",
        weekly_checkin=False,
    )

    assert delivery.should_send is False
    assert delivery.reason == "silent_no_meaningful_trigger"
    assert render_scheduled_checkin_delivery(delivery, cron_output=True) == ""


def test_scheduled_checkin_delivery_sends_when_no_future_content_after_two_days(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_preferences(connection, target_weekly_posts=None)
    _seed_published_post_snapshot(connection, actual_published_at="2026-06-01T07:21:31-04:00")

    delivery = build_scheduled_checkin_delivery(
        connection,
        now_iso="2026-06-03T10:00:00-04:00",
        weekly_checkin=False,
    )

    assert delivery.should_send is True
    assert delivery.reason == "meaningful_trigger"
    assert "no future content scheduled" in delivery.message
    assert "last published/scheduled post was 2 day(s) ago" in delivery.message


def test_scheduled_checkin_delivery_stays_silent_when_last_post_is_recent(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_preferences(connection, target_weekly_posts=None)
    _seed_published_post_snapshot(connection, actual_published_at="2026-06-02T10:30:00-04:00")

    delivery = build_scheduled_checkin_delivery(
        connection,
        now_iso="2026-06-03T10:00:00-04:00",
        weekly_checkin=False,
    )

    assert delivery.should_send is False
    assert delivery.reason == "silent_no_meaningful_trigger"


def test_scheduled_checkin_delivery_prefers_no_future_content_over_generic_weekly_target(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_preferences(connection, target_weekly_posts=3)
    _seed_published_post_snapshot(connection, actual_published_at="2026-06-01T07:21:31-04:00")

    delivery = build_scheduled_checkin_delivery(
        connection,
        now_iso="2026-06-04T10:00:00-04:00",
        weekly_checkin=False,
    )

    assert delivery.should_send is True
    assert "Trigger: cadence risk: no future content scheduled" in delivery.message


def test_scheduled_checkin_delivery_weekly_checkin_sends_progress_without_urgent_trigger(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    _seed_preferences(connection)
    _seed_scheduled_queue(connection)
    _seed_progress_and_performance(connection)

    result = runner.invoke(
        app,
        [
            "agent",
            "scheduled-checkin",
            "--db",
            str(db_path),
            "--now",
            "2026-06-08T10:00:00-04:00",
            "--weekly-checkin",
            "--cron-output",
        ],
    )

    assert result.exit_code == 0
    assert "Post Relay check-in" in result.output
    assert "weekly_checkin" in result.output
    assert "Progress:" in result.output
    assert "Performance:" in result.output
    assert "No automatic posting" in result.output


def test_scheduled_checkin_delivery_silent_outside_working_hours(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    _seed_preferences(connection)
    _seed_meaningful_trigger(connection)

    delivery = build_scheduled_checkin_delivery(
        connection,
        now_iso="2026-06-01T20:00:00-04:00",
        weekly_checkin=True,
    )

    assert delivery.should_send is False
    assert delivery.reason == "outside_working_hours"


def _seed_preferences(connection, *, target_weekly_posts: Optional[int] = 2):
    upsert_account_preferences(
        connection,
        account_key="default",
        target_weekly_posts=target_weekly_posts,
        agent_checkin_cadence="weekly",
        checkin_delivery_destination="discord_dm",
        checkin_trigger_policy="meaningful_plus_weekly",
        checkin_timezone="America/New_York",
        checkin_working_hours_start="09:00",
        checkin_working_hours_end="17:00",
        checkin_run_planners=True,
    )


def _seed_published_post_snapshot(connection, *, actual_published_at: str):
    connection.execute(
        """
        insert into drafts (id, post_type, status, scheduled_for)
        values (1, 'carousel', 'posted', ?)
        """,
        (actual_published_at,),
    )
    connection.execute(
        """
        insert into publish_attempts (id, draft_id, post_type, status, published_media_id, created_at)
        values (1, 1, 'carousel', 'published', 'media-1', ?)
        """,
        (actual_published_at,),
    )
    connection.execute(
        """
        insert into published_post_snapshots (
            id, draft_id, publish_attempt_id, published_media_id, post_type,
            media_urls_json, media_dimensions_json, actual_published_at
        ) values (1, 1, 1, 'media-1', 'carousel', '[]', '[]', ?)
        """,
        (actual_published_at,),
    )
    connection.commit()


def _seed_meaningful_trigger(connection):
    connection.execute(
        "insert into photo_sources (id, name, root, source_type) values (1, 'processed', '/tmp/photos', 'local')"
    )
    connection.execute(
        """
        insert into candidate_groups (id, title, source_name, source_folder, post_type_recommendation)
        values (1, 'Kyoto temples', 'processed', '/tmp/photos/kyoto', 'carousel')
        """
    )
    connection.execute(
        """
        insert into drafts (id, candidate_group_id, post_type, status)
        values (1, 1, 'carousel', 'awaiting_review')
        """
    )
    connection.commit()


def _seed_scheduled_queue(connection):
    for draft_id in [1, 2]:
        connection.execute(
            """
            insert into drafts (id, post_type, status, scheduled_for)
            values (?, 'carousel', 'scheduled', '2026-06-10T09:00:00-04:00')
            """,
            (draft_id,),
        )
    connection.commit()


def _seed_progress_and_performance(connection):
    connection.execute(
        """
        insert or ignore into drafts (id, post_type, status)
        values (10, 'carousel', 'posted')
        """
    )
    connection.execute(
        """
        insert into publish_attempts (id, draft_id, post_type, status, published_media_id, created_at)
        values (1, 10, 'carousel', 'published', 'media-1', '2026-06-01T09:00:00-04:00')
        """
    )
    connection.execute(
        """
        insert into published_post_snapshots (
            id, draft_id, publish_attempt_id, published_media_id, post_type, final_caption,
            media_urls_json, media_dimensions_json, actual_published_at
        ) values (1, 10, 1, 'media-1', 'carousel', 'caption', '[]', '[]', '2026-06-01T09:00:00-04:00')
        """
    )
    connection.execute(
        """
        insert into media_insight_snapshots (
            draft_id, published_post_snapshot_id, published_media_id, metrics_json, raw_payload_json, collected_at
        ) values (10, 1, 'media-1', '{"reach": 1200, "saved": 42, "likes": 100}', '{}', '2026-06-02T09:00:00-04:00')
        """
    )
    connection.execute(
        """
        insert into account_metric_snapshots (
            instagram_account_id, username, follower_count, follows_count, media_count, raw_payload_json, collected_at
        ) values ('ig-1', 'andrewhml', 1234, 100, 214, '{}', '2026-06-02T09:00:00-04:00')
        """
    )
    connection.commit()
