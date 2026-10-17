import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# passlib (previously used here) is unmaintained and crashes against bcrypt>=4.1
# ("password cannot be longer than 72 bytes" / "_bcrypt.__about__" AttributeError) —
# calling bcrypt directly avoids that broken compatibility shim.


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "tid": str(tenant_id), "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class InvalidToken(Exception):
    pass


def decode_access_token(token: str) -> tuple[uuid.UUID, uuid.UUID]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return uuid.UUID(payload["sub"]), uuid.UUID(payload["tid"])
    except (JWTError, KeyError, ValueError) as exc:
        raise InvalidToken from exc
