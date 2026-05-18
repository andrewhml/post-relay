from pathlib import Path

import pytest

from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig, R2StagingConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.indexer import index_photo_sources
from post_relay.meta_graph import MetaGraphClient, MetaGraphConfig
from post_relay.publishing import (
    DraftNotReadyForImagePublish,
    PublishValidationError,
    UnsupportedPublishDraft,
    execute_carousel_publish_validation,
    execute_single_image_publish_validation,
    prepare_carousel_publish_validation,
    prepare_single_image_publish_validation,
    resolve_staged_r2_publish_image_urls,
)
from post_relay.repository import (
    create_r2_staged_object_record,
    get_draft,
    list_candidate_group_photo_paths,
    list_candidate_groups,
    list_publish_attempts,
    update_draft_content,
)
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


def _build_carousel_ready_draft(tmp_path: Path, *, caption: str = "A quiet carousel."):
    root = tmp_path / "processed"
    folder = root / "2023" / "kyoto"
    folder.mkdir(parents=True)
    (folder / "temple.jpg").write_bytes(b"fake image")
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


def test_execute_single_image_publish_validation_refuses_before_scheduled_time_without_network_calls(tmp_path: Path):
    connection, draft = _build_single_image_ready_draft(tmp_path, caption="Temple morning.")
    requested = []

    client = MetaGraphClient(
        MetaGraphConfig(access_token="secret-token", instagram_account_id="17841400498120050"),
        transport=lambda method, url, params: requested.append((method, url, dict(params))) or {"id": "unexpected"},
    )

    with pytest.raises(PublishValidationError) as error:
        execute_single_image_publish_validation(
            connection,
            draft.id,
            image_url="https://example.com/test-image.jpg",
            client=client,
            now="2026-05-05T08:30:00-07:00",
        )

    assert "scheduled for 2026-05-05T09:30:00-07:00" in str(error.value)
    assert "Current time: 2026-05-05T08:30:00-07:00" in str(error.value)
    assert "--publish-now" in str(error.value)
    assert requested == []
    assert get_draft(connection, draft.id).status == DraftState.READY_TO_PUBLISH.value
    assert list_publish_attempts(connection, draft.id) == []


def test_execute_carousel_publish_validation_allows_explicit_publish_now_before_schedule(tmp_path: Path):
    connection, draft = _build_carousel_ready_draft(tmp_path, caption="Kyoto garden sequence.")
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        media_url = "https://graph.facebook.com/v19.0/17841400498120050/media"
        if url == media_url and params.get("image_url") == "https://example.com/temple.jpg":
            return {"id": "child-1"}
        if url == media_url and params.get("image_url") == "https://example.com/garden.jpg":
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

    result = execute_carousel_publish_validation(
        connection,
        draft.id,
        image_urls=["https://example.com/temple.jpg", "https://example.com/garden.jpg"],
        client=client,
        now="2026-05-05T08:30:00-07:00",
        publish_now=True,
    )

    assert result.status == "published"
    assert get_draft(connection, draft.id).status == DraftState.POSTED.value
    assert [method for method, _url, _params in requested] == ["POST", "POST", "POST", "GET", "POST"]


def test_execute_single_image_publish_validation_rejects_invalid_schedule_timestamp(tmp_path: Path):
    connection, draft = _build_single_image_ready_draft(tmp_path, caption="Temple morning.")
    connection.execute(
        "update drafts set scheduled_for = ? where id = ?",
        ("not-a-date", draft.id),
    )
    requested = []
    client = MetaGraphClient(
        MetaGraphConfig(access_token="secret-token", instagram_account_id="17841400498120050"),
        transport=lambda method, url, params: requested.append((method, url, dict(params))) or {"id": "unexpected"},
    )

    with pytest.raises(PublishValidationError) as error:
        execute_single_image_publish_validation(
            connection,
            draft.id,
            image_url="https://example.com/test-image.jpg",
            client=client,
            now="2026-05-05T09:30:00-07:00",
        )

    assert "Invalid scheduled_for timestamp" in str(error.value)
    assert requested == []


