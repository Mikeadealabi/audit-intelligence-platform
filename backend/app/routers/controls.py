import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import ControlDefinition, ControlRun, ControlVersion, DatasetVersion, Finding, TransactionRecord
from app.routers.engagements import get_engagement_or_404
from app.schemas import ControlRunOut, RunControlRequest
from app.services.audit import record_audit_event
from app.services.controls import duplicate_invoices, threshold_splitting
from app.services.controls.base import ControlResult, InvalidControlParameters

router = APIRouter(prefix="/engagements/{engagement_id}/control-runs", tags=["controls"])


class ControlModule(Protocol):
    CONTROL_CODE: str
    CONTROL_VERSION: int

    def run(self, records: list, parameters: dict | None = None) -> ControlResult: ...


@dataclass(frozen=True)
class ControlSpec:
    module: ControlModule
    name: str
    description: str


_CONTROL_REGISTRY: dict[str, ControlSpec] = {
    duplicate_invoices.CONTROL_CODE: ControlSpec(
        module=duplicate_invoices,
        name="Duplicate invoice candidates",
        description=(
            "Flags records sharing supplier, invoice reference, currency, amount, "
            "and date. See docs/control-library.md for assumptions and limitations."
        ),
    ),
    threshold_splitting.CONTROL_CODE: ControlSpec(
        module=threshold_splitting,
        name="Threshold-splitting candidates",
        description=(
            "Flags clusters of sub-threshold transactions to the same supplier, "
            "close together in time, that together exceed a configured approval "
            "threshold. Requires parameters: threshold_amount, currency, "
            "window_days. See docs/control-library.md."
        ),
    ),
}


def _get_or_create_control_version(db: Session, control_code: str) -> ControlVersion:
    spec = _CONTROL_REGISTRY.get(control_code)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown control code '{control_code}'")

    module = spec.module
    definition = db.execute(
        select(ControlDefinition).where(ControlDefinition.code == control_code)
    ).scalar_one_or_none()
    if definition is None:
        definition = ControlDefinition(code=control_code, name=spec.name, description=spec.description)
        db.add(definition)
        db.flush()

    version = db.execute(
        select(ControlVersion).where(
            ControlVersion.control_definition_id == definition.id,
            ControlVersion.version_number == module.CONTROL_VERSION,
        )
    ).scalar_one_or_none()
    if version is None:
        version = ControlVersion(
            control_definition_id=definition.id,
            version_number=module.CONTROL_VERSION,
            logic_doc_ref="docs/control-library.md#" + control_code.replace("_", "-"),
        )
        db.add(version)
        db.flush()

    return version


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

    control_version = _get_or_create_control_version(db, body.control_code)
    spec = _CONTROL_REGISTRY[body.control_code]

    records = list(
        db.execute(
            select(TransactionRecord).where(
                TransactionRecord.tenant_id == principal.tenant_id,
                TransactionRecord.dataset_version_id == dataset_version.id,
            )
        ).scalars()
    )

    try:
        result = spec.module.run(records, body.parameters)
    except InvalidControlParameters as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    control_run = ControlRun(
        tenant_id=principal.tenant_id,
        engagement_id=engagement.id,
        dataset_version_id=dataset_version.id,
        control_version_id=control_version.id,
        status="completed",
        finished_at=datetime.now(UTC),
        run_by=principal.user_id,
        finding_count=len(result.findings),
        skipped_row_count=result.skipped_row_count,
        parameters=body.parameters or {},
    )
    db.add(control_run)
    db.flush()

    for f in result.findings:
        db.add(
            Finding(
                tenant_id=principal.tenant_id,
                engagement_id=engagement.id,
                control_run_id=control_run.id,
                severity=f.severity,
                summary=f.summary,
                evidence_record_ids=[str(rid) for rid in f.evidence_record_ids],
            )
        )

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="control.run_completed",
        payload={
            "control_run_id": str(control_run.id),
            "control_code": body.control_code,
            "control_version": control_version.version_number,
            "dataset_version_id": str(dataset_version.id),
            "finding_count": control_run.finding_count,
            "skipped_row_count": control_run.skipped_row_count,
            "parameters": control_run.parameters,
        },
    )
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
