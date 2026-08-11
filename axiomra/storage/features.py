"""Feature artifact repository for persisting computed feature tables."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from axiomra.storage.base import ArtifactStore
from axiomra.storage.hashing import sha256_bytes
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.manifest import (
    SUPPORTED_FEATURE_SCHEMAS,
    FeatureManifest,
    UnsupportedSchemaError,
)


class FeatureRepository:
    """Repository for persisting and restoring feature artifacts separate from market datasets."""

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store or LocalArtifactStore()

    def _feature_dir(self, feature_id: str) -> str:
        return f"features/{feature_id}"

    def save_features(
        self,
        features_df: pd.DataFrame,
        dataset_id: str,
        dataset_checksum: str,
        feature_version: str = "f1",
        parameters: dict[str, Any] | None = None,
    ) -> FeatureManifest:
        feature_cols = [c for c in features_df.columns if c not in {"instrument_id", "symbol", "timestamp", "date"}]
        buf = io.BytesIO()
        features_df.to_parquet(buf, index=False)
        bytes_feat = buf.getvalue()
        file_hash = sha256_bytes(bytes_feat)

        # Content checksum over deterministic JSON of parameters & feature names
        content_payload = {
            "dataset_checksum": dataset_checksum,
            "feature_version": feature_version,
            "feature_names": sorted(feature_cols),
            "parameters": parameters or {},
            "file_sha256": file_hash,
        }
        content_checksum = sha256_bytes(json.dumps(content_payload, sort_keys=True).encode("utf-8"))
        feature_id = f"feat-{content_checksum[:12]}"
        prefix = self._feature_dir(feature_id)

        key_feat = f"{prefix}/features.parquet"
        self.store.put_bytes(key_feat, bytes_feat)

        manifest = FeatureManifest(
            schema_version="features-v1",
            feature_artifact_id=feature_id,
            dataset_id=dataset_id,
            dataset_checksum=dataset_checksum,
            feature_version=feature_version,
            feature_names=feature_cols,
            parameters=parameters or {},
            file_sha256=file_hash,
            content_checksum=content_checksum,
            created_at=datetime.now(UTC),
        )

        bytes_manifest = manifest.model_dump_json(indent=2).encode("utf-8")
        key_manifest = f"{prefix}/manifest.json"
        self.store.put_bytes(key_manifest, bytes_manifest)

        return manifest

    def load_features(self, feature_id: str) -> tuple[pd.DataFrame, FeatureManifest]:
        prefix = self._feature_dir(feature_id)
        key_manifest = f"{prefix}/manifest.json"
        if not self.store.exists(key_manifest):
            raise FileNotFoundError(f"Feature manifest not found: {key_manifest}")

        manifest_data = json.loads(self.store.get_bytes(key_manifest).decode("utf-8"))
        manifest = FeatureManifest.model_validate(manifest_data)

        if manifest.schema_version not in SUPPORTED_FEATURE_SCHEMAS:
            raise UnsupportedSchemaError(f"Unsupported feature schema version: {manifest.schema_version!r}")

        bytes_feat = self.store.get_bytes(f"{prefix}/features.parquet")
        df = pd.read_parquet(io.BytesIO(bytes_feat))
        return df, manifest

    def verify_features(self, feature_id: str) -> bool:
        prefix = self._feature_dir(feature_id)
        key_manifest = f"{prefix}/manifest.json"
        if not self.store.exists(key_manifest):
            return False

        try:
            manifest_data = json.loads(self.store.get_bytes(key_manifest).decode("utf-8"))
            manifest = FeatureManifest.model_validate(manifest_data)

            bytes_feat = self.store.get_bytes(f"{prefix}/features.parquet")
            actual_hash = sha256_bytes(bytes_feat)
            return actual_hash == manifest.file_sha256
        except Exception:
            return False