def test_execute_single_image_publish_validation_sends_hashtags_inside_meta_caption(tmp_path: Path):
    connection, draft = _build_single_image_ready_draft(tmp_path, caption="Temple morning.")
    update_draft_content(
        connection,
        draft.id,
        hashtags=["#travelphotography", "#Kyoto"],
        location_text="Kyoto, Japan",
        alt_text="Review-only accessibility note",
    )
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
        MetaGraphConfig(access_token="secret-token", instagram_account_id="17841400498120050"),
        transport=fake_transport,
    )

    result = execute_single_image_publish_validation(
        connection,
        draft.id,
        image_url="https://example.com/test-image.jpg",
        client=client,
    )

    assert result.caption == "Temple morning.\n\n#travelphotography #Kyoto"
    media_params = requested[0][2]
    assert media_params["caption"] == "Temple morning.\n\n#travelphotography #Kyoto"
    assert "location_id" not in media_params
    assert "alt_text" not in media_params
    assert list_publish_attempts(connection, draft.id)[0].caption == "Temple morning.\n\n#travelphotography #Kyoto"



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


def test_prepare_carousel_publish_validation_records_sanitized_dry_run_attempt(tmp_path: Path):
    connection, draft = _build_carousel_ready_draft(tmp_path, caption="Kyoto garden sequence.")

    result = prepare_carousel_publish_validation(
        connection,
        draft.id,
        image_urls=[
            "https://example.com/temple.jpg?token=abc123",
            "https://example.com/garden.jpg?signature=def456",
        ],
    )

    assert result.status == "planned"
    assert result.image_urls == [
        "https://example.com/temple.jpg?token=<redacted>",
        "https://example.com/garden.jpg?signature=<redacted>",
    ]
    assert result.container_id is None
    assert result.child_container_ids == []
    assert result.to_text().startswith("Carousel publish validation")
    attempts = list_publish_attempts(connection, draft.id)
    assert len(attempts) == 1
    assert attempts[0].post_type == "carousel"
    assert attempts[0].status == "planned"
    assert attempts[0].image_urls == result.image_urls
    assert attempts[0].child_container_ids == []
    assert attempts[0].caption == "Kyoto garden sequence."


def test_resolve_staged_r2_publish_image_urls_handles_single_image_draft(tmp_path: Path):
    connection, draft = _build_single_image_ready_draft(tmp_path, caption="Temple morning.")
    selected_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    r2_config = R2StagingConfig(
        enabled=True,
        bucket="post-relay-publish",
        public_base_url="https://peddocks.net",
        prefix="post-relay/staging",
    )
    create_r2_staged_object_record(
        connection,
        draft_id=draft.id,
        kind="draft_media",
        source_path=selected_paths[0],
        bucket="post-relay-publish",
        object_key="post-relay/staging/drafts/1/media/01-temple.jpg",
        public_url="https://peddocks.net/post-relay/staging/drafts/1/media/01-temple.jpg",
    )

    result = prepare_single_image_publish_validation(
        connection,
        draft.id,
        image_url=resolve_staged_r2_publish_image_urls(connection, draft.id, r2_config)[0],
    )

    assert result.image_url == "https://peddocks.net/post-relay/staging/drafts/1/media/01-temple.jpg"
    assert list_publish_attempts(connection, draft.id)[0].image_url == result.image_url


def test_resolve_staged_r2_publish_image_urls_preserves_selected_media_order(tmp_path: Path):
    connection, draft = _build_carousel_ready_draft(tmp_path, caption="Kyoto garden sequence.")
    selected_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    r2_config = R2StagingConfig(
        enabled=True,
        bucket="post-relay-publish",
        public_base_url="https://peddocks.net",
        prefix="post-relay/staging",
    )
    create_r2_staged_object_record(
        connection,
        draft_id=draft.id,
        kind="draft_media",
        source_path=selected_paths[1],
        bucket="post-relay-publish",
        object_key="post-relay/staging/drafts/1/media/02-garden.jpg",
        public_url="https://peddocks.net/post-relay/staging/drafts/1/media/02-garden.jpg?token=secret",
    )
    create_r2_staged_object_record(
        connection,
        draft_id=draft.id,
        kind="draft_media",
        source_path=selected_paths[0],
        bucket="post-relay-publish",
        object_key="post-relay/staging/drafts/1/media/01-temple.jpg",
        public_url="https://peddocks.net/post-relay/staging/drafts/1/media/01-temple.jpg?signature=secret",
    )
    create_r2_staged_object_record(
        connection,
        draft_id=draft.id,
        kind="contact_sheet",
        source_path="/tmp/contact-sheet.jpg",
        bucket="post-relay-publish",
        object_key="post-relay/staging/drafts/1/artifacts/contact-sheet.jpg",
        public_url="https://peddocks.net/post-relay/staging/drafts/1/artifacts/contact-sheet.jpg",
    )

    urls = resolve_staged_r2_publish_image_urls(connection, draft.id, r2_config)

    assert urls == [
        "https://peddocks.net/post-relay/staging/drafts/1/media/01-temple.jpg?signature=secret",
        "https://peddocks.net/post-relay/staging/drafts/1/media/02-garden.jpg?token=secret",
    ]


