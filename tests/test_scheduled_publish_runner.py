from pathlib import Path

import pytest

from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig, R2StagingConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.meta_graph import MetaGraphClient, MetaGraphConfig
from post_relay.repository import (
    create_r2_staged_object_record,
    get_draft,
    invalidate_active_approvals,
    list_candidate_group_photo_paths,
    list_candidate_groups,
    list_publish_attempts,
)
from post_relay.scheduled_publish_runner import (
    ScheduledPublishNotReady,
    execute_due_scheduled_publish,
    preflight_due_scheduled_publish,
)
from post_relay.scheduling import (
    approve_draft_for_publishing,
    request_publish_approval,
    schedule_draft,
)
from post_relay.state import DraftState


def _build_ready_draft(tmp_path: Path, *, post_type: str = "carousel"):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
    if post_type == "carousel":
        (folder / "garden.jpg").write_bytes(b"fake image")
    connection = connect_db(tmp_path / "post_relay.sqlite")
    initialize_db(connection)
    config = PostRelayConfig(
        photo_sources=[PhotoSource(name="processed", root=root, source_type="processed_folder")]
    )
    index_photo_sources(connection, config)
    build_candidate_groups(connection)
    candidate = list_candidate_groups(connection)[0]
    draft = create_draft_from_candidate(connection, candidate.id)
    connection.execute(
        "update drafts set caption = ?, status = ?, post_type = ? where id = ?",
        ("A scheduled post.", DraftState.DRAFTING.value, post_type, draft.id),
    )
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")
    request_publish_approval(connection, draft.id)
    approve_draft_for_publishing(connection, draft.id, approved_by="andrew")
    r2_config = R2StagingConfig(
        enabled=True,
        bucket="post-relay-publish",
        public_base_url="https://peddocks.net",
        prefix="post-relay/staging",
    )
    for index, source_path in enumerate(list_candidate_group_photo_paths(connection, draft.candidate_group_id), start=1):
        create_r2_staged_object_record(
            connection,
            draft_id=draft.id,
            kind="draft_media",
            source_path=source_path,
            bucket="post-relay-publish",
            object_key=f"post-relay/staging/drafts/{draft.id}/media/{index:02d}-image.jpg",
            public_url=f"https://peddocks.net/post-relay/staging/drafts/{draft.id}/media/{index:02d}-image.jpg?token=secret",
        )
    connection.commit()
    return connection, get_draft(connection, draft.id), r2_config


def test_preflight_due_scheduled_publish_refuses_before_schedule_without_publish_attempt(tmp_path: Path):
    connection, draft, r2_config = _build_ready_draft(tmp_path)

    with pytest.raises(ScheduledPublishNotReady) as error:
        preflight_due_scheduled_publish(
            connection,
            draft.id,
            r2_config=r2_config,
            now="2026-05-05T08:30:00-07:00",
        )

    assert "scheduled for 2026-05-05T09:30:00-07:00" in str(error.value)
    assert "not due until" in str(error.value)
    assert get_draft(connection, draft.id).status == DraftState.READY_TO_PUBLISH.value
    assert list_publish_attempts(connection, draft.id) == []


def test_preflight_due_scheduled_publish_requires_valid_scheduled_for(tmp_path: Path):
    connection, draft, r2_config = _build_ready_draft(tmp_path)
    connection.execute("update drafts set scheduled_for = null where id = ?", (draft.id,))

    with pytest.raises(ScheduledPublishNotReady, match="scheduled_for"):
        preflight_due_scheduled_publish(
            connection,
            draft.id,
            r2_config=r2_config,
            now="2026-05-05T09:30:00-07:00",
        )

    connection.execute("update drafts set scheduled_for = ? where id = ?", ("not-a-date", draft.id))

    with pytest.raises(ScheduledPublishNotReady, match="Invalid scheduled_for timestamp"):
        preflight_due_scheduled_publish(
            connection,
            draft.id,
            r2_config=r2_config,
            now="2026-05-05T09:30:00-07:00",
        )


