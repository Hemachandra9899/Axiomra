"""NIFTY 50 universe seed (V1).

Universe = a point-in-time list of tradable symbols with membership history.
The authoritative source is the NSE index factsheet; this seed is the V1
development list and MUST be verified/refreshed against the factsheet before
production use. Membership changes over time, so a production system records
`index_memberships` (instrument_id, from, until) per index.

Load rule: read `universe/nifty50.csv`. When the file is missing (e.g. a
stripped checkout), fall back to the embedded seed tuple so development keeps
working without network access.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, field_validator

from axiomra.domain.common import as_utc

UNIVERSE_SEED = "nifty50-v1"

# Development seed — symbol, sector. Verify against NSE factsheet before use.
_NIFTY_50_SEED: tuple[tuple[str, str], ...] = (
    ("RELIANCE.NS", "Energy"),
    ("TCS.NS", "Information Technology"),
    ("HDFCBANK.NS", "Financial Services"),
    ("ICICIBANK.NS", "Financial Services"),
    ("INFY.NS", "Information Technology"),
    ("BHARTIARTL.NS", "Telecommunication"),
    ("SBIN.NS", "Financial Services"),
    ("KOTAKBANK.NS", "Financial Services"),
    ("AXISBANK.NS", "Financial Services"),
    ("HINDUNILVR.NS", "FMCG"),
    ("ITC.NS", "FMCG"),
    ("LT.NS", "Infrastructure"),
    ("BAJFINANCE.NS", "Financial Services"),
    ("MARUTI.NS", "Automobile"),
    ("SUNPHARMA.NS", "Pharmaceuticals"),
    ("HCLTECH.NS", "Information Technology"),
    ("TITAN.NS", "Consumer Durables"),
    ("ULTRACEMCO.NS", "Cement"),
    ("ADANIENT.NS", "Conglomerate"),
    ("ASIANPAINT.NS", "Consumer Durables"),
    ("BAJAJFINSV.NS", "Financial Services"),
    ("HDFC.NS", "Financial Services"),
    ("JSWSTEEL.NS", "Metals"),
    ("NTPC.NS", "Energy"),
    ("POWERGRID.NS", "Energy"),
    ("TATAMOTORS.NS", "Automobile"),
    ("TATASTEEL.NS", "Metals"),
    ("WIPRO.NS", "Information Technology"),
    ("ADANIPORTS.NS", "Infrastructure"),
    ("APOLLOHOSP.NS", "Healthcare"),
    ("BRITANNIA.NS", "FMCG"),
    ("COALINDIA.NS", "Energy"),
    ("DRREDDY.NS", "Pharmaceuticals"),
    ("EICHERMOT.NS", "Automobile"),
    ("GRASIM.NS", "Cement"),
    ("HINDALCO.NS", "Metals"),
    ("INDUSINDBK.NS", "Financial Services"),
    ("NESTLEIND.NS", "FMCG"),
    ("ONGC.NS", "Energy"),
    ("SHREECEM.NS", "Cement"),
    ("TECHM.NS", "Information Technology"),
    ("UPL.NS", "Agrochemicals"),
    ("CIPLA.NS", "Pharmaceuticals"),
    ("HEROMOTOCO.NS", "Automobile"),
    ("SBILIFE.NS", "Insurance"),
    ("HDFCLIFE.NS", "Insurance"),
    ("DIVISLAB.NS", "Pharmaceuticals"),
    ("BAJAJ-AUTO.NS", "Automobile"),
    ("TATACONSUM.NS", "FMCG"),
    ("M&M.NS", "Automobile"),
)

NIFTY_50 = tuple(symbol for symbol, _ in _NIFTY_50_SEED)
SECTOR_OF: dict[str, str] = {symbol: sector for symbol, sector in _NIFTY_50_SEED}


class Universe(BaseModel):
    """A versioned, point-in-time universe."""

    name: str
    version: str
    as_of: datetime
    members: list[str]

    def contains(self, symbol: str) -> bool:
        return symbol in self.members


def load_universe_csv(
    path: str | Path | None = None,
    name: str = "NIFTY 50",
) -> Universe:
    """Load a universe from a CSV (symbol[,sector]) or the embedded seed."""
    csv_path = Path(path) if path else Path(__file__).parent / "universe" / "nifty50.csv"

    if csv_path.exists():
        rows: list[tuple[str, str]] = []
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                symbol = (row.get("symbol") or "").strip()
                sector = (row.get("sector") or "").strip()
                if symbol:
                    rows.append((symbol, sector))
        members = tuple(s for s, _ in rows)
    else:
        members = NIFTY_50
    return Universe(

        name=name,
        version=UNIVERSE_SEED,
        as_of=datetime.now(UTC),
        members=list(members),
    )


class IndexMembership(BaseModel):

    """Point-in-time membership of an instrument in a market index."""

    instrument_id: str
    symbol: str
    index_name: str
    from_date: datetime
    until_date: datetime | None = None

    @field_validator("from_date", "until_date")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None

    def is_active(self, as_of: datetime) -> bool:
        utc_as_of = as_utc(as_of)
        if utc_as_of < self.from_date:
            return False
        if self.until_date is not None and utc_as_of > self.until_date:
            return False
        return True


class HistoricalUniverseRegistry:
    """Registry managing historical index memberships for point-in-time universe retrieval."""

    def __init__(self) -> None:
        self._memberships: list[IndexMembership] = []

    def add_membership(self, membership: IndexMembership) -> None:
        self._memberships.append(membership)

    def constituents_at(self, index_name: str, as_of: datetime) -> list[str]:
        """Return symbols of all active index constituents as of a date."""
        utc_as_of = as_utc(as_of)
        active_symbols: list[str] = []
        for m in self._memberships:
            if m.index_name.upper() == index_name.upper() and m.is_active(utc_as_of):
                if m.symbol not in active_symbols:
                    active_symbols.append(m.symbol)
        return active_symbols

    def load_universe_at(
        self,
        index_name: str,
        as_of: datetime,
        version: str = "pit-v1",
    ) -> Universe:
        """Construct a Universe object representing exact point-in-time membership."""
        members = self.constituents_at(index_name, as_of)
        return Universe(
            name=index_name,
            version=version,
            as_of=as_utc(as_of),
            members=members,
        )

