from pathlib import Path

from app.storage.base import FileStorage


class LocalFilesystemStorage(FileStorage):
    """Dev-only adapter. Not web-served, not encrypted at rest beyond whatever the
    host filesystem provides. Do not point this at a production deployment."""

    def __init__(self, base_dir: str):
        self._base_dir = Path(base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # key is always server-generated (tenant_id/engagement_id/source_file_id),
        # but resolve-and-check anyway so a future caller can't escape the base dir.
        full_path = (self._base_dir / key).resolve()
        if self._base_dir not in full_path.parents and full_path != self._base_dir:
            raise ValueError("Resolved path escapes storage base directory")
        return full_path

    def write(self, key: str, data: bytes) -> str:
        full_path = self._resolve(key)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(data)
        return str(full_path)

    def read(self, key: str) -> bytes:
        full_path = self._resolve(key)
        with open(full_path, "rb") as f:
            return f.read()
