"""Local disk implementation of ArtifactStore."""

from __future__ import annotations

from pathlib import Path

from axiomra.storage.base import ArtifactStore


class LocalArtifactStore(ArtifactStore):
    """Stores artifacts on local filesystem under root_dir (defaults to artifacts/)."""

    def __init__(self, root_dir: str | Path = "artifacts") -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        return self.root_dir / key

    def put_bytes(self, key: str, data: bytes) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return str(target)

    def get_bytes(self, key: str) -> bytes:
        target = self._resolve(key)
        if not target.exists():
            raise FileNotFoundError(f"Artifact not found: {key} (at {target})")
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> bool:
        target = self._resolve(key)
        if target.exists():
            target.unlink()
            return True
        return False
