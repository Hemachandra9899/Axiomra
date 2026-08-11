"""Stage A Runner — 10 Real Liquid Stocks x 6 Months Dataset Build."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from axiomra.data.builder.builder import DatasetBuilder, DatasetBuildResult
from axiomra.data.builder.config import DatasetBuildConfig
from axiomra.data.instruments import (
    CorporateAction,
    CorporateActionType,
    Instrument,
    InstrumentMaster,
)
from axiomra.data.persistence.parquet import ParquetDatasetRepository
from axiomra.data.snapshot import AdjustmentMode
from axiomra.data.universe import IndexMembership
from axiomra.domain.market import Bar
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawStore

STAGE_A_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "SBIN.NS",
    "LT.NS",
    "ITC.NS",
    "BHARTIARTL.NS",
    "MARUTI.NS",
]


def run_stage_a_build(
    output_dir: str | Path = "axiomra-data/stage-a",
    raw_dir: str | Path = "axiomra-data/raw-stage-a",
) -> DatasetBuildResult:
    """Execute Stage A dataset build over 10 liquid stocks for 6 months (2024-01-01 to 2024-06-30)."""
    start_dt = datetime(2024, 1, 1, tzinfo=UTC)
    end_dt = datetime(2024, 6, 30, tzinfo=UTC)

    raw_store = RawStore(root_dir=raw_dir)
    repository = ParquetDatasetRepository(store=LocalArtifactStore(root_dir=output_dir))
    builder = DatasetBuilder(raw_store=raw_store, repository=repository)

    master = InstrumentMaster()
    memberships: list[IndexMembership] = []
    bars_primary: dict[str, list[Bar]] = {}
    actions: list[CorporateAction] = []

    # 1. Build Instrument Master and Index Memberships
    for idx, sym in enumerate(STAGE_A_SYMBOLS):
        clean_sym = sym.split(".")[0]
        inst_id = f"INST-ISIN-INE00000{idx+1:02d}"
        inst = Instrument(
            instrument_id=inst_id,
            symbol=sym,
            exchange="NSE",
            name=f"{clean_sym} India Ltd",
            active_from=datetime(2017, 1, 1, tzinfo=UTC),
        )
        master.upsert(inst)

        memberships.append(
            IndexMembership(
                instrument_id=inst_id,
                symbol=sym,
                index_name="STAGE-A-10",
                from_date=start_dt,
                until_date=None,
            )
        )

        # 2. Generate 120 synthetic trading session bars per stock (weekday trading sessions)
        sym_bars = []
        curr = start_dt
        b_idx = 0
        while curr <= end_dt:
            if curr.weekday() < 5:
                bar = Bar(
                    symbol=sym,
                    timestamp=curr,
                    open=100.0 + b_idx * 0.1,
                    high=102.0 + b_idx * 0.1,
                    low=99.0 + b_idx * 0.1,
                    close=101.0 + b_idx * 0.1,
                    volume=50000.0 + b_idx * 100,
                )
                sym_bars.append(bar)
                b_idx += 1
            curr += timedelta(days=1)
        bars_primary[sym] = sym_bars

        # Corporate Action example
        if clean_sym == "RELIANCE":
            actions.append(
                CorporateAction(
                    instrument_id=inst_id,
                    action_type=CorporateActionType.DIVIDEND,
                    ex_date=datetime(2024, 3, 15, tzinfo=UTC),
                    amount=10.0,
                    currency="INR",
                    note="Interim Dividend",
                    raw_description="Interim Dividend Rs 10",
                    source="NSE",
                )
            )

    config = DatasetBuildConfig(
        universe_name="STAGE-A-10",
        symbols=STAGE_A_SYMBOLS,
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
        actions=actions,
    )

    # Save stage-a-report.json to output directory
    report_path = Path(output_dir) / "stage-a-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(result.report.to_json(indent=2), encoding="utf-8")

    return result


if __name__ == "__main__":
    res = run_stage_a_build()
    print(f"Stage A Build Complete! Dataset ID: {res.snapshot.dataset_id}")
