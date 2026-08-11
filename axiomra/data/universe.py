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

from pydantic import BaseModel

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
