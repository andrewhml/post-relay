from post_relay.instagram_capabilities import (
    capability_matrix_text,
    filter_publishable_metadata,
    get_instagram_publish_capability,
)


def test_instagram_capability_matrix_marks_v1_publishable_and_review_only_fields():
    assert get_instagram_publish_capability("media_urls").status == "publishable"
    assert get_instagram_publish_capability("caption").status == "publishable"
    assert get_instagram_publish_capability("hashtags_in_caption").status == "publishable"

    alt_text = get_instagram_publish_capability("alt_text")
    assert alt_text.status == "review_only"
    assert "accessibility" in alt_text.review_note

    location = get_instagram_publish_capability("location_tag")
    assert location.status == "needs_validation"
    assert "not sent" in location.publish_note

    assert get_instagram_publish_capability("music").status == "unsupported_v1"
    assert get_instagram_publish_capability("unknown_future_field").status == "unsupported_v1"


def test_filter_publishable_metadata_keeps_only_meta_graph_v1_fields():
    publishable, review_only = filter_publishable_metadata(
        {
            "media_urls": ["https://example.com/one.jpg"],
            "caption": "Seoul night market #travelphotography",
            "hashtags_in_caption": ["#travelphotography"],
            "alt_text": "Local accessibility note",
            "location_tag": "Seoul, South Korea",
            "collaborators": ["someone"],
            "music": "track id",
        }
    )

    assert publishable == {
        "media_urls": ["https://example.com/one.jpg"],
        "caption": "Seoul night market #travelphotography",
        "hashtags_in_caption": ["#travelphotography"],
    }
    assert review_only["alt_text"].value == "Local accessibility note"
    assert review_only["location_tag"].capability.status == "needs_validation"
    assert review_only["collaborators"].capability.status == "needs_validation"
    assert review_only["music"].capability.status == "unsupported_v1"


def test_capability_matrix_text_is_clear_for_discord_review_copy():
    rendered = capability_matrix_text()

    assert "Instagram Capability Matrix" in rendered
    assert "media_urls: publishable" in rendered
    assert "alt_text: review_only" in rendered
    assert "location_tag: needs_validation" in rendered
    assert "review/local only" in rendered
