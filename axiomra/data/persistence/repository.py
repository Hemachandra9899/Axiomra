"""DatasetRepository abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from axiomra.data.instruments import InstrumentMaster
from axiomra.data.persistence.models import PersistedDataset
from axiomra.data.snapshot import DatasetSnapshot
from axiomra.storage.manifest import DatasetManifest


class DatasetRepository(ABC):
    """Abstract interface for dataset persistence repositories."""

    @abstractmethod
    def save(
        self,
        snapshot: DatasetSnapshot,
        instruments: InstrumentMaster,
        allow_invalid: bool = False,
    ) -> DatasetManifest:
        """Persist snapshot and instrument master as a dataset artifact."""

    @abstractmethod
    def load(
        self,
        dataset_id: str,
    ) -> PersistedDataset:
        """Load and restore a persisted dataset artifact by dataset_id."""

    @abstractmethod
    def verify(
        self,
        dataset_id: str,
    ) -> bool:
        """Verify artifact checksum and file integrity for dataset_id."""
