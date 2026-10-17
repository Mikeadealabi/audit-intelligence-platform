import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TenantMembership
from app.security import InvalidToken, decode_access_token
from app.services.llm.orchestrator import InvestigationUnavailable, provider_from_settings
from app.services.llm.provider import LLMProvider

_bearer = HTTPBearer()


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str


def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Principal:
    """Authenticates the request and re-checks membership against the DB on every
    call, so a revoked membership takes effect immediately rather than waiting for a
    token to expire."""
    try:
        user_id, tenant_id = decode_access_token(credentials.credentials)
    except InvalidToken as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    membership = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Membership not found or revoked")

    return Principal(user_id=user_id, tenant_id=tenant_id, role=membership.role)


def require_admin(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return principal


def get_llm_provider() -> LLMProvider:
    """Overridden in tests with a fake provider — never hits the real API in the
    test suite. A FastAPI dependency can only signal failure via HTTPException
    (a plain exception here would surface as an unhandled 500), so the
    not-configured case is translated to a 503 right here."""
    try:
        return provider_from_settings()
    except InvestigationUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
