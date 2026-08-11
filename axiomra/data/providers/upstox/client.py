"""Upstox API Client wrapper for fetching instrument master and historical candles."""

from __future__ import annotations

import os
import urllib.parse
import urllib.request


class UpstoxClient:
    """Client for fetching Upstox BOD Instrument Master and V3 Historical Candle data."""

    BOD_INSTRUMENT_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json"
    HISTORICAL_CANDLE_URL_FMT = (
        "https://api.upstox.com/v3/historical-candle/{quoted_key}/days/1/{to_date}/{from_date}"
    )

    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token or os.environ.get("UPSTOX_ACCESS_TOKEN")

    def fetch_bod_instruments_bytes(self, mock_bytes: bytes | None = None) -> bytes:
        """Fetch unparsed BOD JSON instrument master bytes."""
        if mock_bytes is not None:
            return mock_bytes

        headers = {"User-Agent": "Axiomra/1.0", "Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        req = urllib.request.Request(self.BOD_INSTRUMENT_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()

    def fetch_historical_candles_bytes(
        self,
        instrument_key: str,
        start_date: str,
        end_date: str,
        mock_bytes: bytes | None = None,
    ) -> bytes:
        """Fetch unparsed Upstox V3 historical candle JSON bytes.

        URL structure: /v3/historical-candle/{instrument_key}/days/1/{to_date}/{from_date}
        `instrument_key` is URL-encoded (e.g. quote_plus("NSE_EQ|INE002A01018")).
        """
        if mock_bytes is not None:
            return mock_bytes

        quoted_key = urllib.parse.quote_plus(instrument_key)
        url = self.HISTORICAL_CANDLE_URL_FMT.format(
            quoted_key=quoted_key,
            to_date=end_date,
            from_date=start_date,
        )

        headers = {"User-Agent": "Axiomra/1.0", "Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
