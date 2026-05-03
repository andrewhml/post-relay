from pathlib import Path

import pytest

from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.meta_graph import MetaGraphClient, MetaGraphConfig
from post_relay.publishing import (
    DraftNotReadyForImagePublish,
    UnsupportedPublishDraft,
    execute_single_image_publish_validation,
    prepare_single_image_publish_validation,
)
from post_relay.repository import get_draft, list_candidate_groups, list_publish_attempts
from post_relay.scheduling import (
    approve_draft_for_publishing,
    request_publish_approval,
    schedule_draft,
)
from post_relay.state import DraftState


def _build_single_image_ready_draft(tmp_path: Path, *, caption: str = "A quiet test post."):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
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
        "update drafts set caption = ?, status = ? where id = ?",
        (caption, DraftState.DRAFTING.value, draft.id),
    )
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")
    request_publish_approval(connection, draft.id)
    approve_draft_for_publishing(connection, draft.id, approved_by="andrew")
    return connection, get_draft(connection, draft.id)


def test_prepare_single_image_publish_validation_requires_ready_single_image_draft(tmp_path: Path):
    connection, draft = _build_single_image_ready_draft(tmp_path)
    connection.execute(
        "update drafts set status = ? where id = ?",
        (DraftState.AWAITING_PUBLISH_APPROVAL.value, draft.id),
    )

    with pytest.raises(DraftNotReadyForImagePublish):
        prepare_single_image_publish_validation(
            connection,
            draft.id,
            image_url="https://example.com/test-image.jpg",
        )

    connection.execute(
        "update drafts set status = ?, post_type = ? where id = ?",
        (DraftState.READY_TO_PUBLISH.value, "carousel", draft.id),
    )

    with pytest.raises(UnsupportedPublishDraft):
        prepare_single_image_publish_validation(
            connection,
            draft.id,
            image_url="https://example.com/test-image.jpg",
        )


def test_prepare_single_image_publish_validation_records_sanitized_dry_run_attempt(tmp_path: Path):
    connection, draft = _build_single_image_ready_draft(tmp_path, caption="Temple morning.")

    result = prepare_single_image_publish_validation(
        connection,
        draft.id,
        image_url="https://example.com/test-image.jpg?token=abc123",
    )

    assert result.status == "planned"
    assert result.container_id is None
    assert result.published_media_id is None
    assert result.to_text().startswith("Single-image publish validation")
    assert "https://example.com/test-image.jpg?token=<redacted>" in result.to_text()
    attempts = list_publish_attempts(connection, draft.id)
    assert len(attempts) == 1
    assert attempts[0].status == "planned"
    assert attempts[0].image_url == "https://example.com/test-image.jpg?token=<redacted>"
    assert attempts[0].caption == "Temple morning."


def test_execute_single_image_publish_validation_creates_polls_and_publishes_after_approval(tmp_path: Path):
    connection, draft = _build_single_image_ready_draft(tmp_path, caption="Temple morning.")
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        if url.endswith("/17841400498120050/media"):
            return {"id": "creation-123"}
        if url.endswith("/creation-123"):
            return {"id": "creation-123", "status_code": "FINISHED"}
        if url.endswith("/17841400498120050/media_publish"):
            return {"id": "media-456"}
        raise AssertionError(f"unexpected URL: {url}")

    client = MetaGraphClient(
        MetaGraphConfig(
            access_token="secret-token",
            instagram_account_id="17841400498120050",
        ),
        transport=fake_transport,
    )

    result = execute_single_image_publish_validation(
        connection,
        draft.id,
        image_url="https://example.com/test-image.jpg",
        client=client,
    )

    assert result.status == "published"
    assert result.container_id == "creation-123"
    assert result.status_code == "FINISHED"
    assert result.published_media_id == "media-456"
    assert get_draft(connection, draft.id).status == DraftState.POSTED.value
    assert [method for method, _url, _params in requested] == ["POST", "GET", "POST"]
    assert [url for _method, url, _params in requested] == [
        "https://graph.facebook.com/v19.0/17841400498120050/media",
        "https://graph.facebook.com/v19.0/creation-123",
        "https://graph.facebook.com/v19.0/17841400498120050/media_publish",
    ]
    assert requested[0][2]["image_url"] == "https://example.com/test-image.jpg"
    assert requested[0][2]["caption"] == "Temple morning."
    assert requested[1][2]["fields"] == "id,status_code"
    assert requested[2][2]["creation_id"] == "creation-123"
    assert all(params["access_token"] == "secret-token" for _method, _url, params in requested)
    attempts = list_publish_attempts(connection, draft.id)
    assert attempts[0].container_id == "creation-123"
    assert attempts[0].published_media_id == "media-456"
    assert attempts[0].status == "published"
