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


def test_nifty_membership_provider_strict_missing_from_date_raises(tmp_path: Path):
    """Missing 'from_date' in membership record must raise ValueError."""
    import pytest

    mock_bad = [{"symbol": "RELIANCE.NS", "instrument_id": "inst-1"}]
    provider = NIFTYMembershipProvider(raw_store=RawStore(root_dir=tmp_path / "raw"))

    with pytest.raises(ValueError, match="Manufacturing arbitrary historical start dates is prohibited"):
        provider.parse_membership_source_bytes(json.dumps(mock_bad).encode("utf-8"))


def test_nifty_membership_provider_mismatched_identity_raises(tmp_path: Path):
    """Supplied instrument_id mismatching resolved symbol ID at from_date must raise ValueError."""
    from datetime import UTC, datetime

    import pytest

    from axiomra.data.instruments import Instrument, InstrumentMaster

    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="INST-RELIANCE-REAL",
            symbol="RELIANCE.NS",
            active_from=datetime(2017, 1, 1, tzinfo=UTC),
        )
    )
    master.upsert(
        Instrument(
            instrument_id="INST-TCS-REAL",
            symbol="TCS.NS",
            active_from=datetime(2017, 1, 1, tzinfo=UTC),
        )
    )

    # Mismatched pair: RELIANCE.NS paired with TCS ID
    mismatched_input = [
        {
            "instrument_id": "INST-TCS-REAL",
            "symbol": "RELIANCE.NS",
            "from_date": "2017-01-01T00:00:00+00:00",
            "until_date": None,
        }
    ]

    provider = NIFTYMembershipProvider(raw_store=RawStore(root_dir=tmp_path / "raw"))
    with pytest.raises(ValueError, match="Membership identity mismatch"):
        provider.parse_membership_source_bytes(
            json.dumps(mismatched_input).encode("utf-8"),
            instruments=master,
        )


def test_nifty_membership_provider_unresolvable_instrument_id_raises(tmp_path: Path):
    """Unresolvable 'instrument_id' in membership record must raise ValueError."""
    mock_bad = [{"symbol": "UNKNOWN.NS", "from_date": "2020-01-01T00:00:00+00:00"}]
    provider = NIFTYMembershipProvider(raw_store=RawStore(root_dir=tmp_path / "raw"))

    import pytest
    with pytest.raises(ValueError, match="instrument_id"):
        provider.parse_membership_source_bytes(json.dumps(mock_bad).encode("utf-8"))
