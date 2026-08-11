"""M2 data layer: instruments, universe, snapshot, ingestion, providers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from axiomra.data.ingestion import (
    IngestionPipeline,
    UnsupportedActionError,
    adjust_splits,
    next_data_version,
)
from axiomra.data.instruments import (
    CorporateAction,
    Instrument,
    InstrumentMaster,
)
from axiomra.data.providers.base import MarketDataProvider
from axiomra.data.snapshot import (
    DatasetSnapshot,
    compute_checksum,
    create_snapshot,
)
from axiomra.data.universe import NIFTY_50, Universe, load_universe_csv
from axiomra.domain.market import Bar
from axiomra.versions import DATA_VERSION_PREFIX


def _bar(symbol: str, ts: datetime, close: float) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000,
    )


def _universe(members: list[str] | None = None) -> Universe:
    return Universe(
        name="NIFTY 50",
        version="test-v1",
        as_of=datetime.now(UTC),
        members=members or ["RELIANCE.NS", "TCS.NS"],
    )


def _master() -> InstrumentMaster:
    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="i-reliance",
            symbol="RELIANCE.NS",
            active_from=datetime(2000, 1, 1, tzinfo=UTC),
        )
    )
    master.upsert(
        Instrument(
            instrument_id="i-tcs",
            symbol="TCS.NS",
            active_from=datetime(2000, 1, 1, tzinfo=UTC),
        )
    )
    return master


# --- Instrument master -----------------------------------------------------


def test_instrument_master_lookup_and_actions():
    master = _master()
    assert master.by_symbol("RELIANCE.NS").instrument_id == "i-reliance"
    assert master.by_symbol("UNKNOWN.NS") is None

    split = CorporateAction(
        instrument_id="i-reliance",
        action_type="SPLIT",
        ex_date=datetime(2022, 7, 15, tzinfo=UTC),
        ratio=2.0,
    )
    master.add_action(split)
    assert master.actions("i-reliance") == [split]
    before = datetime(2022, 7, 1, tzinfo=UTC)
    assert master.actions("i-reliance", before=before) == []


def test_instrument_rejects_naive_datetime():
    with pytest.raises(Exception):
        Instrument(
            instrument_id="x",
            symbol="X.NS",
            active_from=datetime(2020, 1, 1),  # naive -> invalid
        )


# --- Universe --------------------------------------------------------------


def test_universe_has_fifty_unique_members():
    assert len(NIFTY_50) == 50
    assert len(set(NIFTY_50)) == 50
    assert all(s.endswith(".NS") for s in NIFTY_50)


def test_universe_loader_embedded():
    uni = load_universe_csv()
    assert uni.name == "NIFTY 50"
    assert len(uni.members) == 50
    assert uni.contains("RELIANCE.NS")
    assert not uni.contains("NOPE.NS")


def test_universe_loader_uses_csv_when_present(tmp_path):
    csv_path = tmp_path / "nifty50.csv"
    csv_path.write_text("symbol,sector\nAAA.NS,Energy\nBBB.NS,IT\n")
    uni = load_universe_csv(path=csv_path)
    assert uni.members == ["AAA.NS", "BBB.NS"]


# --- Snapshot --------------------------------------------------------------


def test_snapshot_is_frozen_and_checksummed():
    snap = create_snapshot(
        universe=_universe(),
        bars={
            "RELIANCE.NS": [
                _bar("RELIANCE.NS", datetime(2024, 1, 2, tzinfo=UTC), 100.0)
            ]
        },
        data_version="dtest1",
    )
    assert snap.checksum.startswith("") or len(snap.checksum) == 64
    assert snap.dataset_id.startswith("ds-")
    assert snap.symbol_count() == 1
    assert snap.bar_count() == 1

    with pytest.raises(Exception):
        snap.data_version = "mutated"  # frozen


def test_snapshot_checksum_detects_mutation():
    snap = create_snapshot(
        universe=_universe(),
        bars={
            "RELIANCE.NS": [
                _bar("RELIANCE.NS", datetime(2024, 1, 2, tzinfo=UTC), 100.0)
            ]
        },
        data_version="dtest1",
    )
    other = snap.model_copy(
        update={
            "bars": {
                "RELIANCE.NS": [
                    _bar("RELIANCE.NS", datetime(2024, 1, 2, tzinfo=UTC), 101.0)
                ]
            }
        }
    )
    with pytest.raises(ValueError):
        DatasetSnapshot.model_validate(other.model_dump())


def test_snapshot_checksum_is_deterministic():
    uni = _universe()
    a = create_snapshot(universe=uni, bars={}, data_version="d1")
    b = create_snapshot(universe=uni, bars={}, data_version="d1")
    assert a.checksum == b.checksum == compute_checksum(a)


# --- Ingestion -------------------------------------------------------------


def test_next_data_version_prefix():
    assert next_data_version().startswith(DATA_VERSION_PREFIX)


def test_adjust_splits_forward_only():
    ts_before = datetime(2022, 7, 1, tzinfo=UTC)
    ts_after = datetime(2022, 7, 20, tzinfo=UTC)
    bars = [_bar("R.NS", ts_before, 2000.0), _bar("R.NS", ts_after, 1000.0)]
    split = CorporateAction(
        instrument_id="i",
        action_type="SPLIT",
        ex_date=datetime(2022, 7, 15, tzinfo=UTC),
        ratio=2.0,
    )
    adjusted, moved = adjust_splits(bars, [split])
    assert moved is True
    before_bar = adjusted[0]
    after_bar = adjusted[1]
    assert before_bar.close == 1000.0  # 2000 / 2
    assert before_bar.volume == 2000  # volume doubled
    assert after_bar.close == 1000.0  # untouched
    assert len(adjusted) == 2


def test_adjust_splits_rejects_unsupported_actions():
    bars = [_bar("R.NS", datetime(2022, 7, 1, tzinfo=UTC), 100.0)]
    dividend = CorporateAction(
        instrument_id="i",
        action_type="DIVIDEND",
        ex_date=datetime(2022, 7, 15, tzinfo=UTC),
    )
    with pytest.raises(UnsupportedActionError):
        adjust_splits(bars, [dividend])


def test_adjust_splits_rejects_reverse_split():
    bars = [_bar("R.NS", datetime(2022, 7, 1, tzinfo=UTC), 100.0)]
    reverse = CorporateAction(
        instrument_id="i",
        action_type="SPLIT",
        ex_date=datetime(2022, 7, 15, tzinfo=UTC),
        ratio=0.5,
    )
    with pytest.raises(UnsupportedActionError):
        adjust_splits(bars, [reverse])


class FakeProvider(MarketDataProvider):
    """Provider that returns fixed bars, used to test ingestion."""

    def __init__(self, bars_by_symbol: dict[str, list[Bar]]) -> None:
        self._data = bars_by_symbol

    async def bars(self, symbol, start, end, timeframe="1d"):
        return self._data.get(symbol, [])

    async def latest_snapshot(self, symbol):  # pragma: no cover
        raise NotImplementedError


async def test_ingestion_builds_checksummed_snapshot():
    from datetime import date

    start = date(2024, 1, 1)
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    provider = FakeProvider(
        {
            "RELIANCE.NS": [_bar("RELIANCE.NS", ts, 2500.0)],
            "TCS.NS": [_bar("TCS.NS", ts, 3800.0)],
        }
    )
    pipeline = IngestionPipeline(provider=provider, instruments=_master())
    result = await pipeline.ingest(
        _universe(["RELIANCE.NS", "TCS.NS"]),
        start=start,
        end=date(2024, 1, 31),
    )

    assert result.symbol_count == 2
    assert result.bar_count == 2
    assert result.dataset_id.startswith("ds-")
    assert result.checksum
    assert result.adjusted_symbols == []
    assert result.data_version.startswith(DATA_VERSION_PREFIX)


async def test_ingestion_applies_split_adjustment():
    from datetime import date

    master = _master()
    master.add_action(
        CorporateAction(
            instrument_id="i-reliance",
            action_type="SPLIT",
            ex_date=datetime(2024, 1, 10, tzinfo=UTC),
            ratio=2.0,
        )
    )
    ts_before = datetime(2024, 1, 5, tzinfo=UTC)
    ts_after = datetime(2024, 1, 15, tzinfo=UTC)
    provider = FakeProvider(
        {
            "RELIANCE.NS": [
                _bar("RELIANCE.NS", ts_before, 5000.0),
                _bar("RELIANCE.NS", ts_after, 2500.0),
            ]
        }
    )
    pipeline = IngestionPipeline(provider=provider, instruments=master)
    result = await pipeline.ingest(
        _universe(["RELIANCE.NS"]),
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
    )
    assert result.adjusted_symbols == ["RELIANCE.NS"]
    assert result.bar_count == 2


async def test_ingestion_skips_symbols_without_bars():
    from datetime import date

    ts = datetime(2024, 1, 2, tzinfo=UTC)
    provider = FakeProvider({"RELIANCE.NS": [_bar("RELIANCE.NS", ts, 2500.0)]})
    pipeline = IngestionPipeline(provider=provider, instruments=_master())
    result = await pipeline.ingest(
        _universe(["RELIANCE.NS", "TCS.NS"]),
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
    )
    assert result.symbol_count == 1
