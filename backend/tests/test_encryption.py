import tempfile

from app.services.encryption import decrypt_bytes, decrypt_json, encrypt_bytes, encrypt_json
from app.storage.local import LocalFilesystemStorage


def test_bytes_round_trip():
    original = b"supplier,amount\nAcme,1000.00\n"
    token = encrypt_bytes(original)
    assert token != original
    assert decrypt_bytes(token) == original


def test_json_round_trip():
    original = {"supplier_name": "Acme", "amount": "1000.00"}
    stored = encrypt_json(original)
    assert set(stored.keys()) == {"_encrypted"}
    assert stored != original
    assert decrypt_json(stored) == original


def test_local_storage_writes_ciphertext_not_plaintext():
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = LocalFilesystemStorage(tmp_dir)
        plaintext = b"supplier,amount\nAcme,1000.00\n"
        path = storage.write("tenant/engagement/file/upload.csv", plaintext)

        with open(path, "rb") as f:
            on_disk = f.read()
        assert on_disk != plaintext
        assert b"Acme" not in on_disk  # not trivially recoverable by reading the file directly

        assert storage.read("tenant/engagement/file/upload.csv") == plaintext


def test_local_storage_delete_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = LocalFilesystemStorage(tmp_dir)
        storage.write("tenant/engagement/file/upload.csv", b"data")
        storage.delete("tenant/engagement/file/upload.csv")
        storage.delete("tenant/engagement/file/upload.csv")  # must not raise
        storage.delete("tenant/engagement/file/never-existed.csv")  # must not raise
