"""Domain models for persisted research datasets."""

from __future__ import annotations

from pydantic import BaseModel

from axiomra.data.instruments import InstrumentMaster
from axiomra.data.snapshot import DatasetSnapshot
from axiomra.storage.manifest import DatasetManifest


class DatasetQualityError(ValueError):
    """Raised when trying to save a dataset that fails data quality validation."""


class PersistedDataset(BaseModel):
    """A restored point-in-time dataset binding snapshot, manifest, and instrument master."""

    model_config = {"arbitrary_types_allowed": True}

    snapshot: DatasetSnapshot
    manifest: DatasetManifest
    instrument_master: InstrumentMaster
