"""Raw Data Storage and Manifest Management.

Implements the immutable raw storage layer. Every fetched provider payload
(Upstox BOD JSON, Upstox V3 candle API responses, NSE Bhavcopy CSVs,
NSE Corporate Action CSVs, NIFTY Index constituent files) is saved unaltered
with a corresponding SHA-256 `RawFetchManifest`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from axiomra.storage.base import ArtifactStore
from axiomra.storage.hashing import sha256_bytes
from axiomra.storage.local import LocalArtifactStore


class RawFetchManifest(BaseModel):
    """Immutable audit record for a single raw data fetch from an external provider."""

    model_config = {"frozen": True}

    provider: str
    fetched_at: datetime
    resource_type: str
    request_parameters: dict[str, Any] = Field(default_factory=dict)
    raw_path: str
    sha256: str
    parser_version: str = "v1"


class RawStore:
    """Manages raw provider file persistence and corresponding manifests under a structured path."""

    def __init__(
        self,
        root_dir: str | Path = "axiomra-data/raw",
        store: ArtifactStore | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.store = store or LocalArtifactStore(root_dir=self.root_dir)

    def put_raw(
        self,
        provider: str,
        resource_type: str,
        filename: str,
        data: bytes,
        request_parameters: dict[str, Any] | None = None,
        parser_version: str = "v1",
    ) -> RawFetchManifest:
        """Store raw unparsed bytes and generate SHA-256 `RawFetchManifest`."""
        key = f"{provider}/{resource_type}/{filename}"
        sha = sha256_bytes(data)
        manifest = RawFetchManifest(
            provider=provider,
            fetched_at=datetime.now(UTC),
            resource_type=resource_type,
            request_parameters=request_parameters or {},
            raw_path=key,
            sha256=sha,
            parser_version=parser_version,
        )

        self.store.put_bytes(key, data)
        manifest_key = f"{key}.manifest.json"
        manifest_bytes = manifest.model_dump_json(indent=2).encode("utf-8")
        self.store.put_bytes(manifest_key, manifest_bytes)

        return manifest

    def get_raw(self, raw_path: str) -> bytes:
        """Retrieve raw bytes by key."""
        return self.store.get_bytes(raw_path)

    def get_manifest(self, raw_path: str) -> RawFetchManifest:
        """Retrieve fetch manifest corresponding to a raw file key."""
        manifest_key = f"{raw_path}.manifest.json"
        manifest_bytes = self.store.get_bytes(manifest_key)
        return RawFetchManifest.model_validate_json(manifest_bytes.decode("utf-8"))

    def exists(self, raw_path: str) -> bool:
        """Check if raw file key exists."""
        return self.store.exists(raw_path)
