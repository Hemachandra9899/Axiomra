"""Stage C Real Provider Runner — NIFTY 200 PIT 2017–2026 Dataset Build."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from axiomra.data.acquisition import ProviderAcquisitionService
from axiomra.data.builder.builder import DatasetBuilder, DatasetBuildResult
from axiomra.data.builder.config import DatasetBuildConfig
from axiomra.data.persistence.parquet import ParquetDatasetRepository
from axiomra.data.snapshot import AdjustmentMode
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawStore


def run_stage_c_real_build(
    output_dir: str | Path = "axiomra-data/stage-c-real",
    raw_dir: str | Path = "axiomra-data/raw-stage-c-real",
    token: str | None = None,
) -> DatasetBuildResult:
    """Execute real Stage C dataset build for NIFTY 200 PIT 2017–2026 dataset (ds-nifty200-daily-2017-2026-v1)."""
    start_dt = datetime(2017, 1, 1, tzinfo=UTC)
    end_dt = datetime(2026, 1, 1, tzinfo=UTC)

    raw_store = RawStore(root_dir=raw_dir)
    repository = ParquetDatasetRepository(store=LocalArtifactStore(root_dir=output_dir))
    builder = DatasetBuilder(raw_store=raw_store, repository=repository)
    acquisition_service = ProviderAcquisitionService(raw_store=raw_store)

    config = DatasetBuildConfig(
        universe_name="NIFTY 200",
        symbols=[],  # Populated dynamically via PIT membership history
        start_date=start_dt,
        end_date=end_dt,
        adjustment_mode=AdjustmentMode.SPLIT_ADJUSTED,
        output_dir=str(output_dir),
        min_coverage_ratio=0.98,
    )

    acq_result = acquisition_service.acquire(config=config, token=token)

    symbols_list = list(acq_result.bars.keys()) or ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS"]
    config.symbols = symbols_list

    result = builder.build(
        config=config,
        bars=acq_result.bars,
        instruments=acq_result.instruments,
        memberships=acq_result.memberships,
        actions=acq_result.actions,
        raw_manifests=acq_result.raw_manifests,
        data_origin="provider",
        synthetic_rows=0,
    )

    report_path = Path(output_dir) / "ds-nifty200-daily-2017-2026-v1-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(result.report.to_json(indent=2), encoding="utf-8")

    return result


if __name__ == "__main__":
    res = run_stage_c_real_build()
    print(f"Stage C Real Build Complete! Dataset ID: {res.snapshot.dataset_id}")
