from pathlib import Path

from typer.testing import CliRunner

from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.cli import app
from post_relay.config import PhotoSource, PostRelayConfig, R2StagingConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.final_publish_preview import build_final_publish_preview
from post_relay.indexer import index_photo_sources
from post_relay.location_tags import (
    build_location_candidate_review,
    search_location_pages,
    set_draft_location_tag,
)
from post_relay.meta_graph import MetaGraphClient, MetaGraphConfig
from post_relay.publishing import execute_carousel_publish_validation
from post_relay.repository import (
    create_r2_staged_object_record,
    get_draft,
    get_draft_location_tag,
    list_active_approvals,
    list_candidate_group_photo_paths,
    list_candidate_groups,
)
from post_relay.scheduling import approve_draft_for_publishing, request_publish_approval, schedule_draft
from post_relay.state import DraftState


runner = CliRunner()


def _build_ready_carousel(tmp_path: Path):
    root = tmp_path / "processed"
    folder = root / "2025" / "seoul"
    folder.mkdir(parents=True)
    (folder / "market.jpg").write_bytes(b"fake image")
    (folder / "lanterns.jpg").write_bytes(b"fake image")
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
        ("Night market glow.", DraftState.DRAFTING.value, draft.id),
    )
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")
    request_publish_approval(connection, draft.id)
    approve_draft_for_publishing(connection, draft.id, approved_by="andrew")
    return connection, get_draft(connection, draft.id), candidate


def test_location_candidate_review_asks_for_specific_place_before_searching_vague_context(tmp_path: Path):
    connection, draft, _candidate = _build_ready_carousel(tmp_path)
    connection.execute(
        "update drafts set location_text = ? where id = ?",
        ("Seoul, South Korea", draft.id),
    )
    connection.commit()

    review = build_location_candidate_review(connection, draft.id)

    assert review.status == "needs_clarification"
    assert review.candidates == []
    rendered = review.to_text()
    assert "Need a more specific location before searching Meta Pages" in rendered
    assert "Seoul, South Korea" in rendered
    assert "specific market/venue" in rendered
    assert "No Meta network calls were made." in rendered


def test_location_candidate_review_searches_and_ranks_user_confirmed_query(tmp_path: Path):
    connection, draft, _candidate = _build_ready_carousel(tmp_path)
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        return {
            "data": [
                {
                    "id": "110506962309835",
                    "name": "Seoul, Korea",
                    "location": {"city": "Seoul", "country": "South Korea"},
                    "link": "https://www.facebook.com/pages/Seoul-Korea/110506962309835",
                },
                {
                    "id": "222",
                    "name": "Gwangjang Market",
                    "location": {"city": "Seoul", "country": "South Korea"},
                    "link": "https://www.facebook.com/gwangjangmarket",
                },
            ]
        }

    client = MetaGraphClient(MetaGraphConfig(access_token="secret-token"), transport=fake_transport)

    review = build_location_candidate_review(
        connection,
        draft.id,
        query="Gwangjang Market Seoul",
        client=client,
    )

    assert review.status == "candidates_found"
    assert review.query == "Gwangjang Market Seoul"
    assert review.candidates[0].name == "Gwangjang Market"
    rendered = review.to_text()
    assert "Possible Meta location tags for post" in rendered
    assert "1. Gwangjang Market (222)" in rendered
    assert "Reply with `use 1`" in rendered
    assert "No location tag was set." in rendered
    assert requested[0][0] == "GET"
    assert requested[0][1].endswith("/pages/search")


