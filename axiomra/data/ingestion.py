"""Ingestion: provider raw bars -> point-in-time dataset snapshot.

The ingest step owns point-in-time correctness:

1. Fetch raw bars per symbol from a provider.
2. Apply corporate-action adjustments (splits) to historical prices so a
   moving-average / momentum feature computed across the split boundary is
   meaningful.
3. Assemble a checksummed `DatasetSnapshot` and record the run.

Adjustment rule: prices on/before an `ex_date` are divided by the split
ratio; prices after the ex_date are already split-adjusted by the exchange.
V1 handles forward splits (ratio > 1). Reverse splits and dividends are
explicitly rejected until the backtest engine needs them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from axiomra.data.instruments import CorporateAction, InstrumentMaster
from axiomra.data.providers.base import MarketDataProvider
from axiomra.data.snapshot import create_snapshot
from axiomra.data.universe import Universe
from axiomra.domain.market import Bar
from axiomra.versions import DATA_VERSION_PREFIX

logger = logging.getLogger(__name__)


class UnsupportedActionError(ValueError):
    """Raised for corporate actions the adjuster cannot handle."""


@dataclass
class IngestionResult:
    dataset_id: str
    data_version: str
    symbol_count: int
    bar_count: int
    checksum: str
    adjusted_symbols: list[str]
    created_at: datetime


def adjust_splits(
    bars: list[Bar],
    actions: list[CorporateAction],
) -> tuple[list[Bar], bool]:
    """Divide pre-ex-date prices by each forward split ratio.

    Returns (adjusted_bars, adjusted) where adjusted is True when any bar
    moved, which marks the series as adjusted in the snapshot metadata.
    """
    adjusted = False
    adjusted_bars = list(bars)
    for action in sorted(actions, key=lambda a: a.ex_date):
        if action.action_type != "SPLIT":
            raise UnsupportedActionError(
                f"{action.action_type} not supported yet (instrument {action.instrument_id})"
            )
        ratio = action.ratio
        if ratio is None or ratio <= 0:
            raise UnsupportedActionError(f"SPLIT with invalid ratio {ratio!r}")
        if ratio < 1.0:
            raise UnsupportedActionError(
                f"reverse split ratio {ratio} not supported yet"
            )
        if ratio == 1.0:
            continue

        factor = ratio
        adjusted = True
        adjusted_bars = [
            bar
            if bar.timestamp >= action.ex_date
            else bar.model_copy(
                update={
                    "open": bar.open / factor,
                    "high": bar.high / factor,
                    "low": bar.low / factor,
                    "close": bar.close / factor,
                    "volume": bar.volume * factor,
                }
            )
            for bar in adjusted_bars
        ]
    return adjusted_bars, adjusted


def next_data_version(previous: str | None = None) -> str:
    """Monotonic data version: dYYYYMMDDHHMMSS."""
    return f"{DATA_VERSION_PREFIX}{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"


class IngestionPipeline:
    """Pulls bars for a universe and commits a DatasetSnapshot."""

    def __init__(
        self,
        provider: MarketDataProvider,
        instruments: InstrumentMaster,
    ) -> None:
        self.provider = provider
        self.instruments = instruments

    async def ingest(
        self,
        universe: Universe,
        start: date,
        end: date,
        timeframe: str = "1d",
        data_version: str | None = None,
    ) -> IngestionResult:
        version = data_version or next_data_version()
        bars_by_symbol: dict[str, list[Bar]] = {}
        adjusted_symbols: list[str] = []
        all_actions: list[CorporateAction] = []

        for symbol in universe.members:
            instrument = self.instruments.by_symbol(symbol)
            raw = await self.provider.bars(symbol, start, end, timeframe)
            if not raw:
                logger.warning("no bars for %s", symbol)
                continue

            if instrument is None:
                bars_by_symbol[symbol] = raw
                continue

            actions = self.instruments.actions(instrument.instrument_id)
            adjusted, moved = adjust_splits(raw, actions)
            bars_by_symbol[symbol] = adjusted
            all_actions.extend(actions)
            if moved:
                adjusted_symbols.append(symbol)

        snapshot = create_snapshot(
            universe=universe,
            bars=bars_by_symbol,
            data_version=version,
            actions=all_actions,
        )

        return IngestionResult(
            dataset_id=snapshot.dataset_id,
            data_version=version,
            symbol_count=snapshot.symbol_count(),
            bar_count=snapshot.bar_count(),
            checksum=snapshot.checksum,
            adjusted_symbols=adjusted_symbols,
            created_at=snapshot.created_at,
        )
