from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from post_relay.analytics_feedback import (
    PublishedPostSnapshotNotReady,
    build_analytics_cadence_plan,
    build_feedback_summary,
    build_follower_growth_plan,
    build_follower_growth_summary,
    build_insights_collection_plan,
    collect_and_store_due_analytics,
    collect_and_store_follower_metrics,
    collect_and_store_media_insights,
    record_published_post_snapshot,
    render_analytics_cadence_plan,
    render_feedback_summary,
    render_follower_growth_summary,
)
from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.meta_graph import MetaGraphClient, MetaGraphConfig
from post_relay.publishing import execute_carousel_publish_validation
from post_relay.repository import (
    create_r2_staged_object_record,
    get_draft,
    get_published_post_snapshot_for_draft,
    list_account_metric_snapshots,
    list_candidate_groups,
    list_media_insight_snapshots,
)
from post_relay.scheduling import approve_draft_for_publishing, request_publish_approval, schedule_draft
from post_relay.state import DraftState


runner = CliRunner()


def _build_ready_carousel_with_exported_staged_media(tmp_path: Path):
    source_root = tmp_path / "processed"
    source_folder = source_root / "2025" / "seoul"
    source_folder.mkdir(parents=True)
    Image.new("RGB", (1600, 2000), "red").save(source_folder / "market.jpg")
    Image.new("RGB", (1600, 2000), "blue").save(source_folder / "lanterns.jpg")

    export_root = tmp_path / "publish_exports" / "draft-1" / "feed_portrait_4x5" / "media"
    export_root.mkdir(parents=True)
    export_paths = [export_root / "01-market.jpg", export_root / "02-lanterns.jpg"]
    Image.new("RGB", (1080, 1350), "red").save(export_paths[0])
    Image.new("RGB", (1080, 1350), "blue").save(export_paths[1])

    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=source_root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    connection.execute(
        "update drafts set caption = ?, hashtags_json = ?, status = ? where id = ?",
        ('Night market glow.', '["seoul", "travelphotography"]', DraftState.DRAFTING.value, draft.id),
    )
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    schedule_draft(connection, draft.id, scheduled_for="2026-05-19T10:00:00-04:00")
    request_publish_approval(connection, draft.id)
    approve_draft_for_publishing(connection, draft.id, approved_by="andrew")

    public_urls = [
        "https://peddocks.net/post-relay/staging/drafts/1/media/01-market.jpg",
        "https://peddocks.net/post-relay/staging/drafts/1/media/02-lanterns.jpg",
    ]
    for index, (path, public_url) in enumerate(zip(export_paths, public_urls), start=1):
        create_r2_staged_object_record(
            connection,
            draft_id=draft.id,
            kind="draft_media",
            source_path=path.as_posix(),
            bucket="post-relay-publish",
            object_key=f"post-relay/staging/drafts/1/media/{index:02d}.jpg",
            public_url=public_url,
        )
    connection.commit()
    return connection, get_draft(connection, draft.id), public_urls


