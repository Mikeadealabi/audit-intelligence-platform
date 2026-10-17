import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import (
    AuditEvent,
    ControlDefinition,
    ControlRun,
    ControlVersion,
    DatasetVersion,
    Finding,
    InvestigationRun,
)
from app.routers.engagements import get_engagement_or_404
from app.schemas import (
    EngagementReport,
    ReportControlRunOut,
    ReportDatasetVersionOut,
    ReportDispositionOut,
    ReportFindingOut,
    ReportInvestigationOut,
)
from app.services.audit import record_audit_event

router = APIRouter(prefix="/engagements/{engagement_id}/reports", tags=["reports"])

_STANDARD_LIMITATIONS = [
    "This report reflects deterministic control results and, where present, "
    "Claude-assisted investigation notes. It is not an audit opinion and does not "
    "constitute legal, tax, or regulatory compliance certification of any kind.",
    "Every finding is a candidate for human review, not a confirmed exception, "
    "unless a reviewer disposition below says otherwise.",
    "AI-generated investigation content, where present, is explicitly labeled and "
    "is a starting point for a human reviewer, not a conclusion — it does not "
    "replace professional audit judgement.",
    "Controls run in this report only cover the data and control types documented "
    "in docs/control-library.md. Absence of a finding means the implemented "
    "controls found nothing, not that no issue exists.",
]


@router.get("", response_model=EngagementReport)
def get_engagement_report(
    engagement_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> EngagementReport:
    engagement = get_engagement_or_404(db, principal, engagement_id)

    dataset_versions = list(
        db.execute(
            select(DatasetVersion)
            .where(DatasetVersion.tenant_id == principal.tenant_id, DatasetVersion.engagement_id == engagement.id)
            .order_by(DatasetVersion.version_number)
        ).scalars()
    )
    dataset_version_numbers = {dv.id: dv.version_number for dv in dataset_versions}

    control_runs = list(
        db.execute(
            select(ControlRun)
            .where(ControlRun.tenant_id == principal.tenant_id, ControlRun.engagement_id == engagement.id)
            .order_by(ControlRun.started_at)
        ).scalars()
    )
    control_version_ids = {cr.control_version_id for cr in control_runs}
    control_versions = {
        cv.id: cv
        for cv in db.execute(select(ControlVersion).where(ControlVersion.id.in_(control_version_ids))).scalars()
    }
    control_definitions = {
        cd.id: cd
        for cd in db.execute(
            select(ControlDefinition).where(
                ControlDefinition.id.in_({cv.control_definition_id for cv in control_versions.values()})
            )
        ).scalars()
    }

    findings = list(
        db.execute(
            select(Finding)
            .where(Finding.tenant_id == principal.tenant_id, Finding.engagement_id == engagement.id)
            .order_by(Finding.created_at)
        ).scalars()
    )

    dispositions = _latest_dispositions_by_finding(db, principal.tenant_id, engagement.id)
    investigations = _latest_investigations_by_finding(db, principal.tenant_id, engagement.id)
    control_run_by_id = {cr.id: cr for cr in control_runs}

    report_findings = []
    for finding in findings:
        control_run = control_run_by_id.get(finding.control_run_id)
        control_version = control_versions.get(control_run.control_version_id) if control_run else None
        control_definition = control_definitions.get(control_version.control_definition_id) if control_version else None
        report_findings.append(
            ReportFindingOut(
                id=finding.id,
                severity=finding.severity,
                status=finding.status,
                summary=finding.summary,
                evidence_record_ids=[uuid.UUID(rid) for rid in finding.evidence_record_ids],
                created_at=finding.created_at,
                control_code=control_definition.code if control_definition else "unknown",
                control_version=control_version.version_number if control_version else 0,
                dataset_version_number=dataset_version_numbers.get(control_run.dataset_version_id, 0)
                if control_run
                else 0,
                disposition=dispositions.get(str(finding.id)),
                latest_investigation=investigations.get(str(finding.id)),
            )
        )

    report_control_runs = [
        ReportControlRunOut(
            id=cr.id,
            control_code=control_definitions[control_versions[cr.control_version_id].control_definition_id].code,
            control_name=control_definitions[control_versions[cr.control_version_id].control_definition_id].name,
            control_version=control_versions[cr.control_version_id].version_number,
            parameters=cr.parameters,
            dataset_version_number=dataset_version_numbers.get(cr.dataset_version_id, 0),
            finding_count=cr.finding_count,
            skipped_row_count=cr.skipped_row_count,
            started_at=cr.started_at,
            finished_at=cr.finished_at,
        )
        for cr in control_runs
    ]

    report_dataset_versions = [
        ReportDatasetVersionOut(
            id=dv.id,
            version_number=dv.version_number,
            source_file_sha256=dv.source_file_sha256,
            mapping_snapshot=dv.mapping_snapshot,
            committed_at=dv.committed_at,
        )
        for dv in dataset_versions
    ]

    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        engagement_id=engagement.id,
        event_type="report.exported",
        payload={
            "dataset_version_count": len(dataset_versions),
            "control_run_count": len(control_runs),
            "finding_count": len(findings),
        },
    )
    db.commit()

    return EngagementReport(
        engagement_id=engagement.id,
        engagement_name=engagement.name,
        client_name=engagement.client_name,
        generated_at=datetime.now(UTC),
        dataset_versions=report_dataset_versions,
        control_runs=report_control_runs,
        findings=report_findings,
        limitations=_STANDARD_LIMITATIONS,
    )


def _latest_dispositions_by_finding(
    db: Session, tenant_id: uuid.UUID, engagement_id: uuid.UUID
) -> dict[str, ReportDispositionOut]:
    events = list(
        db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.engagement_id == engagement_id,
                AuditEvent.event_type == "finding.disposition_recorded",
            )
            .order_by(AuditEvent.created_at)
        ).scalars()
    )
    latest: dict[str, ReportDispositionOut] = {}
    for event in events:
        finding_id = event.payload.get("finding_id")
        if not finding_id:
            continue
        latest[finding_id] = ReportDispositionOut(
            status=event.payload.get("new_status", "unknown"),
            rationale=event.payload.get("rationale", ""),
            recorded_at=event.created_at,
            recorded_by=event.actor_user_id,
        )
    return latest


def _latest_investigations_by_finding(
    db: Session, tenant_id: uuid.UUID, engagement_id: uuid.UUID
) -> dict[str, ReportInvestigationOut]:
    runs = list(
        db.execute(
            select(InvestigationRun)
            .where(
                InvestigationRun.tenant_id == tenant_id,
                InvestigationRun.engagement_id == engagement_id,
                InvestigationRun.status == "completed",
            )
            .order_by(InvestigationRun.completed_at)
        ).scalars()
    )
    latest: dict[str, ReportInvestigationOut] = {}
    for run in runs:
        latest[str(run.finding_id)] = ReportInvestigationOut(
            id=run.id, model_id=run.model_id, completed_at=run.completed_at, result=run.result
        )
    return latest
