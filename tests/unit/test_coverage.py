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


def test_coverage_analyzer_flags_data_gap_when_below_threshold():
    """CoverageAnalyzer must assign DATA_GAP status when coverage_ratio < min_coverage_ratio (0.98)."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 31, tzinfo=UTC)  # 23 weekdays

    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="INST-GAP",
            symbol="GAP.NS",
            active_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )

    memberships = [
        IndexMembership(
            instrument_id="INST-GAP",
            symbol="GAP.NS",
            index_name="NIFTY 200",
            from_date=start,
            until_date=end,
        )
    ]

    bars_gap = [
        Bar(symbol="GAP.NS", timestamp=start + timedelta(days=i), open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)
        for i in range(5)
    ]
    bars_full = [
        Bar(symbol="FULL.NS", timestamp=start + timedelta(days=i), open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)
        for i in range(31)
    ]
    uni = Universe(name="NIFTY 200", version="v1", as_of=datetime.now(UTC), members=["GAP.NS", "FULL.NS"])
    snap = create_snapshot(universe=uni, bars={"GAP.NS": bars_gap, "FULL.NS": bars_full}, data_version="d1")

    analyzer = CoverageAnalyzer(min_coverage_ratio=0.98)
    report = analyzer.analyze_coverage(
        memberships=memberships,
        snapshot=snap,
        instruments=master,
        index_name="NIFTY 200",
    )

    item = report.items[0]
    assert item.coverage_ratio < 0.98
    assert item.status == "DATA_GAP"
    assert "Coverage ratio" in item.notes[0]
    assert report.ready_for_dataset is False


def test_coverage_respects_half_open_membership_boundary():
    """CoverageAnalyzer must strictly enforce half-open membership boundary [from_date, until_date)."""
    from_dt = datetime(2024, 1, 1, tzinfo=UTC)
    until_dt = datetime(2024, 1, 10, tzinfo=UTC)  # Jan 10 is until_date (exclusive)

    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="INST-BOUND",
            symbol="BOUND.NS",
            active_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )

    memberships = [
        IndexMembership(
            instrument_id="INST-BOUND",
            symbol="BOUND.NS",
            index_name="NIFTY 200",
            from_date=from_dt,
            until_date=until_dt,
        )
    ]

    # Bar on until_dt (Jan 10) must be excluded from active interval bars
    bars = [
        Bar(symbol="BOUND.NS", timestamp=from_dt + timedelta(days=i), open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)
        for i in range(15)  # Spans Jan 1 to Jan 15
    ]
    uni = Universe(name="NIFTY 200", version="v1", as_of=datetime.now(UTC), members=["BOUND.NS"])
    snap = create_snapshot(universe=uni, bars={"BOUND.NS": bars}, data_version="d1")

    analyzer = CoverageAnalyzer(min_coverage_ratio=0.98)
    report = analyzer.analyze_coverage(
        memberships=memberships,
        snapshot=snap,
        instruments=master,
        index_name="NIFTY 200",
    )

    item = report.items[0]
    # Jan 10 bar must NOT be counted in actual_sessions for half-open interval [Jan 1, Jan 10)
    assert item.last_required_date == until_dt
    assert item.actual_sessions == len({b.timestamp.date() for b in bars if from_dt <= b.timestamp < until_dt})
