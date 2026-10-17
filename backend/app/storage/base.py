from abc import ABC, abstractmethod


class FileStorage(ABC):
    """A production implementation (e.g. S3-compatible) must implement this same
    interface and must not accept a client-controlled path — callers always pass a
    server-generated, tenant/engagement-namespaced key."""

    @abstractmethod
    def write(self, key: str, data: bytes) -> str:
        """Writes data under key, returns a storage-backend-specific path/URI."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        ...