def test_record_published_post_snapshot_captures_final_payload_and_export_dimensions(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    connection.execute(
        """
        insert into publish_attempts (
            draft_id, post_type, image_url, caption, container_id, published_media_id,
            status, status_code, image_urls_json, child_container_ids_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft.id,
            "carousel",
            public_urls[0],
            "Night market glow.\n\n#seoul #travelphotography",
            "carousel-123",
            "media-789",
            "published",
            "FINISHED",
            '["https://peddocks.net/post-relay/staging/drafts/1/media/01-market.jpg", "https://peddocks.net/post-relay/staging/drafts/1/media/02-lanterns.jpg"]',
            '["child-1", "child-2"]',
        ),
    )
    connection.execute("update drafts set status = ? where id = ?", (DraftState.POSTED.value, draft.id))
    connection.commit()

    snapshot = record_published_post_snapshot(
        connection,
        draft.id,
        actual_published_at="2026-05-19T10:02:30-04:00",
    )

    assert snapshot.published_media_id == "media-789"
    assert snapshot.final_caption == "Night market glow.\n\n#seoul #travelphotography"
    assert snapshot.media_urls == public_urls
    assert snapshot.media_dimensions == [
        {"width": 1080, "height": 1350},
        {"width": 1080, "height": 1350},
    ]
    assert snapshot.scheduled_for == "2026-05-19T10:00:00-04:00"
    assert snapshot.actual_published_at == "2026-05-19T10:02:30-04:00"


def test_record_published_post_snapshot_requires_successful_published_attempt(tmp_path: Path):
    connection, draft, _public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)

    with pytest.raises(PublishedPostSnapshotNotReady, match="successful published attempt"):
        record_published_post_snapshot(connection, draft.id)


def test_execute_publish_records_post_publish_snapshot_without_extra_network_calls(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        media_url = "https://graph.facebook.com/v19.0/17841400498120050/media"
        if url == media_url and params.get("image_url") == public_urls[0]:
            return {"id": "child-1"}
        if url == media_url and params.get("image_url") == public_urls[1]:
            return {"id": "child-2"}
        if url == media_url and params.get("media_type") == "CAROUSEL":
            return {"id": "carousel-123"}
        if url.endswith("/carousel-123"):
            return {"id": "carousel-123", "status_code": "FINISHED"}
        if url.endswith("/17841400498120050/media_publish"):
            return {"id": "media-789"}
        raise AssertionError(f"unexpected request: {method} {url} {params}")

    client = MetaGraphClient(
        MetaGraphConfig(access_token="secret-token", instagram_account_id="17841400498120050"),
        transport=fake_transport,
    )

    execute_carousel_publish_validation(
        connection,
        draft.id,
        image_urls=public_urls,
        client=client,
        now="2026-05-19T10:02:30-04:00",
    )

    snapshot = get_published_post_snapshot_for_draft(connection, draft.id)
    assert snapshot is not None
    assert snapshot.published_media_id == "media-789"
    assert snapshot.media_dimensions == [
        {"width": 1080, "height": 1350},
        {"width": 1080, "height": 1350},
    ]
    assert len(requested) == 5


def test_insights_collection_plan_is_read_only_and_uses_published_media_id(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    connection.execute(
        """
        insert into publish_attempts (
            draft_id, post_type, image_url, caption, container_id, published_media_id,
            status, status_code, image_urls_json, child_container_ids_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft.id,
            "carousel",
            public_urls[0],
            "Night market glow.",
            "carousel-123",
            "media-789",
            "published",
            "FINISHED",
            '["https://peddocks.net/post-relay/staging/drafts/1/media/01-market.jpg", "https://peddocks.net/post-relay/staging/drafts/1/media/02-lanterns.jpg"]',
            '["child-1", "child-2"]',
        ),
    )
    connection.execute("update drafts set status = ? where id = ?", (DraftState.POSTED.value, draft.id))
    connection.commit()
    record_published_post_snapshot(connection, draft.id, actual_published_at="2026-05-19T10:02:30-04:00")

    plan = build_insights_collection_plan(connection, draft.id)

    assert plan.draft_id == draft.id
    assert plan.published_media_id == "media-789"
    assert plan.read_only is True
    assert "GET /media-789/insights" in plan.to_text()
    assert "No network calls were made" in plan.to_text()


def test_analytics_snapshot_cli_renders_local_snapshot_without_network(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    connection.execute(
        """
        insert into publish_attempts (
            draft_id, post_type, image_url, caption, container_id, published_media_id,
            status, status_code, image_urls_json, child_container_ids_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft.id,
            "carousel",
            public_urls[0],
            "Night market glow.",
            "carousel-123",
            "media-789",
            "published",
            "FINISHED",
            '["https://peddocks.net/post-relay/staging/drafts/1/media/01-market.jpg", "https://peddocks.net/post-relay/staging/drafts/1/media/02-lanterns.jpg"]',
            '["child-1", "child-2"]',
        ),
    )
    connection.execute("update drafts set status = ? where id = ?", (DraftState.POSTED.value, draft.id))
    connection.commit()
    connection.close()

    result = runner.invoke(
        app,
        [
            "analytics",
            "snapshot",
            "--post-id",
            str(draft.id),
            "--actual-published-at",
            "2026-05-19T10:02:30-04:00",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Post-publish analytics snapshot" in result.output
    assert "Published media ID: media-789" in result.output
    assert "Media dimensions:" in result.output
    assert "1080x1350" in result.output
    assert "No network calls were made" in result.output


def _insert_successful_publish_attempt(connection, draft, public_urls):
    connection.execute(
        """
        insert into publish_attempts (
            draft_id, post_type, image_url, caption, container_id, published_media_id,
            status, status_code, image_urls_json, child_container_ids_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft.id,
            "carousel",
            public_urls[0],
            "Night market glow.",
            "carousel-123",
            "media-789",
            "published",
            "FINISHED",
            '["https://peddocks.net/post-relay/staging/drafts/1/media/01-market.jpg", "https://peddocks.net/post-relay/staging/drafts/1/media/02-lanterns.jpg"]',
            '["child-1", "child-2"]',
        ),
    )
    connection.execute("update drafts set status = ? where id = ?", (DraftState.POSTED.value, draft.id))
    connection.commit()
    return record_published_post_snapshot(
        connection,
        draft.id,
        actual_published_at="2026-05-19T10:02:30-04:00",
    )


def test_meta_graph_client_fetches_media_insights_with_read_only_get():
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        return {
            "data": [
                {"name": "reach", "period": "lifetime", "values": [{"value": 420}]},
                {"name": "likes", "period": "lifetime", "values": [{"value": 37}]},
            ]
        }

    client = MetaGraphClient(MetaGraphConfig(access_token="secret-token"), transport=fake_transport)

    payload = client.get_media_insights("media-789", metrics=["reach", "likes"])

    assert payload["data"][0]["name"] == "reach"
    assert requested == [
        (
            "GET",
            "https://graph.facebook.com/v19.0/media-789/insights",
            {"metric": "reach,likes", "access_token": "secret-token"},
        )
    ]


def test_meta_graph_client_fetches_follower_metrics_with_read_only_get():
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        return {
            "id": "17841400498120050",
            "username": "andrewhml",
            "followers_count": 758,
            "follows_count": 611,
            "media_count": 208,
        }

    client = MetaGraphClient(MetaGraphConfig(access_token="secret-token"), transport=fake_transport)

    payload = client.get_instagram_account_metrics("17841400498120050")

    assert payload["followers_count"] == 758
    assert requested == [
        (
            "GET",
            "https://graph.facebook.com/v19.0/17841400498120050",
            {
                "fields": "id,username,followers_count,follows_count,media_count",
                "access_token": "secret-token",
            },
        )
    ]


def test_collect_and_store_media_insights_persists_read_only_metrics(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    _insert_successful_publish_attempt(connection, draft, public_urls)
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        return {
            "data": [
                {"name": "reach", "period": "lifetime", "values": [{"value": 420}]},
                {"name": "likes", "period": "lifetime", "values": [{"value": 37}]},
            ]
        }

    client = MetaGraphClient(MetaGraphConfig(access_token="secret-token"), transport=fake_transport)

    result = collect_and_store_media_insights(
        connection,
        draft.id,
        client=client,
        metrics=["reach", "likes"],
        collected_at="2026-05-20T10:00:00-04:00",
    )

    assert result.draft_id == draft.id
    assert result.published_media_id == "media-789"
    assert result.metrics == {"reach": 420, "likes": 37}
    assert result.collected_at == "2026-05-20T10:00:00-04:00"
    assert requested[0][0] == "GET"
    records = list_media_insight_snapshots(connection, draft.id)
    assert len(records) == 1
    assert records[0].metrics == {"reach": 420, "likes": 37}


def test_analytics_insights_fetch_requires_execute_before_meta_network(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    _insert_successful_publish_attempt(connection, draft, public_urls)
    connection.close()

    result = runner.invoke(
        app,
        [
            "analytics",
            "insights-fetch",
            "--post-id",
            str(draft.id),
            "--db",
            str(db_path),
            "--env-file",
            str(tmp_path / "missing.env"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Dry run only" in result.output
    assert "No Meta network calls were made" in result.output
    assert "--execute" in result.output


def test_analytics_insights_fetch_cli_execute_collects_and_stores_with_injected_client(tmp_path: Path, monkeypatch):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    _insert_successful_publish_attempt(connection, draft, public_urls)
    connection.close()

    class FakeClient:
        def get_media_insights(self, media_id, *, metrics):
            assert media_id == "media-789"
            assert list(metrics) == ["reach", "likes"]
            return {
                "data": [
                    {"name": "reach", "period": "lifetime", "values": [{"value": 420}]},
                    {"name": "likes", "period": "lifetime", "values": [{"value": 37}]},
                ]
            }

    monkeypatch.setattr("post_relay.cli.load_meta_graph_config", lambda env_file: MetaGraphConfig(access_token="secret-token"))
    monkeypatch.setattr("post_relay.cli.MetaGraphClient", lambda config: FakeClient())

    result = runner.invoke(
        app,
        [
            "analytics",
            "insights-fetch",
            "--post-id",
            str(draft.id),
            "--metric",
            "reach",
            "--metric",
            "likes",
            "--collected-at",
            "2026-05-20T10:00:00-04:00",
            "--execute",
            "--db",
            str(db_path),
            "--env-file",
            str(tmp_path / "private.env"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Read-only Instagram insights fetched" in result.output
    assert "Published media ID: media-789" in result.output
    assert "reach: 420" in result.output
    assert "likes: 37" in result.output
    assert "Publishing endpoints called: no" in result.output

    verify_connection = connect_db(db_path)
    initialize_db(verify_connection)
    records = list_media_insight_snapshots(verify_connection, draft.id)
    assert len(records) == 1
    assert records[0].metrics == {"reach": 420, "likes": 37}


def test_feedback_summary_combines_latest_insights_with_payload_features(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    _insert_successful_publish_attempt(connection, draft, public_urls)

    class FakeClient:
        def __init__(self, reach, likes):
            self.reach = reach
            self.likes = likes

        def get_media_insights(self, media_id, *, metrics):
            assert media_id == "media-789"
            return {
                "data": [
                    {"name": "reach", "period": "lifetime", "values": [{"value": self.reach}]},
                    {"name": "likes", "period": "lifetime", "values": [{"value": self.likes}]},
                ]
            }

    collect_and_store_media_insights(
        connection,
        draft.id,
        client=FakeClient(reach=300, likes=20),
        metrics=["reach", "likes"],
        collected_at="2026-05-20T09:00:00-04:00",
    )
    collect_and_store_media_insights(
        connection,
        draft.id,
        client=FakeClient(reach=420, likes=37),
        metrics=["reach", "likes"],
        collected_at="2026-05-20T10:00:00-04:00",
    )

    summary = build_feedback_summary(connection, draft_id=draft.id)
    rendered = render_feedback_summary(summary)

    assert len(summary.entries) == 1
    entry = summary.entries[0]
    assert entry.draft_id == draft.id
    assert entry.insight_metrics == {"reach": 420, "likes": 37}
    assert entry.media_count == 2
    assert entry.caption_character_count == len("Night market glow.")
    assert entry.hashtag_count == 0
    assert entry.aspect_ratio_class == "portrait_4x5"
    assert entry.minutes_from_schedule == 2
    assert entry.has_location_tag is False
    assert "Observed signals" in rendered
    assert "reach: 420" in rendered
    assert "Caption length: 18 characters" in rendered
    assert "Next-post suggestions" in rendered
    assert "advisory, not causal" in rendered


def test_feedback_summary_renders_payload_only_fallback_without_insights(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    _insert_successful_publish_attempt(connection, draft, public_urls)

    summary = build_feedback_summary(connection, draft_id=draft.id)
    rendered = render_feedback_summary(summary)

    assert summary.entries[0].insight_metrics == {}
    assert "No stored insight metrics yet" in rendered
    assert "analytics insights-fetch --post-id 1 --db data/post_relay.sqlite" in rendered
    assert "No Discord, R2, or Meta calls were made" in rendered


def test_feedback_summary_cli_is_local_only_and_does_not_mutate_state(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    _insert_successful_publish_attempt(connection, draft, public_urls)
    before_draft_status = get_draft(connection, draft.id).status
    connection.close()

    result = runner.invoke(
        app,
        [
            "analytics",
            "feedback-summary",
            "--post-id",
            str(draft.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Recommendation feedback summary" in result.output
    assert "Observed signals" in result.output
    assert "No Discord, R2, or Meta calls were made" in result.output

    verify_connection = connect_db(db_path)
    initialize_db(verify_connection)
    assert get_draft(verify_connection, draft.id).status == before_draft_status
    assert list_media_insight_snapshots(verify_connection, draft.id) == []


def test_follower_growth_plan_is_read_only_for_instagram_account():
    plan = build_follower_growth_plan("17841400498120050")

    assert plan.instagram_account_id == "17841400498120050"
    assert plan.read_only is True
    assert plan.endpoint == "/17841400498120050"
    assert plan.fields == ["id", "username", "followers_count", "follows_count", "media_count"]
    assert "GET /17841400498120050?fields=id,username,followers_count,follows_count,media_count" in plan.to_text()
    assert "No network calls were made" in plan.to_text()


def test_collect_and_store_follower_metrics_records_read_only_account_snapshot(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    requested = []

    class FakeClient:
        def get_instagram_account_metrics(self, instagram_account_id: str):
            requested.append(instagram_account_id)
            return {
                "id": instagram_account_id,
                "username": "andrewhml",
                "followers_count": 758,
                "follows_count": 611,
                "media_count": 208,
            }

    record = collect_and_store_follower_metrics(
        connection,
        "17841400498120050",
        client=FakeClient(),
        collected_at="2026-05-19T09:00:00-07:00",
    )

    assert requested == ["17841400498120050"]
    assert record.instagram_account_id == "17841400498120050"
    assert record.username == "andrewhml"
    assert record.follower_count == 758
    assert record.follows_count == 611
    assert record.media_count == 208
    assert record.collected_at == "2026-05-19T09:00:00-07:00"
    assert list_account_metric_snapshots(connection)[0].follower_count == 758


def test_follower_growth_summary_computes_progress_and_delta(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    class FakeClient:
        def __init__(self, payload):
            self.payload = payload

        def get_instagram_account_metrics(self, instagram_account_id: str):
            return dict(self.payload, id=instagram_account_id)

    collect_and_store_follower_metrics(
        connection,
        "17841400498120050",
        client=FakeClient({"username": "andrewhml", "followers_count": 758, "media_count": 206}),
        collected_at="2026-05-18T09:00:00-07:00",
    )
    collect_and_store_follower_metrics(
        connection,
        "17841400498120050",
        client=FakeClient({"username": "andrewhml", "followers_count": 763, "media_count": 208}),
        collected_at="2026-05-19T09:00:00-07:00",
    )

    summary = build_follower_growth_summary(connection, target_followers=5000)
    rendered = render_follower_growth_summary(summary)

    assert summary.current_follower_count == 763
    assert summary.previous_follower_count == 758
    assert summary.follower_delta == 5
    assert summary.remaining_to_target == 4237
    assert "Follower growth summary" in rendered
    assert "Current followers: 763" in rendered
    assert "Change from previous snapshot: +5" in rendered
    assert "Progress to 5,000: 763/5000" in rendered
    assert "No Discord, R2, Meta publish, or post lifecycle state changes" in rendered


def test_follower_fetch_cli_dry_run_makes_no_network_or_state_changes(tmp_path: Path):
    db_path = tmp_path / "post_relay.sqlite"
    connection = connect_db(db_path)
    initialize_db(connection)
    connection.close()

    result = runner.invoke(
        app,
        [
            "analytics",
            "follower-fetch",
            "--instagram-account-id",
            "17841400498120050",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Dry run only: read-only Instagram follower metrics fetch" in result.output
    assert "Endpoint: GET /17841400498120050" in result.output
    assert "No Meta network calls were made" in result.output
    verify_connection = connect_db(db_path)
    initialize_db(verify_connection)
    assert list_account_metric_snapshots(verify_connection) == []


def test_analytics_cadence_plan_lists_due_post_windows_and_weekly_account_check(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    _insert_successful_publish_attempt(connection, draft, public_urls)

    plan = build_analytics_cadence_plan(
        connection,
        now="2026-05-22T11:00:00-04:00",
        instagram_account_id="17841400498120050",
    )
    rendered = render_analytics_cadence_plan(plan)

    assert [window.label for window in plan.post_windows] == ["24h", "72h"]
    assert plan.post_windows[0].draft_id == draft.id
    assert plan.post_windows[0].due_at == "2026-05-20T10:02:30-04:00"
    assert plan.post_windows[0].command == (
        ".venv/bin/post-relay analytics insights-fetch --post-id 1 "
        "--metric reach --metric likes --metric comments --metric saved --metric shares "
        "--db data/post_relay.sqlite"
    )
    assert plan.account_due is not None
    assert plan.account_due.command == (
        ".venv/bin/post-relay analytics follower-fetch "
        "--instagram-account-id 17841400498120050 --db data/post_relay.sqlite"
    )
    assert "Post insight windows due: 2" in rendered
    assert "24h due 2026-05-20T10:02:30-04:00" in rendered
    assert "Account metrics due: yes" in rendered
    assert "No network calls were made" in rendered


def test_analytics_cadence_plan_skips_collected_windows_and_stops_after_14_days(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    _insert_successful_publish_attempt(connection, draft, public_urls)

    class FakeInsightsClient:
        def get_media_insights(self, media_id, *, metrics):
            return {"data": [{"name": "reach", "period": "lifetime", "values": [{"value": 420}]}]}

    collect_and_store_media_insights(
        connection,
        draft.id,
        client=FakeInsightsClient(),
        metrics=["reach"],
        collected_at="2026-05-20T10:30:00-04:00",
    )

    plan_during_window = build_analytics_cadence_plan(
        connection,
        now="2026-05-27T12:00:00-04:00",
        instagram_account_id="17841400498120050",
    )
    assert [window.label for window in plan_during_window.post_windows] == ["72h", "7d"]

    expired_plan = build_analytics_cadence_plan(
        connection,
        now="2026-06-05T12:00:00-04:00",
        instagram_account_id="17841400498120050",
    )
    assert expired_plan.post_windows == []
    assert "Post insight windows due: 0" in render_analytics_cadence_plan(expired_plan)


def test_analytics_cadence_plan_uses_weekly_account_cadence(tmp_path: Path):
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)

    class FakeAccountClient:
        def get_instagram_account_metrics(self, instagram_account_id: str):
            return {
                "id": instagram_account_id,
                "username": "andrewhml",
                "followers_count": 763,
                "media_count": 208,
            }

    collect_and_store_follower_metrics(
        connection,
        "17841400498120050",
        client=FakeAccountClient(),
        collected_at="2026-05-17T09:00:00-07:00",
    )

    not_due = build_analytics_cadence_plan(
        connection,
        now="2026-05-23T08:59:00-07:00",
        instagram_account_id="17841400498120050",
    )
    assert not_due.account_due is None

    due = build_analytics_cadence_plan(
        connection,
        now="2026-05-24T09:00:01-07:00",
        instagram_account_id="17841400498120050",
    )
    assert due.account_due is not None
    assert due.account_due.reason == "latest account snapshot is older than weekly cadence"


def test_analytics_cadence_plan_cli_is_no_network_and_state_safe(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    _insert_successful_publish_attempt(connection, draft, public_urls)
    connection.close()

    result = runner.invoke(
        app,
        [
            "analytics",
            "cadence-plan",
            "--now",
            "2026-05-22T11:00:00-04:00",
            "--instagram-account-id",
            "17841400498120050",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Analytics cadence plan" in result.output
    assert "Post insight windows due: 2" in result.output
    assert "analytics insights-fetch --post-id 1" in result.output
    assert f"--db {db_path.as_posix()}" in result.output
    assert "analytics follower-fetch --instagram-account-id 17841400498120050" in result.output
    assert "No Meta network calls were made" in result.output

    verify_connection = connect_db(db_path)
    initialize_db(verify_connection)
    assert list_media_insight_snapshots(verify_connection, draft.id) == []
    assert list_account_metric_snapshots(verify_connection) == []


def test_collect_due_analytics_fetches_once_per_due_post_and_account(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    _insert_successful_publish_attempt(connection, draft, public_urls)
    requested_media = []
    requested_accounts = []

    class FakeClient:
        def get_media_insights(self, media_id, *, metrics):
            requested_media.append((media_id, list(metrics)))
            return {
                "data": [
                    {"name": "reach", "period": "lifetime", "values": [{"value": 420}]},
                    {"name": "likes", "period": "lifetime", "values": [{"value": 37}]},
                ]
            }

        def get_instagram_account_metrics(self, instagram_account_id: str):
            requested_accounts.append(instagram_account_id)
            return {
                "id": instagram_account_id,
                "username": "andrewhml",
                "followers_count": 763,
                "media_count": 208,
            }

    result = collect_and_store_due_analytics(
        connection,
        now="2026-05-22T11:00:00-04:00",
        instagram_account_id="17841400498120050",
        client=FakeClient(),
    )

    assert requested_media == [("media-789", ["reach", "likes", "comments", "saved", "shares"])]
    assert requested_accounts == ["17841400498120050"]
    assert [record.draft_id for record in result.media_records] == [draft.id]
    assert result.media_records[0].collected_at == "2026-05-22T11:00:00-04:00"
    assert result.account_record is not None
    assert result.account_record.collected_at == "2026-05-22T11:00:00-04:00"

    follow_up_plan = build_analytics_cadence_plan(
        connection,
        now="2026-05-22T11:01:00-04:00",
        instagram_account_id="17841400498120050",
    )
    assert follow_up_plan.post_windows == []
    assert follow_up_plan.account_due is None


def test_analytics_collect_due_dry_run_makes_no_network_or_state_changes(tmp_path: Path):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    _insert_successful_publish_attempt(connection, draft, public_urls)
    connection.close()

    result = runner.invoke(
        app,
        [
            "analytics",
            "collect-due",
            "--now",
            "2026-05-22T11:00:00-04:00",
            "--instagram-account-id",
            "17841400498120050",
            "--db",
            str(db_path),
            "--env-file",
            str(tmp_path / "missing.env"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Dry run only: due analytics collection" in result.output
    assert "Post insight windows due: 2" in result.output
    assert "No Meta network calls were made" in result.output
    assert "--execute" in result.output

    verify_connection = connect_db(db_path)
    initialize_db(verify_connection)
    assert list_media_insight_snapshots(verify_connection, draft.id) == []
    assert list_account_metric_snapshots(verify_connection) == []


def test_analytics_collect_due_execute_collects_due_read_only_metrics(tmp_path: Path, monkeypatch):
    connection, draft, public_urls = _build_ready_carousel_with_exported_staged_media(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    _insert_successful_publish_attempt(connection, draft, public_urls)
    connection.close()
    requested_media = []
    requested_accounts = []

    class FakeClient:
        def get_media_insights(self, media_id, *, metrics):
            requested_media.append((media_id, list(metrics)))
            return {"data": [{"name": "reach", "period": "lifetime", "values": [{"value": 420}]}]}

        def get_instagram_account_metrics(self, instagram_account_id: str):
            requested_accounts.append(instagram_account_id)
            return {
                "id": instagram_account_id,
                "username": "andrewhml",
                "followers_count": 763,
                "media_count": 208,
            }

    monkeypatch.setattr("post_relay.cli.load_meta_graph_config", lambda env_file: MetaGraphConfig(access_token="secret-token"))
    monkeypatch.setattr("post_relay.cli.MetaGraphClient", lambda config: FakeClient())

    result = runner.invoke(
        app,
        [
            "analytics",
            "collect-due",
            "--now",
            "2026-05-22T11:00:00-04:00",
            "--instagram-account-id",
            "17841400498120050",
            "--execute",
            "--db",
            str(db_path),
            "--env-file",
            str(tmp_path / "private.env"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Due analytics collected" in result.output
    assert "Post insight snapshots stored: 1" in result.output
    assert "Account metric snapshot stored: yes" in result.output
    assert "Publishing endpoints called: no" in result.output
    assert requested_media == [("media-789", ["reach", "likes", "comments", "saved", "shares"])]
    assert requested_accounts == ["17841400498120050"]

    verify_connection = connect_db(db_path)
    initialize_db(verify_connection)
    assert len(list_media_insight_snapshots(verify_connection, draft.id)) == 1
    assert len(list_account_metric_snapshots(verify_connection)) == 1
