"""Live Network Integration Test — NIFTY Indices Source Loader.

Requires active internet access.
Execute explicitly via: `pytest -m live`
"""

from __future__ import annotations

from pathlib import Path

import pytest

from axiomra.data.nifty_loader import NSEIndicesSourceLoader
from axiomra.storage.raw import RawStore


@pytest.mark.live
def test_nifty_live_constituents_download(tmp_path: Path):
    """Download live NIFTY 200 constituent CSV from niftyindices.com."""
    raw_store = RawStore(root_dir=tmp_path / "live_raw")
    loader = NSEIndicesSourceLoader(raw_store=raw_store)

    try:
        csv_bytes, manifest = loader.fetch_index_constituents_bytes(index_name="NIFTY 200")
    except Exception as exc:
        pytest.skip(f"NIFTY Indices constituent endpoint unavailable: {exc}")

    assert manifest.provider == "nifty_indices"
    assert manifest.sha256 is not None
    assert len(csv_bytes) > 500
