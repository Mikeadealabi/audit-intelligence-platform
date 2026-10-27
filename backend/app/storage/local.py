from pathlib import Path

from app.services.encryption import decrypt_bytes, encrypt_bytes
from app.storage.base import FileStorage


class LocalFilesystemStorage(FileStorage):
    """Dev-only adapter. Not web-served. File bytes are encrypted at rest with
    app-level Fernet encryption (app/services/encryption.py) before being written,
    specifically to compensate for this adapter having no infra-level encryption
    of its own — a production adapter (e.g. S3-compatible) may instead rely on the
    storage provider's server-side encryption, but this dev adapter cannot assume
    that. Do not point this at a production deployment regardless."""

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
            f.write(encrypt_bytes(data))
        return str(full_path)

    def read(self, key: str) -> bytes:
        full_path = self._resolve(key)
        with open(full_path, "rb") as f:
            return decrypt_bytes(f.read())

    def delete(self, key: str) -> None:
        full_path = self._resolve(key)
        full_path.unlink(missing_ok=True)
