from pathlib import Path

from post_relay.config import load_config


def test_loads_local_nas_review_and_r2_pipeline_config(tmp_path: Path):
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        """
photo_sources:
  - name: nas-processed-2024
    root: /Volumes/Media/photos/2024 Photos/Processed
    source_type: processed_folder
    enabled: true
    reliability_score: 1.0
  - name: local-processed-2025
    root: /Users/andrewlee/Pictures/2025 Photos/Processed
    source_type: processed_folder
    enabled: true
    reliability_score: 1.0

review_artifacts:
  root: data/review_artifacts
  thumbnail_max_px: 1600
  contact_sheet_columns: 3
  mode: local

r2_staging:
  enabled: false
  bucket: post-relay-publish
  endpoint_url: https://d79fef40225063d4b0e2d2cb33b346d0.r2.cloudflarestorage.com
  public_base_url: https://peddocks.net
  prefix: post-relay/staging
  default_ttl_hours: 72
  cleanup_after_publish: true
""".strip()
    )

    config = load_config(config_path)

    assert [source.name for source in config.photo_sources] == [
        "nas-processed-2024",
        "local-processed-2025",
    ]
    assert config.photo_sources[0].root == Path("/Volumes/Media/photos/2024 Photos/Processed")
    assert config.photo_sources[1].root == Path("/Users/andrewlee/Pictures/2025 Photos/Processed")

    assert config.review_artifacts.root == Path("data/review_artifacts")
    assert config.review_artifacts.thumbnail_max_px == 1600
    assert config.review_artifacts.contact_sheet_columns == 3
    assert config.review_artifacts.mode == "local"

    assert config.r2_staging.enabled is False
    assert config.r2_staging.bucket == "post-relay-publish"
    assert (
        config.r2_staging.endpoint_url
        == "https://d79fef40225063d4b0e2d2cb33b346d0.r2.cloudflarestorage.com"
    )
    assert config.r2_staging.public_base_url == "https://peddocks.net"
    assert config.r2_staging.prefix == "post-relay/staging"
    assert config.r2_staging.default_ttl_hours == 72
    assert config.r2_staging.cleanup_after_publish is True


def test_pipeline_config_defaults_keep_r2_disabled(tmp_path: Path):
    config_path = tmp_path / "photo_sources.yaml"
    config_path.write_text(
        """
photo_sources:
  - name: local-processed-2025
    root: /Users/andrewlee/Pictures/2025 Photos/Processed
""".strip()
    )

    config = load_config(config_path)

    assert config.review_artifacts.root == Path("data/review_artifacts")
    assert config.review_artifacts.mode == "local"
    assert config.r2_staging.enabled is False
    assert config.r2_staging.bucket is None
    assert config.r2_staging.endpoint_url is None
    assert config.r2_staging.public_base_url is None
    assert config.r2_staging.account_id_env == "POST_RELAY_R2_ACCOUNT_ID"
    assert config.r2_staging.access_key_id_env == "POST_RELAY_R2_ACCESS_KEY_ID"
    assert config.r2_staging.secret_access_key_env == "POST_RELAY_R2_SECRET_ACCESS_KEY"
    assert config.r2_staging.prefix == "post-relay/staging"
