"""Stage B Synthetic Fixture Runner — Integration Test Fixture Generator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from axiomra.data.builder.builder import DatasetBuilder, DatasetBuildResult
from axiomra.data.builder.config import DatasetBuildConfig
from axiomra.data.builder.errors import IncompleteRunError
from axiomra.data.instruments import Instrument, InstrumentMaster
from axiomra.data.persistence.parquet import ParquetDatasetRepository
from axiomra.data.snapshot import AdjustmentMode
from axiomra.data.universe import IndexMembership
from axiomra.domain.market import Bar
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawStore

STAGE_B_SYMBOLS = [f"STOCK{i:02d}.NS" for i in range(1, 51)]


def run_stage_b_fixture(
    output_dir: str | Path = "axiomra-data/stage-b-fixture",
    raw_dir: str | Path = "axiomra-data/raw-stage-b-fixture",
    simulate_failure_symbol: str | None = None,
) -> DatasetBuildResult:
    """Execute synthetic Stage B integration test fixture build."""
    start_dt = datetime(2023, 1, 1, tzinfo=UTC)
    end_dt = datetime(2024, 12, 31, tzinfo=UTC)

    raw_store = RawStore(root_dir=raw_dir)
    repository = ParquetDatasetRepository(store=LocalArtifactStore(root_dir=output_dir))
    builder = DatasetBuilder(raw_store=raw_store, repository=repository)

    master = InstrumentMaster()
    memberships: list[IndexMembership] = []
    bars_primary: dict[str, list[Bar]] = {}
    failed_symbols: list[str] = []
    total_synthetic_rows = 0

    for idx, sym in enumerate(STAGE_B_SYMBOLS):
        if simulate_failure_symbol and sym == simulate_failure_symbol:
            failed_symbols.append(sym)
            continue

        inst_id = f"INST-ISIN-B{idx+1:03d}"
        inst = Instrument(
            instrument_id=inst_id,
            symbol=sym,
            exchange="NSE",
            name=f"Stage B Stock {idx+1}",
            active_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
        master.upsert(inst)

        memberships.append(
            IndexMembership(
                instrument_id=inst_id,
                symbol=sym,
                index_name="STAGE-B-FIXTURE",
                from_date=start_dt,
                until_date=None,
            )
        )

        sym_bars = []
        curr = start_dt
        b_idx = 0
        while curr <= end_dt:
            if curr.weekday() < 5:
                bar = Bar(
                    symbol=sym,
                    timestamp=curr,
                    open=200.0 + b_idx * 0.05,
                    high=204.0 + b_idx * 0.05,
                    low=198.0 + b_idx * 0.05,
                    close=202.0 + b_idx * 0.05,
                    volume=100000.0 + b_idx * 50,
                )
                sym_bars.append(bar)
                b_idx += 1
            curr += timedelta(days=1)
        bars_primary[sym] = sym_bars
        total_synthetic_rows += len(sym_bars)

    if failed_symbols:
        raise IncompleteRunError(
            f"Stage B run aborted: {len(failed_symbols)} instruments failed acquisition: {failed_symbols}"
        )

    config = DatasetBuildConfig(
        universe_name="STAGE-B-FIXTURE",
        symbols=STAGE_B_SYMBOLS,
        start_date=start_dt,
        end_date=end_dt,
        adjustment_mode=AdjustmentMode.SPLIT_ADJUSTED,
        output_dir=str(output_dir),
        min_coverage_ratio=0.98,
    )

    result = builder.build(
        config=config,
        bars=bars_primary,
        instruments=master,
        memberships=memberships,
        data_origin="synthetic",
        synthetic_rows=total_synthetic_rows,
    )

    report_path = Path(output_dir) / "stage-b-fixture-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(result.report.to_json(indent=2), encoding="utf-8")

    return result
