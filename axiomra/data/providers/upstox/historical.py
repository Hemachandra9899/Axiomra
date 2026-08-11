"""Upstox V3 Historical Candle Provider."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from axiomra.data.providers.upstox.client import UpstoxClient
from axiomra.domain.market import Bar
from axiomra.storage.raw import RawFetchManifest, RawStore


class UpstoxHistoricalProvider:
    """Fetches daily candles from Upstox V3 API and normalizes to Axiomra Bars."""

    def __init__(
        self,
        raw_store: RawStore | None = None,
        client: UpstoxClient | None = None,
    ) -> None:
        self.raw_store = raw_store or RawStore()
        self.client = client or UpstoxClient()

    def fetch_and_parse_candles(
        self,
        instrument_key: str,
        symbol: str,
        start_date: str,
        end_date: str,
        mock_bytes: bytes | None = None,
        parser_version: str = "v1",
    ) -> tuple[list[Bar], RawFetchManifest]:
        """Fetch historical candle JSON, save to RawStore with manifest, parse to Bars."""
        raw_bytes = self.client.fetch_historical_candles_bytes(
            instrument_key=instrument_key,
            start_date=start_date,
            end_date=end_date,
            mock_bytes=mock_bytes,
        )

        safe_symbol = symbol.replace("/", "_").replace(":", "_")
        filename = f"{safe_symbol}_{start_date}_to_{end_date}.json"
        manifest = self.raw_store.put_raw(
            provider="upstox",
            resource_type="historical",
            filename=filename,
            data=raw_bytes,
            request_parameters={
                "instrument_key": instrument_key,
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
            },
            parser_version=parser_version,
        )

        payload: dict[str, Any] = json.loads(raw_bytes.decode("utf-8"))
        candles = payload.get("data", {}).get("candles", [])

        bars: list[Bar] = []
        symbol_ns = symbol if symbol.endswith(".NS") else f"{symbol}.NS"

        for candle in candles:
            # candle format: [timestamp, open, high, low, close, volume, open_interest]
            if len(candle) < 6:
                continue
            ts_str = str(candle[0])
            dt = datetime.fromisoformat(ts_str)
            dt_utc = dt.astimezone(UTC)

            bars.append(
                Bar(
                    symbol=symbol_ns,
                    timestamp=dt_utc,
                    open=float(candle[1]),
                    high=float(candle[2]),
                    low=float(candle[3]),
                    close=float(candle[4]),
                    volume=float(candle[5]),
                )
            )

        bars.sort(key=lambda b: b.timestamp)
        return bars, manifest
