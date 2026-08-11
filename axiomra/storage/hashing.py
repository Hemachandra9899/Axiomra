"""SHA-256 hashing utilities for artifact verification."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hash string over bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Compute SHA-256 hash string over a file on disk."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()
