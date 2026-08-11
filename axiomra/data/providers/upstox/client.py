"""Upstox API Client wrapper for fetching instrument master and historical candles."""

from __future__ import annotations

import urllib.request


class UpstoxClient:
    """Client for fetching Upstox BOD Instrument Master and V3 Historical Candle data."""

    BOD_INSTRUMENT_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json"
    HISTORICAL_CANDLE_URL_FMT = "https://api.upstox.com/v3/historical-candle/{instrument_key}/day/{end_date}/{start_date}"

    def fetch_bod_instruments_bytes(self, mock_bytes: bytes | None = None) -> bytes:
        """Fetch unparsed BOD JSON instrument master bytes."""
        if mock_bytes is not None:
            return mock_bytes

        req = urllib.request.Request(
            self.BOD_INSTRUMENT_URL,
            headers={"User-Agent": "Axiomra/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()

    def fetch_historical_candles_bytes(
        self,
        instrument_key: str,
        start_date: str,
        end_date: str,
        mock_bytes: bytes | None = None,
    ) -> bytes:
        """Fetch unparsed Upstox V3 historical candle JSON bytes."""
        if mock_bytes is not None:
            return mock_bytes

        url = self.HISTORICAL_CANDLE_URL_FMT.format(
            instrument_key=instrument_key,
            start_date=start_date,
            end_date=end_date,
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Axiomra/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
