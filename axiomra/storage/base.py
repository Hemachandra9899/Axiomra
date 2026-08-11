"""Abstract base storage interface for Axiomra artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ArtifactStore(ABC):
    """Abstract interface for artifact storage (local disk, S3, etc.)."""

    @abstractmethod
    def put_bytes(self, key: str, data: bytes) -> str:
        """Store bytes under key. Returns key or URI."""

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        """Retrieve bytes stored under key."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in storage."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete key from storage."""
