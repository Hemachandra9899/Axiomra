"""Dataset Builder Configuration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from axiomra.data.snapshot import AdjustmentMode


class DatasetBuildConfig(BaseModel):
    """Configuration specification for building a persistent, verifiable Axiomra dataset."""

    universe_name: str
    symbols: list[str] = Field(default_factory=list)
    start_date: datetime
    end_date: datetime
    adjustment_mode: AdjustmentMode = AdjustmentMode.SPLIT_ADJUSTED
    output_dir: str = "axiomra-data/datasets"
    min_coverage_ratio: float = 0.98
    fail_on_missing_coverage: bool = True
    fail_on_reconciliation_error: bool = True

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)