def test_resolve_staged_r2_publish_image_urls_requires_uploaded_media_for_each_selected_photo(tmp_path: Path):
    connection, draft = _build_carousel_ready_draft(tmp_path, caption="Kyoto garden sequence.")
    selected_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    r2_config = R2StagingConfig(
        enabled=True,
        bucket="post-relay-publish",
        public_base_url="https://peddocks.net",
        prefix="post-relay/staging",
    )
    create_r2_staged_object_record(
        connection,
        draft_id=draft.id,
        kind="draft_media",
        source_path=selected_paths[0],
        bucket="post-relay-publish",
        object_key="post-relay/staging/drafts/1/media/01-temple.jpg",
        public_url="https://peddocks.net/post-relay/staging/drafts/1/media/01-temple.jpg",
    )

    with pytest.raises(UnsupportedPublishDraft, match="staged R2 media"):
        resolve_staged_r2_publish_image_urls(connection, draft.id, r2_config)


def test_prepare_carousel_publish_validation_uses_staged_r2_urls(tmp_path: Path):
    connection, draft = _build_carousel_ready_draft(tmp_path, caption="Kyoto garden sequence.")
    selected_paths = list_candidate_group_photo_paths(connection, draft.candidate_group_id)
    r2_config = R2StagingConfig(
        enabled=True,
        bucket="post-relay-publish",
        public_base_url="https://peddocks.net",
        prefix="post-relay/staging",
    )
    for index, source_path in enumerate(selected_paths, start=1):
        create_r2_staged_object_record(
            connection,
            draft_id=draft.id,
            kind="draft_media",
            source_path=source_path,
            bucket="post-relay-publish",
            object_key=f"post-relay/staging/drafts/1/media/{index:02d}-image.jpg",
            public_url=f"https://peddocks.net/post-relay/staging/drafts/1/media/{index:02d}-image.jpg?token=secret",
        )

    urls = resolve_staged_r2_publish_image_urls(connection, draft.id, r2_config)
    result = prepare_carousel_publish_validation(connection, draft.id, image_urls=urls)

    assert result.image_urls == [
        "https://peddocks.net/post-relay/staging/drafts/1/media/01-image.jpg?token=<redacted>",
        "https://peddocks.net/post-relay/staging/drafts/1/media/02-image.jpg?token=<redacted>",
    ]
    attempts = list_publish_attempts(connection, draft.id)
    assert attempts[0].image_urls == result.image_urls


def test_execute_carousel_publish_validation_creates_child_and_carousel_containers_then_publishes(tmp_path: Path):
    connection, draft = _build_carousel_ready_draft(tmp_path, caption="Kyoto garden sequence.")
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        media_url = "https://graph.facebook.com/v19.0/17841400498120050/media"
        if url == media_url and params.get("image_url") == "https://example.com/temple.jpg":
            return {"id": "child-1"}
        if url == media_url and params.get("image_url") == "https://example.com/garden.jpg":
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

    result = execute_carousel_publish_validation(
        connection,
        draft.id,
        image_urls=["https://example.com/temple.jpg", "https://example.com/garden.jpg"],
        client=client,
    )

    assert result.status == "published"
    assert result.child_container_ids == ["child-1", "child-2"]
    assert result.container_id == "carousel-123"
    assert result.status_code == "FINISHED"
    assert result.published_media_id == "media-789"
    assert get_draft(connection, draft.id).status == DraftState.POSTED.value
    assert [method for method, _url, _params in requested] == ["POST", "POST", "POST", "GET", "POST"]
    assert requested[0][2]["is_carousel_item"] == "true"
    assert requested[1][2]["is_carousel_item"] == "true"
    assert requested[2][2]["media_type"] == "CAROUSEL"
    assert requested[2][2]["children"] == "child-1,child-2"
    assert requested[2][2]["caption"] == "Kyoto garden sequence."
    assert requested[3][2]["fields"] == "id,status_code"
    assert requested[4][2]["creation_id"] == "carousel-123"
    assert all(params["access_token"] == "secret-token" for _method, _url, params in requested)
    attempts = list_publish_attempts(connection, draft.id)
    assert attempts[0].child_container_ids == ["child-1", "child-2"]
    assert attempts[0].container_id == "carousel-123"
    assert attempts[0].published_media_id == "media-789"
    assert attempts[0].status == "published"


