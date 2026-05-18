from pathlib import Path

from post_relay.approvals import approve_draft_content, submit_draft_for_review
from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig, R2StagingConfig
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.final_publish_preview import build_final_publish_preview, compose_final_meta_caption
from post_relay.indexer import index_photo_sources
from post_relay.repository import (
    create_r2_staged_object_record,
    get_draft,
    list_candidate_group_photo_paths,
    list_candidate_groups,
    update_draft_content,
)
from post_relay.scheduling import approve_draft_for_publishing, request_publish_approval, schedule_draft
from post_relay.state import DraftState


def _build_ready_carousel_with_metadata(tmp_path: Path):
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
    update_draft_content(
        connection,
        draft.id,
        hashtags=["#travelphotography", "#Seoul", "#travelphotography"],
        location_text="Seoul, South Korea",
        alt_text="Review-only accessibility note for the selected market photos.",
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
            public_url=f"https://peddocks.net/post-relay/staging/drafts/{draft.id}/media/{index:02d}-image.jpg?token=secret",
        )
    connection.commit()
    return connection, get_draft(connection, draft.id), r2_config


def test_compose_final_meta_caption_embeds_approved_hashtags_once(tmp_path: Path):
    connection, draft, _r2_config = _build_ready_carousel_with_metadata(tmp_path)

    assert compose_final_meta_caption(draft) == "Night market glow.\n\n#travelphotography #Seoul"

    update_draft_content(connection, draft.id, caption="Night market glow. #Seoul")
    updated = get_draft(connection, draft.id)

    assert compose_final_meta_caption(updated) == "Night market glow. #Seoul\n\n#travelphotography"


def test_final_publish_preview_shows_meta_bound_caption_and_review_only_metadata(tmp_path: Path):
    connection, draft, r2_config = _build_ready_carousel_with_metadata(tmp_path)

    preview = build_final_publish_preview(connection, draft.id, r2_config=r2_config)

    assert preview.draft_id == draft.id
    assert preview.post_type == "carousel"
    assert preview.meta_caption == "Night market glow.\n\n#travelphotography #Seoul"
    assert preview.hashtags_embedded_in_caption == ["#travelphotography", "#Seoul"]
    assert preview.location_handling == "local/review-only"
    assert preview.location_text == "Seoul, South Korea"
    assert preview.review_only_fields["alt_text"] == "Review-only accessibility note for the selected market photos."
    assert preview.image_urls == [
        f"https://peddocks.net/post-relay/staging/drafts/{draft.id}/media/01-image.jpg?token=<redacted>",
        f"https://peddocks.net/post-relay/staging/drafts/{draft.id}/media/02-image.jpg?token=<redacted>",
    ]
    rendered = preview.to_text()
    assert "Final publish preview" in rendered
    assert "Exact Meta-bound caption:" in rendered
    assert "#travelphotography #Seoul" in rendered
    assert "Location handling: local/review-only" in rendered
    assert "No Meta publishing endpoints were called." in rendered
    assert "secret" not in rendered
