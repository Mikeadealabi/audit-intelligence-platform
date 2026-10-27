import json

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken as _FernetInvalidToken

from app.config import settings

# Reads settings.file_encryption_key fresh on every call (never cached at import
# time) — same convention as app/security.py's jwt_secret usage, so tests can
# monkeypatch settings.file_encryption_key without import-order games.


class EncryptionError(Exception):
    pass


def _fernet() -> Fernet:
    try:
        return Fernet(settings.file_encryption_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise EncryptionError("FILE_ENCRYPTION_KEY is not a valid Fernet key") from exc


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    try:
        return _fernet().decrypt(token)
    except _FernetInvalidToken as exc:
        raise EncryptionError("Could not decrypt — wrong key or corrupted ciphertext") from exc


def encrypt_json(obj: dict) -> dict:
    """Wraps ciphertext in {"_encrypted": "<token>"} so a JSON-typed column's
    Python-side contract (dict) never changes — no column migration needed."""
    token = _fernet().encrypt(json.dumps(obj).encode("utf-8")).decode("ascii")
    return {"_encrypted": token}


def decrypt_json(stored: dict) -> dict:
    token = stored["_encrypted"]
    try:
        plaintext = _fernet().decrypt(token.encode("ascii"))
    except _FernetInvalidToken as exc:
        raise EncryptionError("Could not decrypt — wrong key or corrupted ciphertext") from exc
    return json.loads(plaintext)
