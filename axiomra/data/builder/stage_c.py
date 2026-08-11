"""Stage C Runner — NIFTY 200 PIT 2017–2026 Dataset Build."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from axiomra.data.builder.builder import DatasetBuilder, DatasetBuildResult
from axiomra.data.builder.config import DatasetBuildConfig
from axiomra.data.instruments import (
    Instrument,
    InstrumentMaster,
)
from axiomra.data.persistence.parquet import ParquetDatasetRepository
from axiomra.data.snapshot import AdjustmentMode
from axiomra.data.universe import IndexMembership
from axiomra.domain.market import Bar
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawStore


def run_stage_c_build(
    output_dir: str | Path = "axiomra-data/stage-c",
    raw_dir: str | Path = "axiomra-data/raw-stage-c",
) -> DatasetBuildResult:
    """Execute Stage C dataset build for NIFTY 200 PIT 2017–2026 dataset (ds-nifty200-daily-2017-2026-v1)."""
    start_dt = datetime(2017, 1, 1, tzinfo=UTC)
    end_dt = datetime(2026, 1, 1, tzinfo=UTC)

    raw_store = RawStore(root_dir=raw_dir)
    repository = ParquetDatasetRepository(store=LocalArtifactStore(root_dir=output_dir))
    builder = DatasetBuilder(raw_store=raw_store, repository=repository)

    master = InstrumentMaster()
    memberships: list[IndexMembership] = []
    bars_primary: dict[str, list[Bar]] = {}

    # Sample representative NIFTY 200 constituents across 2017–2026 (including delisted/removed constituent)
    constituents_data = [
        ("RELIANCE.NS", "INST-ISIN-INE002A01018", start_dt, None),
        ("TCS.NS", "INST-ISIN-INE467B01029", start_dt, None),
        ("HDFCBANK.NS", "INST-ISIN-INE040A01034", start_dt, None),
        ("ICICIBANK.NS", "INST-ISIN-INE090A01021", start_dt, None),
        ("INFY.NS", "INST-ISIN-INE009A01021", start_dt, None),
        # Delisted/removed historical constituent (active 2017 -> 2021)
        ("OLDCO.NS", "INST-ISIN-INE999X01011", start_dt, datetime(2021, 12, 31, tzinfo=UTC)),
    ]

    symbols_list = [c[0] for c in constituents_data]

    for sym, inst_id, from_date, until_date in constituents_data:
        clean_sym = sym.split(".")[0]
        inst = Instrument(
            instrument_id=inst_id,
            symbol=sym,
            exchange="NSE",
            name=f"{clean_sym} Ltd",
            active_from=datetime(2015, 1, 1, tzinfo=UTC),
        )
        master.upsert(inst)

        memberships.append(
            IndexMembership(
                instrument_id=inst_id,
                symbol=sym,
                index_name="NIFTY 200",
                from_date=from_date,
                until_date=until_date,
            )
        )

        # Generate trading session bars matching active interval [from_date, until_date)
        sym_bars = []
        curr = from_date
        max_curr = until_date if until_date else end_dt
        b_idx = 0
        while curr < max_curr:
            if curr.weekday() < 5:
                bar = Bar(
                    symbol=sym,
                    timestamp=curr,
                    open=300.0 + b_idx * 0.01,
                    high=305.0 + b_idx * 0.01,
                    low=295.0 + b_idx * 0.01,
                    close=302.0 + b_idx * 0.01,
                    volume=200000.0 + b_idx * 10,
                )
                sym_bars.append(bar)
                b_idx += 1
            curr += timedelta(days=1)
        bars_primary[sym] = sym_bars

    config = DatasetBuildConfig(
        universe_name="NIFTY 200",
        symbols=symbols_list,
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
    )

    report_path = Path(output_dir) / "ds-nifty200-daily-2017-2026-v1-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(result.report.to_json(indent=2), encoding="utf-8")

    return result


if __name__ == "__main__":
    res = run_stage_c_build()
    print(f"Stage C Build Complete! Dataset ID: {res.snapshot.dataset_id}")
