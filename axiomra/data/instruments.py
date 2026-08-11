"""Instrument master and corporate actions.

Symbols change, companies merge, stocks split, and names move in and out of
indexes. The internal `instrument_id` survives all of that. `symbol` is the
current trading symbol; `active_from`/`active_until` bound instrument
lifetimes. Corporate actions are keyed to `instrument_id` and used to keep
historical prices point-in-time comparable (adjusting for splits).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, field_validator

from axiomra.domain.common import as_utc


class CorporateActionType(StrEnum):

    """Supported corporate action types and ratio conventions.

    Ratio convention:
    ratio = new_shares / old_shares
    - 2-for-1 split: ratio = 2.0 (pre-ex price divided by 2)
    - 1-for-5 reverse split: ratio = 0.2 (pre-ex price divided by 0.2 -> multiplied by 5)
    """

    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    DIVIDEND = "DIVIDEND"
    MERGER = "MERGER"
    DELISTING = "DELISTING"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"


class Instrument(BaseModel):
    """Stable identity for a tradable instrument."""

    instrument_id: str
    symbol: str
    exchange: str = "NSE"
    isin: str | None = None
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    active_from: datetime
    active_until: datetime | None = None

    @field_validator("active_from", "active_until")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None


class CorporateAction(BaseModel):
    """A split, dividend, merger, delisting or symbol change event."""

    instrument_id: str
    action_type: CorporateActionType | str
    ex_date: datetime
    ratio: float | None = None  # e.g. 2.0 for a 2-for-1 split, 0.2 for 1-for-5 reverse split
    amount: float | None = None  # for dividends
    currency: str = "INR"
    note: str | None = None


    @field_validator("ex_date")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class InstrumentMaster:
    """Read model over instruments and corporate actions.

    The persisted `instruments` / `corporate_actions` tables are the source
    of truth; this class is the in-memory index used during ingestion.
    """

    def __init__(self) -> None:
        self._all_instruments: list[Instrument] = []
        self._by_id: dict[str, list[Instrument]] = {}
        self._actions: dict[str, list[CorporateAction]] = {}

    def upsert(self, instrument: Instrument) -> None:
        """Upsert instrument, replacing identical (id, symbol, exchange, active_from) entries."""
        key = (
            instrument.instrument_id,
            instrument.symbol,
            instrument.exchange,
            instrument.active_from,
        )

        # Replace existing entry if key matches exactly
        self._all_instruments = [
            i
            for i in self._all_instruments
            if (i.instrument_id, i.symbol, i.exchange, i.active_from) != key
        ]
        self._all_instruments.append(instrument)

        records = self._by_id.setdefault(instrument.instrument_id, [])
        self._by_id[instrument.instrument_id] = [
            i
            for i in records
            if (i.instrument_id, i.symbol, i.exchange, i.active_from) != key
        ] + [instrument]

    def get(self, instrument_id: str) -> Instrument | None:
        records = self._by_id.get(instrument_id, [])
        return records[-1] if records else None

    def by_symbol(self, symbol: str, exchange: str = "NSE") -> Instrument | None:
        for inst in reversed(self._all_instruments):
            if inst.symbol == symbol and inst.exchange == exchange:
                return inst
        return None

    def resolve_symbol(
        self, symbol: str, as_of: datetime, exchange: str = "NSE"
    ) -> Instrument | None:
        """Resolve a trading symbol at a specific point in time [active_from, active_until). No fallback."""
        utc_as_of = as_utc(as_of)
        matches = [
            inst
            for inst in self._all_instruments
            if inst.symbol == symbol
            and inst.exchange == exchange
            and inst.active_from <= utc_as_of
            and (inst.active_until is None or utc_as_of < inst.active_until)
        ]
        if not matches:
            return None
        return max(matches, key=lambda x: x.active_from)

    def add_action(self, action: CorporateAction) -> None:
        self._actions.setdefault(action.instrument_id, []).append(action)

    def actions(
        self,
        instrument_id: str,
        before: datetime | None = None,
    ) -> list[CorporateAction]:
        actions = self._actions.get(instrument_id, [])
        if before is None:
            return actions
        return [a for a in actions if a.ex_date < before]

    def __len__(self) -> int:
        return len(self._all_instruments)



