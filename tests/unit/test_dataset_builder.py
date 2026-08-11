"""Unit tests for DatasetBuilder module and Stage A/B/C dataset construction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axiomra.data.builder import (
    IncompleteRunError,
)
from axiomra.data.builder.stage_a import run_stage_a_build
from axiomra.data.builder.stage_b import run_stage_b_build
from axiomra.data.builder.stage_c import run_stage_c_build
from axiomra.data.persistence.parquet import ParquetDatasetRepository


def test_stage_a_build_end_to_end(tmp_path: Path):
    """Stage A build must execute 10 stocks x 6 months build, generate Parquet snapshot, and verify logical SHA round-trip."""
    output_dir = tmp_path / "stage_a_out"
    raw_dir = tmp_path / "stage_a_raw"

    result = run_stage_a_build(output_dir=output_dir, raw_dir=raw_dir)

    assert result.snapshot is not None
    assert len(result.snapshot.universe.members) == 10
    assert result.report.instrument_count == 10
    assert result.report.missing_sessions == 0
    assert result.report.quarantined_rows == 0
    assert result.coverage_report.ready_for_dataset is True

    # Report JSON output test
    report_file = output_dir / "stage-a-report.json"
    assert report_file.exists()
    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_data["instrument_count"] == 10
    assert report_data["logical_checksum"] == result.snapshot.dataset_id

    # Parquet reload & exact logical SHA verification test
    from axiomra.storage.local import LocalArtifactStore
    repository = ParquetDatasetRepository(store=LocalArtifactStore(root_dir=output_dir))
    loaded = repository.load(result.snapshot.dataset_id)
    assert loaded.snapshot.dataset_id == result.snapshot.dataset_id
    assert loaded.snapshot.bar_count() == result.snapshot.bar_count()
    assert loaded.snapshot.universe.members == result.snapshot.universe.members


def test_stage_b_incomplete_run_raises(tmp_path: Path):
    """Stage B build must raise IncompleteRunError when an acquisition failure occurs."""
    output_dir = tmp_path / "stage_b_out"
    raw_dir = tmp_path / "stage_b_raw"

    with pytest.raises(IncompleteRunError, match="Stage B run aborted"):
        run_stage_b_build(
            output_dir=output_dir,
            raw_dir=raw_dir,
            simulate_failure_symbol="STOCK05.NS",
        )


def test_stage_c_delisted_constituent_accounting(tmp_path: Path):
    """Stage C build must incorporate historical delisted constituents and verify coverage."""
    output_dir = tmp_path / "stage_c_out"
    raw_dir = tmp_path / "stage_c_raw"

    result = run_stage_c_build(output_dir=output_dir, raw_dir=raw_dir)

    assert result.snapshot is not None
    assert "OLDCO.NS" in result.snapshot.bars
    assert result.coverage_report.delisted_or_removed_constituents == 1
    assert result.coverage_report.ready_for_dataset is True

    report_file = output_dir / "ds-nifty200-daily-2017-2026-v1-report.json"
    assert report_file.exists()
