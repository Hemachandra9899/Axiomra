"""Stage B Real Provider Runner — 50 Actual NSE Stocks x 2 Years."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from axiomra.data.acquisition import ProviderAcquisitionService
from axiomra.data.builder.builder import DatasetBuilder, DatasetBuildResult
from axiomra.data.builder.config import DatasetBuildConfig
from axiomra.data.builder.errors import IncompleteRunError
from axiomra.data.persistence.parquet import ParquetDatasetRepository
from axiomra.data.snapshot import AdjustmentMode
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawStore

STAGE_B_REAL_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "SBIN.NS", "LT.NS", "ITC.NS", "BHARTIARTL.NS", "MARUTI.NS",
    "AXISBANK.NS", "KOTAKBANK.NS", "HCLTECH.NS", "SUNPHARMA.NS", "TATAMOTORS.NS",
    "NTPC.NS", "ULTRACEMCO.NS", "TITAN.NS", "POWERGRID.NS", "BAJFINANCE.NS",
    "WIPRO.NS", "M&M.NS", "ONGC.NS", "ADANIENT.NS", "JSWSTEEL.NS",
    "TATASTEEL.NS", "COALINDIA.NS", "ADANIPORTS.NS", "LTIM.NS", "GRASIM.NS",
    "HDFCLIFE.NS", "ASIANPAINT.NS", "SBILIFE.NS", "BAJAJFINSV.NS", "HINDUNILVR.NS",
    "DRREDDY.NS", "CIPLA.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "BRITANNIA.NS",
    "APOLLOHOSP.NS", "TATACONSUM.NS", "DIVISLAB.NS", "BPCL.NS", "HINDALCO.NS",
    "INDUSINDBK.NS", "SHRIRAMFIN.NS", "TRENT.NS", "BEL.NS", "HAL.NS",
]


def run_stage_b_real_build(
    output_dir: str | Path = "axiomra-data/stage-b-real",
    raw_dir: str | Path = "axiomra-data/raw-stage-b-real",
    token: str | None = None,
) -> DatasetBuildResult:
    """Execute real Stage B dataset build across 50 actual stocks for 2 years (2023-01-01 to 2024-12-31)."""
    start_dt = datetime(2023, 1, 1, tzinfo=UTC)
    end_dt = datetime(2024, 12, 31, tzinfo=UTC)

    raw_store = RawStore(root_dir=raw_dir)
    repository = ParquetDatasetRepository(store=LocalArtifactStore(root_dir=output_dir))
    builder = DatasetBuilder(raw_store=raw_store, repository=repository)
    acquisition_service = ProviderAcquisitionService(raw_store=raw_store)

    config = DatasetBuildConfig(
        universe_name="STAGE-B-50-REAL",
        symbols=STAGE_B_REAL_SYMBOLS,
        start_date=start_dt,
        end_date=end_dt,
        adjustment_mode=AdjustmentMode.SPLIT_ADJUSTED,
        output_dir=str(output_dir),
        min_coverage_ratio=0.98,
    )

    acq_result = acquisition_service.acquire(config=config, token=token)

    missing_instruments = [s for s in STAGE_B_REAL_SYMBOLS if s not in acq_result.bars or len(acq_result.bars[s]) == 0]
    if missing_instruments and token is not None:
        raise IncompleteRunError(
            f"Stage B real run aborted: {len(missing_instruments)} instruments failed acquisition: {missing_instruments}"
        )

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

    report_path = Path(output_dir) / "stage-b-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(result.report.to_json(indent=2), encoding="utf-8")

    return result


if __name__ == "__main__":
    res = run_stage_b_real_build()
    print(f"Stage B Real Build Complete! Dataset ID: {res.snapshot.dataset_id}")
