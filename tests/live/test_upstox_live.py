"""Live Network Integration Test — Upstox API Providers.

Requires active internet access and optional `UPSTOX_ACCESS_TOKEN`.
Execute explicitly via: `pytest -m live`
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from axiomra.data.providers.upstox import (
    UpstoxClient,
    UpstoxHistoricalProvider,
    UpstoxInstrumentProvider,
)
from axiomra.storage.raw import RawStore


@pytest.mark.live
def test_upstox_live_bod_master_fetch(tmp_path: Path):
    """Fetch live Upstox BOD instrument master JSON from assets.upstox.com and parse into InstrumentMaster."""
    raw_store = RawStore(root_dir=tmp_path / "live_raw")
    client = UpstoxClient()
    provider = UpstoxInstrumentProvider(raw_store=raw_store, client=client)

    master, manifest, key_map = provider.fetch_and_parse()

    assert manifest.provider == "upstox"
    assert manifest.sha256 is not None
    assert len(master._all_instruments) > 100
    assert len(key_map) > 100


@pytest.mark.live
def test_upstox_live_reliance_candle_fetch(tmp_path: Path):
    """Fetch live Upstox V3 historical candles for RELIANCE.NS.

    Requires `UPSTOX_ACCESS_TOKEN` environment variable for V3 API access.
    """
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        pytest.skip("UPSTOX_ACCESS_TOKEN not set — skipping live V3 candle API test")

    raw_store = RawStore(root_dir=tmp_path / "live_raw")
    client = UpstoxClient(access_token=token)
    provider = UpstoxHistoricalProvider(raw_store=raw_store, client=client)

    bars, manifest = provider.fetch_and_parse_candles(
        instrument_key="NSE_EQ|INE002A01018",
        symbol="RELIANCE.NS",
        start_date="2024-01-01",
        end_date="2024-01-10",
    )

    assert manifest.provider == "upstox"
    assert len(bars) > 0
    assert bars[0].symbol == "RELIANCE.NS"
