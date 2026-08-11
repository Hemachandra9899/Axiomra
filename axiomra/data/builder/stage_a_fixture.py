"""Stage A Synthetic Fixture Runner — Integration Test Fixture Generator."""

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


def run_stage_a_fixture(
    output_dir: str | Path = "axiomra-data/stage-a-fixture",
    raw_dir: str | Path = "axiomra-data/raw-stage-a-fixture",
) -> DatasetBuildResult:
    """Execute synthetic Stage A integration test fixture build."""
    start_dt = datetime(2024, 1, 1, tzinfo=UTC)
    end_dt = datetime(2024, 6, 30, tzinfo=UTC)

    raw_store = RawStore(root_dir=raw_dir)
    repository = ParquetDatasetRepository(store=LocalArtifactStore(root_dir=output_dir))
    builder = DatasetBuilder(raw_store=raw_store, repository=repository)

    master = InstrumentMaster()
    memberships: list[IndexMembership] = []
    bars_primary: dict[str, list[Bar]] = {}
    actions: list[CorporateAction] = []
    total_synthetic_rows = 0

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
                index_name="STAGE-A-FIXTURE",
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
        total_synthetic_rows += len(sym_bars)

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
        universe_name="STAGE-A-FIXTURE",
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
        data_origin="synthetic",
        synthetic_rows=total_synthetic_rows,
    )

    report_path = Path(output_dir) / "stage-a-fixture-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(result.report.to_json(indent=2), encoding="utf-8")

    return result
