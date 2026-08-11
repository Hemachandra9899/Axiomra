"""Live Network Integration Test — NSE India EOD Bhavcopy and Corporate Actions.

Requires active internet access.
Execute explicitly via: `pytest -m live`
"""

from __future__ import annotations

from pathlib import Path

import pytest

from axiomra.data.providers.nse import (
    NSEBhavcopyProvider,
    NSEClient,
    NSECorporateActionProvider,
)
from axiomra.storage.raw import RawStore


@pytest.mark.live
def test_nse_live_bhavcopy_download_and_parse(tmp_path: Path):
    """Download live NSE CM-UDiFF Bhavcopy ZIP from niftyindices.com, extract CSV, and parse."""
    raw_store = RawStore(root_dir=tmp_path / "live_raw")
    client = NSEClient(raw_store=raw_store)
    bhavcopy_provider = NSEBhavcopyProvider(raw_store=raw_store)

    try:
        csv_bytes, manifest = client.fetch_bhavcopy_bytes(trade_date="20240603")
    except Exception as exc:
        pytest.skip(f"NSE live network endpoint unavailable: {exc}")

    assert manifest.provider == "nse"
    assert manifest.sha256 is not None

    bars, _ = bhavcopy_provider.parse_bhavcopy_bytes(
        raw_bytes=csv_bytes,
        trade_date="20240603",
    )
    assert len(bars) > 100


@pytest.mark.live
def test_nse_live_corporate_actions_download_and_parse(tmp_path: Path):
    """Download live NSE Corporate Action CSV export and parse structured events."""
    raw_store = RawStore(root_dir=tmp_path / "live_raw")
    client = NSEClient(raw_store=raw_store)
    actions_provider = NSECorporateActionProvider(raw_store=raw_store)

    try:
        csv_bytes, manifest = client.fetch_corporate_actions_bytes()
    except Exception as exc:
        pytest.skip(f"NSE corporate actions endpoint unavailable: {exc}")

    assert manifest.provider == "nse"
    actions, _ = actions_provider.parse_actions_bytes(raw_bytes=csv_bytes)
    assert len(actions) > 0