def test_preflight_due_scheduled_publish_requires_active_draft_and_publish_approvals(tmp_path: Path):
    connection, draft, r2_config = _build_ready_draft(tmp_path)
    invalidate_active_approvals(connection, draft.id, reason="test edit")
    connection.commit()

    with pytest.raises(ScheduledPublishNotReady) as error:
        preflight_due_scheduled_publish(
            connection,
            draft.id,
            r2_config=r2_config,
            now="2026-05-05T09:30:00-07:00",
        )

    assert "active draft and publish approvals" in str(error.value)
    assert list_publish_attempts(connection, draft.id) == []


def test_preflight_due_scheduled_publish_requires_complete_uploaded_staged_r2_media(tmp_path: Path):
    connection, draft, r2_config = _build_ready_draft(tmp_path)
    connection.execute("delete from r2_staged_objects where id = (select max(id) from r2_staged_objects)")
    connection.commit()

    with pytest.raises(ScheduledPublishNotReady) as error:
        preflight_due_scheduled_publish(
            connection,
            draft.id,
            r2_config=r2_config,
            now="2026-05-05T09:30:00-07:00",
        )

    assert "staged R2 media" in str(error.value)
    assert list_publish_attempts(connection, draft.id) == []


def test_preflight_due_scheduled_publish_reports_due_plan_without_network_or_attempt(tmp_path: Path):
    connection, draft, r2_config = _build_ready_draft(tmp_path)

    result = preflight_due_scheduled_publish(
        connection,
        draft.id,
        r2_config=r2_config,
        now="2026-05-05T09:31:00-07:00",
    )

    assert result.ready is True
    assert result.post_type == "carousel"
    assert result.image_urls == [
        "https://peddocks.net/post-relay/staging/drafts/1/media/01-image.jpg?token=<redacted>",
        "https://peddocks.net/post-relay/staging/drafts/1/media/02-image.jpg?token=<redacted>",
    ]
    assert "No Meta publishing endpoints were called." in result.to_text()
    assert "secret" not in result.to_text()
    assert list_publish_attempts(connection, draft.id) == []


def test_execute_due_scheduled_publish_runs_existing_guarded_carousel_execute_when_due(tmp_path: Path):
    connection, draft, r2_config = _build_ready_draft(tmp_path)
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        media_url = "https://graph.facebook.com/v19.0/17841400498120050/media"
        if url == media_url and params.get("image_url") == "https://peddocks.net/post-relay/staging/drafts/1/media/01-image.jpg?token=secret":
            return {"id": "child-1"}
        if url == media_url and params.get("image_url") == "https://peddocks.net/post-relay/staging/drafts/1/media/02-image.jpg?token=secret":
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

    result = execute_due_scheduled_publish(
        connection,
        draft.id,
        r2_config=r2_config,
        client=client,
        now="2026-05-05T09:31:00-07:00",
    )

    assert result.status == "published"
    assert get_draft(connection, draft.id).status == DraftState.POSTED.value
    assert [method for method, _url, _params in requested] == ["POST", "POST", "POST", "GET", "POST"]


def test_execute_due_scheduled_publish_refuses_before_schedule_without_network(tmp_path: Path):
    connection, draft, r2_config = _build_ready_draft(tmp_path)
    requested = []
    client = MetaGraphClient(
        MetaGraphConfig(access_token="secret-token", instagram_account_id="17841400498120050"),
        transport=lambda method, url, params: requested.append((method, url, dict(params))) or {"id": "unexpected"},
    )

    with pytest.raises(ScheduledPublishNotReady):
        execute_due_scheduled_publish(
            connection,
            draft.id,
            r2_config=r2_config,
            client=client,
            now="2026-05-05T08:30:00-07:00",
        )

    assert requested == []
    assert get_draft(connection, draft.id).status == DraftState.READY_TO_PUBLISH.value
    assert list_publish_attempts(connection, draft.id) == []
