import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import ControlRun, DatasetVersion
from app.routers.engagements import get_engagement_or_404
from app.schemas import ControlRunOut, RunControlRequest
from app.services.control_execution import InvalidControlParameters, UnknownControlCode, execute_control_run

router = APIRouter(prefix="/engagements/{engagement_id}/control-runs", tags=["controls"])


@router.post("", response_model=ControlRunOut, status_code=status.HTTP_201_CREATED)
def run_control(
    engagement_id: uuid.UUID,
    body: RunControlRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ControlRun:
    engagement = get_engagement_or_404(db, principal, engagement_id)

    dataset_version = db.execute(
        select(DatasetVersion).where(
            DatasetVersion.id == body.dataset_version_id,
            DatasetVersion.tenant_id == principal.tenant_id,
            DatasetVersion.engagement_id == engagement.id,
        )
    ).scalar_one_or_none()
    if dataset_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found")

    try:
        control_run = execute_control_run(
            db,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            engagement=engagement,
            dataset_version=dataset_version,
            control_code=body.control_code,
            parameters=body.parameters,
            triggered_by="manual",
        )
    except UnknownControlCode as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except InvalidControlParameters as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    return control_run


@router.get("/{control_run_id}", response_model=ControlRunOut)
def get_control_run(
    engagement_id: uuid.UUID,
    control_run_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ControlRun:
    engagement = get_engagement_or_404(db, principal, engagement_id)
    control_run = db.execute(
        select(ControlRun).where(
            ControlRun.id == control_run_id,
            ControlRun.tenant_id == principal.tenant_id,
            ControlRun.engagement_id == engagement.id,
        )
    ).scalar_one_or_none()
    if control_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control run not found")
    return control_run
