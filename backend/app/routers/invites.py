import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppUser, Tenant, TenantInvite, TenantMembership
from app.schemas import AcceptInviteRequest, InvitePreview, TokenResponse
from app.security import create_access_token, hash_password
from app.services.audit import record_audit_event

router = APIRouter(prefix="/invites", tags=["invites"])


def _get_valid_invite(db: Session, token: str) -> TenantInvite:
    """404 for an unrecognized token, 410 Gone for one that no longer leads
    anywhere (expired/revoked/already accepted) — distinct from "never existed"
    so a stale link can tell the user why, without leaking which case it is to
    someone merely guessing tokens (both are equally unusable either way)."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    invite = db.execute(select(TenantInvite).where(TenantInvite.token_hash == token_hash)).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This invite has been revoked")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This invite has already been accepted")
    # Stored as a naive UTC datetime (same convention as every other DateTime
    # column in this app) — strip tzinfo before comparing, not a tz-aware "now".
    if invite.expires_at < datetime.now(UTC).replace(tzinfo=None):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This invite has expired")
    return invite


@router.get("/{token}", response_model=InvitePreview)
def preview_invite(token: str, db: Session = Depends(get_db)) -> InvitePreview:
    invite = _get_valid_invite(db, token)
    tenant_name = db.execute(select(Tenant.name).where(Tenant.id == invite.tenant_id)).scalar_one()
    return InvitePreview(email=invite.email, role=invite.role, tenant_name=tenant_name)


@router.post("/{token}/accept", response_model=TokenResponse)
def accept_invite(token: str, body: AcceptInviteRequest, db: Session = Depends(get_db)) -> TokenResponse:
    invite = _get_valid_invite(db, token)

    existing = db.execute(select(AppUser).where(AppUser.email == invite.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists — log in instead",
        )

    user = AppUser(email=invite.email, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()

    membership = TenantMembership(tenant_id=invite.tenant_id, user_id=user.id, role=invite.role)
    db.add(membership)

    invite.accepted_at = datetime.now(UTC)
    invite.accepted_by = user.id

    record_audit_event(
        db,
        tenant_id=invite.tenant_id,
        actor_user_id=user.id,
        event_type="team.invite_accepted",
        payload={"invite_id": str(invite.id), "user_id": str(user.id), "role": invite.role},
    )
    db.commit()

    return TokenResponse(access_token=create_access_token(user.id, invite.tenant_id))
