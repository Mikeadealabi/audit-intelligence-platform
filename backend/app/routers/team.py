import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import Principal, get_current_principal, require_admin
from app.models import AppUser, TenantInvite, TenantMembership
from app.schemas import InviteCreateRequest, InviteCreateResponse, InviteOut, TenantMemberOut
from app.services.audit import record_audit_event

router = APIRouter(prefix="/team", tags=["team"])


def _invite_status(invite: TenantInvite) -> str:
    if invite.revoked_at is not None:
        return "revoked"
    if invite.accepted_at is not None:
        return "accepted"
    if invite.expires_at < datetime.now(UTC).replace(tzinfo=None):
        return "expired"
    return "pending"


@router.post("/invites", response_model=InviteCreateResponse, status_code=status.HTTP_201_CREATED)
def create_invite(
    body: InviteCreateRequest,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> InviteCreateResponse:
    existing = db.execute(select(AppUser).where(AppUser.email == body.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists")

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(hours=settings.invite_expires_hours)

    invite = TenantInvite(
        tenant_id=principal.tenant_id,
        email=body.email,
        role=body.role,
        token_hash=token_hash,
        invited_by=principal.user_id,
        expires_at=expires_at,
    )
    db.add(invite)
    db.flush()

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        event_type="team.invite_created",
        payload={"invite_id": str(invite.id), "email": invite.email, "role": invite.role},
    )
    db.commit()

    invite_url = f"{settings.frontend_base_url}/accept-invite?token={token}"
    return InviteCreateResponse(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        token=token,
        invite_url=invite_url,
        expires_at=invite.expires_at,
    )


@router.get("/invites", response_model=list[InviteOut])
def list_invites(
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[InviteOut]:
    invites = db.execute(
        select(TenantInvite).where(TenantInvite.tenant_id == principal.tenant_id).order_by(TenantInvite.created_at.desc())
    ).scalars()
    return [
        InviteOut(
            id=i.id,
            email=i.email,
            role=i.role,
            status=_invite_status(i),
            created_at=i.created_at,
            expires_at=i.expires_at,
            invited_by=i.invited_by,
            accepted_at=i.accepted_at,
        )
        for i in invites
    ]


@router.post("/invites/{invite_id}/revoke", response_model=InviteOut)
def revoke_invite(
    invite_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> InviteOut:
    invite = db.execute(
        select(TenantInvite).where(TenantInvite.id == invite_id, TenantInvite.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.accepted_at is not None or invite.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invite is already {_invite_status(invite)}; cannot revoke it",
        )

    invite.revoked_at = datetime.now(UTC)
    invite.revoked_by = principal.user_id

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        event_type="team.invite_revoked",
        payload={"invite_id": str(invite.id), "email": invite.email},
    )
    db.commit()

    return InviteOut(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        status=_invite_status(invite),
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        invited_by=invite.invited_by,
        accepted_at=invite.accepted_at,
    )


@router.get("/members", response_model=list[TenantMemberOut])
def list_members(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[TenantMemberOut]:
    rows = db.execute(
        select(TenantMembership, AppUser.email)
        .join(AppUser, AppUser.id == TenantMembership.user_id)
        .where(TenantMembership.tenant_id == principal.tenant_id)
        .order_by(TenantMembership.created_at)
    ).all()
    return [
        TenantMemberOut(id=m.id, user_id=m.user_id, email=email, role=m.role, created_at=m.created_at)
        for m, email in rows
    ]


@router.post("/members/{membership_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_member(
    membership_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    membership = db.execute(
        select(TenantMembership).where(
            TenantMembership.id == membership_id, TenantMembership.tenant_id == principal.tenant_id
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")

    if membership.role == "admin":
        admin_count = db.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == principal.tenant_id, TenantMembership.role == "admin"
            )
        ).scalars().all()
        if len(admin_count) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Cannot remove the only admin on this tenant"
            )

    removed_user_id = membership.user_id
    removed_email = db.execute(select(AppUser.email).where(AppUser.id == removed_user_id)).scalar_one()

    # Recorded before the delete — get_current_principal re-checks membership on
    # every request, so this takes effect immediately for the removed user with
    # no token-blacklist needed.
    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        event_type="team.member_removed",
        payload={"removed_user_id": str(removed_user_id), "removed_email": removed_email, "role": membership.role},
    )
    db.delete(membership)
    db.commit()
