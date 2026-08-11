"""Milestone 7: Data Correctness unit tests.

Tests point-in-time index membership, reverse split adjustments, dividend adjustments,
symbol resolution, and data quality checker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from axiomra.data.ingestion import adjust_splits
from axiomra.data.instruments import CorporateAction, Instrument, InstrumentMaster
from axiomra.data.quality import DataQualityChecker
from axiomra.data.snapshot import create_snapshot
from axiomra.data.universe import HistoricalUniverseRegistry, IndexMembership, Universe
from axiomra.domain.market import Bar


def _sample_bars(symbol: str = "AAA.NS", days: int = 5, start_price: float = 100.0) -> list[Bar]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = []
    for i in range(days):
        ts = start + timedelta(days=i)
        p = start_price + i * 2.0
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=ts,
                open=p,
                high=p + 1.0,
                low=p - 1.0,
                close=p,
                volume=10_000.0,
            )
        )
    return bars


def test_reverse_split_adjusts_price_and_volume():
    bars = _sample_bars(days=4, start_price=10.0)  # prices: 10, 12, 14, 16
    # 1-for-5 reverse split on day 3 (ratio = 0.2)
    # Pre-ex-date prices (days 0, 1) divided by 0.2 -> multiplied by 5
    action = CorporateAction(
        instrument_id="inst-1",
        action_type="REVERSE_SPLIT",
        ex_date=datetime(2024, 1, 3, tzinfo=UTC),
        ratio=0.2,
    )
    adjusted, moved = adjust_splits(bars, [action])
    assert moved

    # Pre-ex-date bars (2024-01-01, 2024-01-02) prices multiplied by 5
    assert adjusted[0].close == pytest.approx(50.0)
    assert adjusted[0].volume == pytest.approx(2_000.0)

    # Ex-date onwards (2024-01-03, 2024-01-04) unadjusted
    assert adjusted[2].close == pytest.approx(14.0)
    assert adjusted[2].volume == pytest.approx(10_000.0)


def test_dividend_total_return_adjustment():
    bars = _sample_bars(days=4, start_price=100.0)  # closes: 100, 102, 104, 106
    # Rs. 10 dividend on 2024-01-03 (ex-date)
    # Prior close (2024-01-02) is 102.0. Factor = 1 - 10 / 102 = 92 / 102
    action = CorporateAction(
        instrument_id="inst-1",
        action_type="DIVIDEND",
        ex_date=datetime(2024, 1, 3, tzinfo=UTC),
        amount=10.0,
    )
    adjusted, moved = adjust_splits(bars, [action], adjust_dividends=True)
    assert moved
    factor = 1.0 - 10.0 / 102.0
    assert adjusted[0].close == pytest.approx(100.0 * factor)
    assert adjusted[1].close == pytest.approx(102.0 * factor)
    # Ex-date bar unadjusted
    assert adjusted[2].close == pytest.approx(104.0)


def test_point_in_time_index_membership_registry():
    registry = HistoricalUniverseRegistry()
    # RELIANCE added 2020-01-01
    registry.add_membership(
        IndexMembership(
            instrument_id="inst-rel",
            symbol="RELIANCE.NS",
            index_name="NIFTY 50",
            from_date=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    # TEMP_CO added 2021-01-01, removed 2023-01-01
    registry.add_membership(
        IndexMembership(
            instrument_id="inst-temp",
            symbol="TEMP.NS",
            index_name="NIFTY 50",
            from_date=datetime(2021, 1, 1, tzinfo=UTC),
            until_date=datetime(2023, 1, 1, tzinfo=UTC),
        )
    )

    # In 2022: both RELIANCE and TEMP are in index
    uni_2022 = registry.load_universe_at("NIFTY 50", datetime(2022, 6, 1, tzinfo=UTC))
    assert "RELIANCE.NS" in uni_2022.members
    assert "TEMP.NS" in uni_2022.members

    # In 2024: TEMP removed, RELIANCE remains
    uni_2024 = registry.load_universe_at("NIFTY 50", datetime(2024, 6, 1, tzinfo=UTC))
    assert "RELIANCE.NS" in uni_2024.members
    assert "TEMP.NS" not in uni_2024.members


def test_instrument_master_symbol_resolution():
    master = InstrumentMaster()
    inst_old = Instrument(
        instrument_id="inst-1",
        symbol="OLD_SYM.NS",
        active_from=datetime(2020, 1, 1, tzinfo=UTC),
        active_until=datetime(2022, 12, 31, tzinfo=UTC),
    )
    inst_new = Instrument(
        instrument_id="inst-1",
        symbol="NEW_SYM.NS",
        active_from=datetime(2023, 1, 1, tzinfo=UTC),
    )
    master.upsert(inst_old)
    master.upsert(inst_new)

    # Resolve in 2021 -> OLD_SYM
    res_2021 = master.resolve_symbol("OLD_SYM.NS", datetime(2021, 6, 1, tzinfo=UTC))
    assert res_2021 is not None and res_2021.symbol == "OLD_SYM.NS"

    # Resolve in 2024 -> NEW_SYM
    res_2024 = master.resolve_symbol("NEW_SYM.NS", datetime(2024, 6, 1, tzinfo=UTC))
    assert res_2024 is not None and res_2024.symbol == "NEW_SYM.NS"


def test_data_quality_checker_validates_snapshot():
    bars = _sample_bars("AAA.NS", days=5)
    uni = Universe(
        name="TEST",
        version="v1",
        as_of=datetime.now(UTC),
        members=["AAA.NS"],
    )
    snap = create_snapshot(universe=uni, bars={"AAA.NS": bars}, data_version="d1")

    checker = DataQualityChecker()
    report = checker.check(snap)
    assert report.valid
    assert report.total_issues == 0


def test_data_quality_checker_flags_invalid_bar():
    invalid_bar = Bar(
        symbol="AAA.NS",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        open=100.0,
        high=90.0,  # High < Open (invalid)
        low=80.0,
        close=95.0,
        volume=1000.0,
    )
    uni = Universe(
        name="TEST",
        version="v1",
        as_of=datetime.now(UTC),
        members=["AAA.NS"],
    )
    snap = create_snapshot(universe=uni, bars={"AAA.NS": [invalid_bar]}, data_version="d1")

    checker = DataQualityChecker()
    report = checker.check(snap)
    assert not report.valid
    assert report.total_issues > 0
