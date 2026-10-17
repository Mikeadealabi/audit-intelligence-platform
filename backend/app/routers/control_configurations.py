import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import ControlConfiguration
from app.routers.engagements import get_engagement_or_404
from app.schemas import ControlConfigurationIn, ControlConfigurationOut
from app.services.audit import record_audit_event
from app.services.control_execution import CONTROL_REGISTRY

router = APIRouter(prefix="/engagements/{engagement_id}/control-configurations", tags=["control-configurations"])


def _to_out(control_code: str, cfg: ControlConfiguration | None) -> ControlConfigurationOut:
    spec = CONTROL_REGISTRY[control_code]
    return ControlConfigurationOut(
        control_code=control_code,
        control_name=spec.name,
        description=spec.description,
        enabled=cfg.enabled if cfg else False,
        parameters=cfg.parameters if cfg else {},
        required_parameters_hint=list(spec.required_parameters_hint),
        updated_at=cfg.updated_at if cfg else None,
    )


@router.get("", response_model=list[ControlConfigurationOut])
def list_control_configurations(
    engagement_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[ControlConfigurationOut]:
    """Every control in the registry, each merged with its saved configuration for
    this engagement (or defaults — disabled, no parameters — if none has been
    saved yet). This is what drives auto-run on dataset commit; see
    app/services/control_automation.py."""
    engagement = get_engagement_or_404(db, principal, engagement_id)

    saved = {
        cfg.control_code: cfg
        for cfg in db.execute(
            select(ControlConfiguration).where(
                ControlConfiguration.tenant_id == principal.tenant_id,
                ControlConfiguration.engagement_id == engagement.id,
            )
        ).scalars()
    }

    return [_to_out(control_code, saved.get(control_code)) for control_code in CONTROL_REGISTRY]


@router.put("/{control_code}", response_model=ControlConfigurationOut)
def set_control_configuration(
    engagement_id: uuid.UUID,
    control_code: str,
    body: ControlConfigurationIn,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ControlConfigurationOut:
    engagement = get_engagement_or_404(db, principal, engagement_id)

    if control_code not in CONTROL_REGISTRY:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown control code '{control_code}'")

    cfg = db.execute(
        select(ControlConfiguration).where(
            ControlConfiguration.tenant_id == principal.tenant_id,
            ControlConfiguration.engagement_id == engagement.id,
            ControlConfiguration.control_code == control_code,
        )
    ).scalar_one_or_none()
    if cfg is None:
        cfg = ControlConfiguration(
            tenant_id=principal.tenant_id,
            engagement_id=engagement.id,
            control_code=control_code,
            updated_by=principal.user_id,
        )
        db.add(cfg)

    cfg.enabled = body.enabled
    cfg.parameters = body.parameters or {}
    cfg.updated_by = principal.user_id
    db.flush()

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="control_configuration.updated",
        payload={"control_code": control_code, "enabled": cfg.enabled, "parameters": cfg.parameters},
    )
    db.commit()

    return _to_out(control_code, cfg)
