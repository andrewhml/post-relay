from __future__ import annotations

from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field


class PhotoSource(BaseModel):
    """A configured source of candidate media."""

    name: str
    root: Path
    source_type: Literal["processed_folder", "immich", "manual"] = "processed_folder"
    enabled: bool = True
    reliability_score: float = Field(default=1.0, ge=0.0, le=1.0)


class PostRelayConfig(BaseModel):
    """Runtime configuration for Post Relay."""

    photo_sources: List[PhotoSource] = Field(default_factory=list)
    supported_image_extensions: List[str] = Field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff"]
    )
