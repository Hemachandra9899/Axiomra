"""Instrument master and corporate actions.

Symbols change, companies merge, stocks split, and names move in and out of
indexes. The internal `instrument_id` survives all of that. `symbol` is the
current trading symbol; `active_from`/`active_until` bound instrument
lifetimes. Corporate actions are keyed to `instrument_id` and used to keep
historical prices point-in-time comparable (adjusting for splits).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from axiomra.domain.common import as_utc


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
    action_type: str  # SPLIT, DIVIDEND, MERGER, DELISTING, SYMBOL_CHANGE
    ex_date: datetime
    ratio: float | None = None  # e.g. 2.0 for a 2-for-1 split
    amount: float | None = None  # for dividends
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
        self._instruments: dict[str, Instrument] = {}
        self._actions: dict[str, list[CorporateAction]] = {}

    def upsert(self, instrument: Instrument) -> None:
        self._instruments[instrument.instrument_id] = instrument

    def get(self, instrument_id: str) -> Instrument | None:
        return self._instruments.get(instrument_id)

    def by_symbol(self, symbol: str, exchange: str = "NSE") -> Instrument | None:
        for inst in self._instruments.values():
            if inst.symbol == symbol and inst.exchange == exchange:
                return inst
        return None

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
        return len(self._instruments)
