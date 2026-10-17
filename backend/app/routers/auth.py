from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppUser, Tenant, TenantMembership
from app.schemas import LoginRequest, SignupRequest, TokenResponse
from app.security import create_access_token, hash_password, verify_password
from app.services.audit import record_audit_event
from app.services.rate_limit import login_rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Creates a brand-new tenant plus its first admin user. There is no invite-only
    tenant join flow in this slice — a user always creates their own tenant."""
    existing = db.execute(select(AppUser).where(AppUser.email == body.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = AppUser(email=body.email, password_hash=hash_password(body.password))
    tenant = Tenant(name=body.tenant_name)
    db.add_all([user, tenant])
    db.flush()

    membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role="admin")
    db.add(membership)
    record_audit_event(
        db,
        tenant_id=tenant.id,
        actor_user_id=user.id,
        event_type="auth.signup",
        payload={"user_id": str(user.id)},
    )
    db.commit()

    return TokenResponse(access_token=create_access_token(user.id, tenant.id))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{body.email.lower()}"
    if not login_rate_limiter.allow(rate_limit_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in a few minutes.",
        )

    user = db.execute(select(AppUser).where(AppUser.email == body.email)).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    membership = db.execute(
        select(TenantMembership).where(TenantMembership.user_id == user.id)
    ).scalars().first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No tenant membership for this user")

    record_audit_event(
        db,
        tenant_id=membership.tenant_id,
        actor_user_id=user.id,
        event_type="auth.login",
        payload={},
    )
    db.commit()

    return TokenResponse(access_token=create_access_token(user.id, membership.tenant_id))
