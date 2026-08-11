"""Artifact manifests for dataset and feature storage."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from axiomra.data.snapshot import AdjustmentMode

SUPPORTED_DATASET_SCHEMAS = {"dataset-v1"}
SUPPORTED_FEATURE_SCHEMAS = {"features-v1"}


class UnsupportedSchemaError(ValueError):
    """Raised when an unsupported artifact schema version is encountered."""


class FileArtifact(BaseModel):
    path: str
    sha256: str
    rows: int | None = None


class DatasetManifest(BaseModel):
    schema_version: str = "dataset-v1"
    dataset_id: str
    logical_checksum: str
    artifact_checksum: str
    created_at: datetime
    data_version: str
    adjustment_mode: AdjustmentMode
    universe_name: str
    universe_version: str
    universe_as_of: datetime
    """Exact UTC timestamp of the original Universe.as_of — required for checksum identity."""
    universe_members: list[str] = Field(default_factory=list)
    """Ordered member list from the original Universe — required for checksum identity."""
    start_date: date
    end_date: date
    instrument_count: int
    bar_count: int
    files: dict[str, FileArtifact] = Field(default_factory=dict)
    source: str | None = None
    source_version: str | None = None
    git_commit: str | None = None


class FeatureManifest(BaseModel):
    schema_version: str = "features-v1"
    feature_artifact_id: str
    dataset_id: str
    dataset_checksum: str
    feature_version: str
    feature_names: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    file_sha256: str
    content_checksum: str
    git_commit: str | None = None
    created_at: datetime
