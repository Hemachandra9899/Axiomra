"""Dataset Build Report and Build Run Manifest Models."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def get_git_sha() -> str:
    """Resolve current git HEAD commit SHA dynamically at runtime."""
    try:
        res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "unknown"


class DatasetBuildReport(BaseModel):
    """Audit report generated for every persisted Axiomra dataset build."""

    dataset_id: str
    universe_name: str
    date_range: str
    instrument_count: int
    bar_count: int
    data_origin: Literal["provider", "synthetic"] = "provider"
    synthetic_rows: int = 0
    raw_fetch_count: int = 0
    raw_source_shas: list[str] = Field(default_factory=list)
    coverage_by_instrument: dict[str, float] = Field(default_factory=dict)
    missing_sessions: int = 0
    reconciliation_discrepancies: int = 0
    quarantined_rows: int = 0
    corporate_action_count: int = 0
    logical_checksum: str
    artifact_checksum: str = ""
    build_git_sha: str = Field(default_factory=get_git_sha)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_json(self, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)


class BuildRunManifest(BaseModel):
    """Operational execution manifest tracking requested vs successful vs failed instruments."""

    run_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    requested_instruments: int = 0
    successful_instruments: int = 0
    failed_instruments: list[str] = Field(default_factory=list)
    raw_fetches: list[str] = Field(default_factory=list)
    dataset_id: str | None = None
    status: str = "SUCCESS"  # 'SUCCESS', 'FAILED', 'INCOMPLETE'
    notes: list[str] = Field(default_factory=list)
