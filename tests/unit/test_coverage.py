"""Unit tests for Historical Instrument Coverage and Delisted Constituent Audit Engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from axiomra.data.coverage import CoverageAnalyzer, HistoricalInstrumentCoverageReport
from axiomra.data.instruments import Instrument, InstrumentMaster
from axiomra.data.snapshot import create_snapshot
from axiomra.data.universe import IndexMembership, Universe
from axiomra.domain.market import Bar


def test_coverage_analyzer_audit():
    """CoverageAnalyzer must audit constituents, map IDs, detect delisted status, and account for bar coverage."""
    start = datetime(2024, 1, 1, tzinfo=UTC)

    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="INST-AAA",
            symbol="AAA.NS",
            active_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )

    memberships = [
        IndexMembership(
            instrument_id="INST-AAA",
            symbol="AAA.NS",
            index_name="NIFTY 200",
            from_date=start,
            until_date=None,  # Active
        ),
        IndexMembership(
            instrument_id="INST-BBB",
            symbol="BBB.NS",
            index_name="NIFTY 200",
            from_date=start,
            until_date=start + timedelta(days=100),  # Delisted/removed constituent
        ),
    ]

    bars_aaa = [
        Bar(symbol="AAA.NS", timestamp=start + timedelta(days=i), open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)
        for i in range(10)
    ]
    uni = Universe(name="NIFTY 200", version="v1", as_of=datetime.now(UTC), members=["AAA.NS"])
    snap = create_snapshot(universe=uni, bars={"AAA.NS": bars_aaa}, data_version="d1")

    analyzer = CoverageAnalyzer()
    report = analyzer.analyze_coverage(
        memberships=memberships,
        snapshot=snap,
        instruments=master,
        index_name="NIFTY 200",
    )

    assert isinstance(report, HistoricalInstrumentCoverageReport)
    assert report.total_constituents == 2
    assert report.active_constituents == 1
    assert report.delisted_or_removed_constituents == 1

    item_aaa = next(i for i in report.items if i.symbol == "AAA.NS")
    assert item_aaa.is_currently_active is True
    assert item_aaa.has_master_record is True
    assert item_aaa.has_ohlcv_bars is True
    assert item_aaa.status == "PASS"

    item_bbb = next(i for i in report.items if i.symbol == "BBB.NS")
    assert item_bbb.is_currently_active is False
    assert item_bbb.is_delisted_or_removed is True
    assert item_bbb.has_master_record is False
    assert item_bbb.status == "UNRESOLVED_ID"
