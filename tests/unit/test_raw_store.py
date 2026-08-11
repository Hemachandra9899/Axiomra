"""Unit tests for Raw Data Storage and Manifest Management."""

from __future__ import annotations

from pathlib import Path

from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawFetchManifest, RawStore


def test_put_and_get_raw_with_manifest(tmp_path: Path):
    """RawStore must store raw payload bytes and produce matching RawFetchManifest."""
    store = LocalArtifactStore(root_dir=tmp_path / "raw_test")
    raw_store = RawStore(root_dir=tmp_path / "raw_test", store=store)

    data = b'{"status": "success", "data": [1, 2, 3]}'
    params = {"symbol": "RELIANCE", "timeframe": "1d"}

    manifest = raw_store.put_raw(
        provider="upstox",
        resource_type="historical",
        filename="RELIANCE_2024.json",
        data=data,
        request_parameters=params,
        parser_version="v1",
    )

    assert isinstance(manifest, RawFetchManifest)
    assert manifest.provider == "upstox"
    assert manifest.resource_type == "historical"
    assert manifest.raw_path == "upstox/historical/RELIANCE_2024.json"
    assert manifest.request_parameters == params

    # Retrieve raw bytes
    retrieved_data = raw_store.get_raw(manifest.raw_path)
    assert retrieved_data == data

    # Retrieve manifest
    retrieved_manifest = raw_store.get_manifest(manifest.raw_path)
    assert retrieved_manifest.sha256 == manifest.sha256
    assert retrieved_manifest.raw_path == manifest.raw_path
