"""Unit tests for NSE Bhavcopy and Corporate Action providers."""

from __future__ import annotations

from pathlib import Path

from axiomra.data.instruments import CorporateActionType
from axiomra.data.providers.nse import (
    NSEBhavcopyProvider,
    NSECorporateActionProvider,
)
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawStore


def test_nse_bhavcopy_provider_parsing(tmp_path: Path):
    """NSEBhavcopyProvider must parse daily Bhavcopy CSV into Bar dictionary."""
    csv_content = """SYMBOL,SERIES,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,CLOSE_PRICE,TTL_TRD_QTY,TIMESTAMP
RELIANCE,EQ,2500.0,2550.0,2490.0,2540.0,1000000,02-JAN-2024
TCS,EQ,3800.0,3850.0,3790.0,3840.0,500000,02-JAN-2024
NIFTY_FUT,FO,21500.0,21600.0,21400.0,21550.0,10000,02-JAN-2024
"""
    raw_bytes = csv_content.encode("utf-8")

    store = LocalArtifactStore(root_dir=tmp_path / "raw")
    raw_store = RawStore(root_dir=tmp_path / "raw", store=store)
    provider = NSEBhavcopyProvider(raw_store=raw_store)

    bars, manifest = provider.parse_bhavcopy_bytes(
        raw_bytes=raw_bytes,
        trade_date="20240102",
    )

    assert manifest.provider == "nse"
    assert manifest.resource_type == "bhavcopy"
    assert "RELIANCE.NS" in bars
    assert "TCS.NS" in bars
    assert "NIFTY_FUT.NS" not in bars  # Filtered non-EQ series
    assert bars["RELIANCE.NS"].close == 2540.0
    assert bars["TCS.NS"].volume == 500000.0


def test_nse_corporate_action_provider_parsing(tmp_path: Path):
    """NSECorporateActionProvider must parse corporate actions CSV and classify purpose types."""
    csv_content = """SYMBOL,SERIES,PURPOSE,EX-DATE
RELIANCE,EQ,Dividend - Rs 10 Per Share,05-Jan-2024
TCS,EQ,Bonus 1:1,10-Jan-2024
INFY,EQ,Stock Split From Rs 10 To Rs 5,15-Jan-2024
WIPRO,EQ,Demerger,20-Jan-2024
"""
    raw_bytes = csv_content.encode("utf-8")

    store = LocalArtifactStore(root_dir=tmp_path / "raw")
    raw_store = RawStore(root_dir=tmp_path / "raw", store=store)
    provider = NSECorporateActionProvider(raw_store=raw_store)

    actions, manifest = provider.parse_actions_bytes(raw_bytes=raw_bytes)

    assert manifest.provider == "nse"
    assert manifest.resource_type == "corporate_actions"
    assert len(actions) == 4

    # Dividend
    div = next(a for a in actions if a.action_type == CorporateActionType.DIVIDEND)
    assert div.amount == 10.0
    assert div.raw_description == "Dividend - Rs 10 Per Share"
    assert div.source == "NSE"

    # Bonus
    bonus = next(a for a in actions if a.action_type == CorporateActionType.BONUS)
    assert bonus.ratio == 2.0  # 1:1 bonus ratio = (1+1)/1 = 2.0

    # Split
    split = next(a for a in actions if a.action_type == CorporateActionType.SPLIT)
    assert split.ratio == 2.0  # 10 to 5 split ratio = 10/5 = 2.0
