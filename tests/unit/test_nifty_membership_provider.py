"""Unit tests for NIFTY Membership Provider."""

from __future__ import annotations

import json
from pathlib import Path

from axiomra.data.nifty_membership import (
    NIFTYMembershipProvider,
    ReconstructedMembershipRecord,
)
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawStore


def test_nifty_membership_provider_provenance(tmp_path: Path):
    """NIFTYMembershipProvider must parse constituent JSON and record detailed reconstruction provenance."""
    mock_memberships = [
        {
            "instrument_id": "inst-isin-INE002A01018",
            "symbol": "RELIANCE.NS",
            "from_date": "2017-01-01T00:00:00+00:00",
            "until_date": None,
        },
        {
            "instrument_id": "inst-isin-INE467B01029",
            "symbol": "TCS.NS",
            "from_date": "2017-01-01T00:00:00+00:00",
            "until_date": "2023-12-31T00:00:00+00:00",
        },
    ]
    raw_bytes = json.dumps(mock_memberships).encode("utf-8")

    store = LocalArtifactStore(root_dir=tmp_path / "raw")
    raw_store = RawStore(root_dir=tmp_path / "raw", store=store)
    provider = NIFTYMembershipProvider(raw_store=raw_store)

    index_memberships, provenance_records, manifest = provider.parse_membership_source_bytes(
        raw_bytes=raw_bytes,
        index_name="NIFTY 200",
        reconstruction_version="nifty200-reconstructed-v1",
    )

    assert manifest.provider == "nifty_indices"
    assert len(index_memberships) == 2
    assert len(provenance_records) == 2

    rec0 = provenance_records[0]
    assert isinstance(rec0, ReconstructedMembershipRecord)
    assert rec0.index_name == "NIFTY 200"
    assert rec0.instrument_id == "inst-isin-INE002A01018"
    assert rec0.reconstruction_version == "nifty200-reconstructed-v1"
    assert rec0.source == "NSE Indices reconstitution notices & constituent snapshots"