def test_drafts_location_candidates_cli_dry_run_prompts_for_clarification(tmp_path: Path):
    connection, draft, _candidate = _build_ready_carousel(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    connection.execute(
        "update drafts set location_text = ? where id = ?",
        ("Seoul, South Korea", draft.id),
    )
    connection.commit()
    connection.close()

    result = runner.invoke(
        app,
        [
            "drafts",
            "location-candidates",
            "--draft-id",
            str(draft.id),
            "--db",
            str(db_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Need a more specific location before searching Meta Pages" in result.output
    assert "No Meta network calls were made." in result.output


def test_location_page_search_uses_official_pages_search_read_route():
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        return {
            "data": [
                {
                    "id": "110506962309835",
                    "name": "Seoul, Korea",
                    "location": {"city": "Seoul", "country": "South Korea"},
                    "link": "https://www.facebook.com/pages/Seoul-Korea/110506962309835",
                }
            ]
        }

    client = MetaGraphClient(MetaGraphConfig(access_token="secret-token"), transport=fake_transport)

    result = search_location_pages(client, "Seoul Korea")

    assert result.query == "Seoul Korea"
    assert result.candidates[0].page_id == "110506962309835"
    assert result.candidates[0].name == "Seoul, Korea"
    assert result.candidates[0].location["country"] == "South Korea"
    assert requested == [
        (
            "GET",
            "https://graph.facebook.com/v19.0/pages/search",
            {
                "q": "Seoul Korea",
                "fields": "id,name,location,link",
                "access_token": "secret-token",
            },
        )
    ]


def test_setting_resolved_location_tag_is_separate_from_location_text_and_invalidates_approvals(tmp_path: Path):
    connection, draft, _candidate = _build_ready_carousel(tmp_path)

    tag = set_draft_location_tag(
        connection,
        draft.id,
        page_id="110506962309835",
        name="Seoul, Korea",
        source="pages/search",
    )

    assert tag.page_id == "110506962309835"
    assert get_draft_location_tag(connection, draft.id).name == "Seoul, Korea"
    updated = get_draft(connection, draft.id)
    assert updated.location_text is None
    assert updated.status == DraftState.NEEDS_EDITS.value
    assert list_active_approvals(connection, draft.id) == []


def test_drafts_location_tag_set_cli_persists_resolved_page_and_warns_reapproval(tmp_path: Path):
    connection, draft, _candidate = _build_ready_carousel(tmp_path)
    db_path = tmp_path / "post_relay.sqlite"
    connection.close()

    result = runner.invoke(
        app,
        [
            "drafts",
            "location-tag-set",
            "--draft-id",
            str(draft.id),
            "--page-id",
            "110506962309835",
            "--name",
            "Seoul, Korea",
            "--source",
            "pages/search",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Resolved Meta location tag for post" in result.output
    assert "location_id=110506962309835" in result.output
    assert "Prior approvals were invalidated" in result.output
    reopened = connect_db(db_path)
    initialize_db(reopened)
    assert get_draft_location_tag(reopened, draft.id).name == "Seoul, Korea"
    assert get_draft(reopened, draft.id).status == DraftState.NEEDS_EDITS.value


def test_final_preview_shows_resolved_location_tag_payload_after_reapproval(tmp_path: Path):
    connection, draft, candidate = _build_ready_carousel(tmp_path)
    set_draft_location_tag(
        connection,
        draft.id,
        page_id="110506962309835",
        name="Seoul, Korea",
        source="pages/search",
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
    for index, source_path in enumerate(list_candidate_group_photo_paths(connection, candidate.id), start=1):
        create_r2_staged_object_record(
            connection,
            draft_id=draft.id,
            kind="draft_media",
            source_path=source_path,
            bucket="post-relay-publish",
            object_key=f"post-relay/staging/drafts/{draft.id}/media/{index:02d}-image.jpg",
            public_url=f"https://peddocks.net/post-relay/staging/drafts/{draft.id}/media/{index:02d}-image.jpg",
        )
    connection.commit()

    preview = build_final_publish_preview(connection, draft.id, r2_config=r2_config)

    assert preview.location_handling == "resolved Meta location tag"
    assert preview.location_tag_payload == {"location_id": "110506962309835", "name": "Seoul, Korea"}
    rendered = preview.to_text()
    assert "Location handling: resolved Meta location tag" in rendered
    assert "Meta location tag payload: location_id=110506962309835 (Seoul, Korea)" in rendered


def test_carousel_publish_sends_resolved_reviewed_location_id(tmp_path: Path):
    connection, draft, _candidate = _build_ready_carousel(tmp_path)
    set_draft_location_tag(
        connection,
        draft.id,
        page_id="110506962309835",
        name="Seoul, Korea",
        source="pages/search",
    )
    submit_draft_for_review(connection, draft.id)
    approve_draft_content(connection, draft.id, approved_by="andrew")
    schedule_draft(connection, draft.id, scheduled_for="2026-05-05T09:30:00-07:00")
    request_publish_approval(connection, draft.id)
    approve_draft_for_publishing(connection, draft.id, approved_by="andrew")
    requested = []

    def fake_transport(method, url, params):
        requested.append((method, url, dict(params)))
        media_url = "https://graph.facebook.com/v19.0/17841400498120050/media"
        if url == media_url and params.get("image_url") == "https://example.com/market.jpg":
            return {"id": "child-1"}
        if url == media_url and params.get("image_url") == "https://example.com/lanterns.jpg":
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
        image_urls=["https://example.com/market.jpg", "https://example.com/lanterns.jpg"],
        client=client,
    )

    carousel_parent_params = requested[2][2]
    assert carousel_parent_params["media_type"] == "CAROUSEL"
    assert carousel_parent_params["location_id"] == "110506962309835"
    assert "location_id" not in requested[0][2]
    assert "location_id" not in requested[1][2]
