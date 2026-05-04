from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field


class PhotoSource(BaseModel):
    """A configured source of candidate media."""

    name: str
    root: Path
    source_type: Literal["processed_folder", "immich", "manual"] = "processed_folder"
    enabled: bool = True
    reliability_score: float = Field(default=1.0, ge=0.0, le=1.0)


class ReviewArtifactsConfig(BaseModel):
    """Local review artifact generation settings."""

    root: Path = Path("data/review_artifacts")
    thumbnail_max_px: int = Field(default=1600, ge=1)
    contact_sheet_columns: int = Field(default=3, ge=1)
    mode: Literal["local", "r2", "both"] = "local"


class R2StagingConfig(BaseModel):
    """Cloudflare R2 staging settings for temporary publish/review objects."""

    enabled: bool = False
    bucket: Optional[str] = None
    endpoint_url: Optional[str] = None
    public_base_url: Optional[str] = None
    prefix: str = "post-relay/staging"
    default_ttl_hours: int = Field(default=72, ge=1)
    cleanup_after_publish: bool = True
    account_id_env: str = "POST_RELAY_R2_ACCOUNT_ID"
    access_key_id_env: str = "POST_RELAY_R2_ACCESS_KEY_ID"
    secret_access_key_env: str = "POST_RELAY_R2_SECRET_ACCESS_KEY"


class PostRelayConfig(BaseModel):
    """Runtime configuration for Post Relay."""

    photo_sources: List[PhotoSource] = Field(default_factory=list)
    supported_image_extensions: List[str] = Field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff"]
    )
    review_artifacts: ReviewArtifactsConfig = Field(default_factory=ReviewArtifactsConfig)
    r2_staging: R2StagingConfig = Field(default_factory=R2StagingConfig)


def load_config(path: Path) -> PostRelayConfig:
    """Load Post Relay configuration from a YAML file."""
    data = _read_yaml_mapping(path)
    sources = data.get("photo_sources", [])
    normalized_sources = []
    for source in sources:
        normalized = dict(source)
        if "root" in normalized:
            normalized["root"] = Path(str(normalized["root"])).expanduser()
        normalized_sources.append(normalized)
    data["photo_sources"] = normalized_sources
    if "review_artifacts" in data and "root" in data["review_artifacts"]:
        data["review_artifacts"] = dict(data["review_artifacts"])
        data["review_artifacts"]["root"] = Path(str(data["review_artifacts"]["root"])).expanduser()
    return PostRelayConfig(**data)


def _read_yaml_mapping(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data
