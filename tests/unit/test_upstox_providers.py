"""Unit tests for Upstox Instrument Master and Historical Candle providers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from axiomra.data.providers.upstox import (
    UpstoxHistoricalProvider,
    UpstoxInstrumentProvider,
)
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawStore


def test_upstox_instrument_provider_parsing(tmp_path: Path):
    """UpstoxInstrumentProvider must parse BOD JSON and populate InstrumentMaster."""
    mock_bod = [
        {
            "instrument_key": "NSE_EQ|INE002A01018",
            "trading_symbol": "RELIANCE",
            "name": "RELIANCE INDUSTRIES LTD",
            "exchange": "NSE",
            "instrument_type": "EQ",
            "isin": "INE002A01018",
        },
        {
            "instrument_key": "NSE_EQ|INE467B01029",
            "trading_symbol": "TCS",
            "name": "TATA CONSULTANCY SERVICES LTD",
            "exchange": "NSE",
            "instrument_type": "EQ",
            "isin": "INE467B01029",
        },
        {
            "instrument_key": "NSE_FO|12345",
            "trading_symbol": "NIFTY24JANFUT",
            "exchange": "NSE",
            "instrument_type": "FUT",
        },
    ]
    mock_bytes = json.dumps(mock_bod).encode("utf-8")

    store = LocalArtifactStore(root_dir=tmp_path / "raw")
    raw_store = RawStore(root_dir=tmp_path / "raw", store=store)
    provider = UpstoxInstrumentProvider(raw_store=raw_store)

    master, manifest, key_map = provider.fetch_and_parse(mock_bytes=mock_bytes)

    assert manifest.provider == "upstox"
    assert manifest.resource_type == "instruments"
    assert "NSE_EQ|INE002A01018" in key_map
    # Verify canonical instrument_id is ISIN-based
    assert key_map["NSE_EQ|INE002A01018"] == "inst-isin-INE002A01018"
    assert key_map["NSE_EQ|INE002A01018"] != "NSE_EQ|INE002A01018"  # Must NOT make instrument_key canonical ID

    inst = master.resolve_symbol("RELIANCE.NS", datetime(2024, 1, 1, tzinfo=UTC))
    assert inst is not None
    assert inst.instrument_id == "inst-isin-INE002A01018"
    assert inst.isin == "INE002A01018"


def test_upstox_historical_provider_parsing(tmp_path: Path):
    """UpstoxHistoricalProvider must parse V3 Candle response into Bar objects."""
    mock_candle_response = {
        "status": "success",
        "data": {
            "candles": [
                ["2024-01-02T00:00:00+05:30", 2500.0, 2550.0, 2490.0, 2540.0, 1000000, 0],
                ["2024-01-03T00:00:00+05:30", 2540.0, 2560.0, 2520.0, 2550.0, 1200000, 0],
            ]
        },
    }
    mock_bytes = json.dumps(mock_candle_response).encode("utf-8")

    store = LocalArtifactStore(root_dir=tmp_path / "raw")
    raw_store = RawStore(root_dir=tmp_path / "raw", store=store)
    provider = UpstoxHistoricalProvider(raw_store=raw_store)

    bars, manifest = provider.fetch_and_parse_candles(
        instrument_key="NSE_EQ|INE002A01018",
        symbol="RELIANCE.NS",
        start_date="2024-01-01",
        end_date="2024-01-05",
        mock_bytes=mock_bytes,
    )

    assert manifest.provider == "upstox"
    assert manifest.resource_type == "historical"
    assert len(bars) == 2
    assert bars[0].symbol == "RELIANCE.NS"
    assert bars[0].close == 2540.0
    assert bars[1].close == 2550.0
    assert bars[0].timestamp.tzinfo is not None
