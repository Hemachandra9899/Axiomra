"""Unit tests for DatasetBuilder module, checksum lineage, quality fail-fast, and Stage A/B/C runners."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from axiomra.data.builder import (
    DatasetBuildConfig,
    DatasetBuilder,
    IncompleteRunError,
    run_stage_a_fixture,
    run_stage_b_fixture,
    run_stage_c_fixture,
)
from axiomra.data.instruments import Instrument, InstrumentMaster
from axiomra.data.persistence.models import DatasetQualityError
from axiomra.data.persistence.parquet import ParquetDatasetRepository
from axiomra.data.universe import IndexMembership
from axiomra.domain.market import Bar
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawStore


def test_dataset_builder_quality_fail_fast(tmp_path: Path):
    """DatasetBuilder must raise DatasetQualityError and abort persistence if quality check fails."""
    start_dt = datetime(2024, 1, 1, tzinfo=UTC)
    end_dt = datetime(2024, 1, 10, tzinfo=UTC)

    raw_store = RawStore(root_dir=tmp_path / "raw")
    repository = ParquetDatasetRepository(store=LocalArtifactStore(root_dir=tmp_path / "out"))
    builder = DatasetBuilder(raw_store=raw_store, repository=repository)

    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="INST-BAD",
            symbol="BAD.NS",
            active_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )

    # Bar with High (50.0) < max(Open, Close) (100.0) fails DataQualityChecker rules
    bad_bars = {
        "BAD.NS": [
            Bar(symbol="BAD.NS", timestamp=start_dt, open=100.0, high=50.0, low=40.0, close=90.0, volume=1000.0)
        ]
    }

    config = DatasetBuildConfig(
        universe_name="TEST-BAD",
        symbols=["BAD.NS"],
        start_date=start_dt,
        end_date=end_dt,
    )

    memberships = [
        IndexMembership(
            instrument_id="INST-BAD",
            symbol="BAD.NS",
            index_name="TEST-BAD",
            from_date=start_dt,
            until_date=None,
        )
    ]

    with pytest.raises(DatasetQualityError, match="failed quality check"):
        builder.build(
            config=config,
            bars=bad_bars,
            instruments=master,
            memberships=memberships,
        )


def test_dataset_builder_manifest_checksum_lineage(tmp_path: Path):
    """DatasetBuildReport must contain 64-char SHA256 logical_checksum and artifact_checksum from DatasetManifest."""
    output_dir = tmp_path / "fixture_out"
    raw_dir = tmp_path / "fixture_raw"

    result = run_stage_a_fixture(output_dir=output_dir, raw_dir=raw_dir)

    assert result.report.data_origin == "synthetic"
    assert result.report.synthetic_rows > 0

    # Verify logical_checksum and artifact_checksum are 64-char SHA256 hex strings
    assert len(result.report.logical_checksum) == 64
    assert len(result.report.artifact_checksum) == 64
    assert result.report.logical_checksum != result.snapshot.dataset_id
    assert result.report.artifact_checksum != result.snapshot.dataset_id


def test_stage_a_fixture_end_to_end(tmp_path: Path):
    """Stage A fixture build must execute 10 stocks x 6 months build, generate Parquet snapshot, and verify logical SHA round-trip."""
    output_dir = tmp_path / "stage_a_out"
    raw_dir = tmp_path / "stage_a_raw"

    result = run_stage_a_fixture(output_dir=output_dir, raw_dir=raw_dir)

    assert result.snapshot is not None
    assert len(result.snapshot.universe.members) == 10
    assert result.report.instrument_count == 10
    assert result.report.missing_sessions == 0
    assert result.report.quarantined_rows == 0
    assert result.coverage_report.ready_for_dataset is True

    # Report JSON output test
    report_file = output_dir / "stage-a-fixture-report.json"
    assert report_file.exists()
    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_data["instrument_count"] == 10
    assert report_data["data_origin"] == "synthetic"
    assert len(report_data["logical_checksum"]) == 64

    # Parquet reload & exact logical SHA verification test
    repository = ParquetDatasetRepository(store=LocalArtifactStore(root_dir=output_dir))
    loaded = repository.load(result.snapshot.dataset_id)
    assert loaded.snapshot.dataset_id == result.snapshot.dataset_id
    assert loaded.snapshot.bar_count() == result.snapshot.bar_count()
    assert loaded.snapshot.universe.members == result.snapshot.universe.members


def test_stage_b_fixture_incomplete_run_raises(tmp_path: Path):
    """Stage B fixture build must raise IncompleteRunError when an acquisition failure occurs."""
    output_dir = tmp_path / "stage_b_out"
    raw_dir = tmp_path / "stage_b_raw"

    with pytest.raises(IncompleteRunError, match="Stage B run aborted"):
        run_stage_b_fixture(
            output_dir=output_dir,
            raw_dir=raw_dir,
            simulate_failure_symbol="STOCK05.NS",
        )


def test_stage_c_fixture_delisted_constituent_accounting(tmp_path: Path):
    """Stage C fixture build must incorporate historical delisted constituents and verify coverage."""
    output_dir = tmp_path / "stage_c_out"
    raw_dir = tmp_path / "stage_c_raw"

    result = run_stage_c_fixture(output_dir=output_dir, raw_dir=raw_dir)

    assert result.snapshot is not None
    assert "OLDCO.NS" in result.snapshot.bars
    assert result.coverage_report.delisted_or_removed_constituents == 1
    assert result.coverage_report.ready_for_dataset is True

    report_file = output_dir / "stage-c-fixture-report.json"
    assert report_file.exists()