def test_single_image_publish_request_excludes_review_only_metadata(tmp_path: Path):
    connection, draft = _build_single_image_ready_draft(tmp_path, caption="Temple morning.")
    update_draft_content(
        connection,
        draft.id,
        location_text="Kyoto, Japan",
        alt_text="Review-only accessibility note",
    )
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
        MetaGraphConfig(access_token="secret-token", instagram_account_id="17841400498120050"),
        transport=fake_transport,
    )

    execute_single_image_publish_validation(
        connection,
        draft.id,
        image_url="https://example.com/test-image.jpg",
        client=client,
    )

    media_params = requested[0][2]
    assert media_params["image_url"] == "https://example.com/test-image.jpg"
    assert media_params["caption"] == "Temple morning."
    assert "alt_text" not in media_params
    assert "location_id" not in media_params
    assert "collaborators" not in media_params


def test_carousel_publish_request_excludes_review_only_metadata(tmp_path: Path):
    connection, draft = _build_carousel_ready_draft(tmp_path, caption="Kyoto garden sequence.")
    update_draft_content(
        connection,
        draft.id,
        location_text="Kyoto, Japan",
        alt_text="Review-only accessibility note",
    )
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        media_url = "https://graph.facebook.com/v19.0/17841400498120050/media"
        if url == media_url and params.get("image_url") == "https://example.com/temple.jpg":
            return {"id": "child-1"}
        if url == media_url and params.get("image_url") == "https://example.com/garden.jpg":
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
        image_urls=["https://example.com/temple.jpg", "https://example.com/garden.jpg"],
        client=client,
    )

    media_requests = [params for _method, url, params in requested if url.endswith("/17841400498120050/media")]
    assert len(media_requests) == 3
    for params in media_requests:
        assert "alt_text" not in params
        assert "location_id" not in params
        assert "collaborators" not in params
    assert media_requests[2]["caption"] == "Kyoto garden sequence."


def test_execute_carousel_publish_validation_sends_hashtags_inside_parent_caption_only(tmp_path: Path):
    connection, draft = _build_carousel_ready_draft(tmp_path, caption="Kyoto garden sequence.")
    update_draft_content(
        connection,
        draft.id,
        hashtags=["#travelphotography", "#Kyoto"],
        location_text="Kyoto, Japan",
        alt_text="Review-only accessibility note",
    )
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        media_url = "https://graph.facebook.com/v19.0/17841400498120050/media"
        if url == media_url and params.get("image_url") == "https://example.com/temple.jpg":
            return {"id": "child-1"}
        if url == media_url and params.get("image_url") == "https://example.com/garden.jpg":
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

    result = execute_carousel_publish_validation(
        connection,
        draft.id,
        image_urls=["https://example.com/temple.jpg", "https://example.com/garden.jpg"],
        client=client,
    )

    assert result.caption == "Kyoto garden sequence.\n\n#travelphotography #Kyoto"
    media_requests = [params for _method, url, params in requested if url.endswith("/17841400498120050/media")]
    assert "caption" not in media_requests[0]
    assert "caption" not in media_requests[1]
    assert media_requests[2]["caption"] == "Kyoto garden sequence.\n\n#travelphotography #Kyoto"
    assert "location_id" not in media_requests[2]
    assert list_publish_attempts(connection, draft.id)[0].caption == "Kyoto garden sequence.\n\n#travelphotography #Kyoto"
