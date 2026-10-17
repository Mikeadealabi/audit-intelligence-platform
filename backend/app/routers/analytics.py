import uuid
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import ControlDefinition, ControlRun, ControlVersion, DatasetVersion, Finding, TransactionRecord
from app.routers.engagements import get_engagement_or_404
from app.schemas import EngagementAnalytics, FindingsByControlOut, SupplierRiskOut, SupplierSummaryOut

router = APIRouter(prefix="/engagements/{engagement_id}/analytics", tags=["analytics"])

_MISSING_SUPPLIER = "(missing supplier name)"
_MISSING_CURRENCY = "(missing currency)"

_SEVERITIES = ["high", "medium", "low"]
_STATUSES = ["open", "confirmed", "false_positive", "needs_more_evidence"]

# Weights a composite risk score by severity — a triage aid, never a verdict. A
# supplier hit by three distinct controls scores higher than one hit many times
# by the same control, which is the point: breadth of independent signals matters
# more than volume of one signal.
_SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}


@router.get("", response_model=EngagementAnalytics)
def get_engagement_analytics(
    engagement_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> EngagementAnalytics:
    """Server-side aggregation, not raw-record export — datasets can run to tens
    of thousands of rows (see MAX_ROWS_PER_IMPORT), so this groups in SQL rather
    than shipping records to the client for aggregation there."""
    engagement = get_engagement_or_404(db, principal, engagement_id)

    findings = list(
        db.execute(
            select(Finding).where(
                Finding.tenant_id == principal.tenant_id,
                Finding.engagement_id == engagement.id,
            )
        ).scalars()
    )

    findings_by_severity = {s: 0 for s in _SEVERITIES}
    findings_by_status = {s: 0 for s in _STATUSES}
    for f in findings:
        findings_by_severity[f.severity] = findings_by_severity.get(f.severity, 0) + 1
        findings_by_status[f.status] = findings_by_status.get(f.status, 0) + 1

    control_runs = list(
        db.execute(
            select(ControlRun).where(
                ControlRun.tenant_id == principal.tenant_id,
                ControlRun.engagement_id == engagement.id,
            )
        ).scalars()
    )
    control_run_by_id = {cr.id: cr for cr in control_runs}
    control_versions = {
        cv.id: cv
        for cv in db.execute(
            select(ControlVersion).where(ControlVersion.id.in_({cr.control_version_id for cr in control_runs}))
        ).scalars()
    }
    control_definitions = {
        cd.id: cd
        for cd in db.execute(
            select(ControlDefinition).where(
                ControlDefinition.id.in_({cv.control_definition_id for cv in control_versions.values()})
            )
        ).scalars()
    }

    finding_counts_by_control: dict[str, int] = {}
    control_names: dict[str, str] = {}
    for f in findings:
        control_run = control_run_by_id.get(f.control_run_id)
        control_version = control_versions.get(control_run.control_version_id) if control_run else None
        control_definition = control_definitions.get(control_version.control_definition_id) if control_version else None
        code = control_definition.code if control_definition else "unknown"
        control_names[code] = control_definition.name if control_definition else "Unknown control"
        finding_counts_by_control[code] = finding_counts_by_control.get(code, 0) + 1

    findings_by_control = [
        FindingsByControlOut(control_code=code, control_name=control_names[code], finding_count=count)
        for code, count in sorted(finding_counts_by_control.items(), key=lambda kv: kv[1], reverse=True)
    ]

    latest_dataset_version = db.execute(
        select(DatasetVersion)
        .where(DatasetVersion.tenant_id == principal.tenant_id, DatasetVersion.engagement_id == engagement.id)
        .order_by(DatasetVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()

    supplier_summary: list[SupplierSummaryOut] = []
    supplier_risk_scores: list[SupplierRiskOut] = []
    if latest_dataset_version is not None:
        supplier_summary = _build_supplier_summary(
            db,
            tenant_id=principal.tenant_id,
            dataset_version_id=latest_dataset_version.id,
            findings=findings,
            control_run_by_id=control_run_by_id,
            latest_dataset_version_id=latest_dataset_version.id,
        )
        supplier_risk_scores = _build_supplier_risk_scores(
            db,
            tenant_id=principal.tenant_id,
            findings=findings,
            control_run_by_id=control_run_by_id,
            control_versions=control_versions,
            control_definitions=control_definitions,
            latest_dataset_version_id=latest_dataset_version.id,
        )

    return EngagementAnalytics(
        dataset_version_id=latest_dataset_version.id if latest_dataset_version else None,
        dataset_version_number=latest_dataset_version.version_number if latest_dataset_version else None,
        findings_by_severity=findings_by_severity,
        findings_by_status=findings_by_status,
        findings_by_control=findings_by_control,
        supplier_summary=supplier_summary,
        supplier_risk_scores=supplier_risk_scores,
    )


def _build_supplier_risk_scores(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    findings: list[Finding],
    control_run_by_id: dict[uuid.UUID, ControlRun],
    control_versions: dict[uuid.UUID, ControlVersion],
    control_definitions: dict[uuid.UUID, ControlDefinition],
    latest_dataset_version_id: uuid.UUID,
) -> list[SupplierRiskOut]:
    """A composite, explainable triage score per supplier: the sum, over every
    *distinct* control that flagged this supplier, of that control's
    highest-severity finding weight. Rewards being flagged by several different
    controls over being flagged many times by the same one — a supplier hit once
    each by duplicate-invoice, ghost-vendor, and tax-variance checks is a stronger
    signal than the same supplier hit ten times by round-number alone. This is a
    triage aid to help a reviewer decide where to look first, never a verdict —
    see docs/control-library.md."""
    relevant = [
        f
        for f in findings
        if (cr := control_run_by_id.get(f.control_run_id)) is not None and cr.dataset_version_id == latest_dataset_version_id
    ]
    if not relevant:
        return []

    all_evidence_ids: set[uuid.UUID] = set()
    for f in relevant:
        all_evidence_ids.update(uuid.UUID(rid) for rid in f.evidence_record_ids)

    tx_supplier = {
        row.id: row.supplier_name
        for row in db.execute(
            select(TransactionRecord.id, TransactionRecord.supplier_name).where(
                TransactionRecord.tenant_id == tenant_id,
                TransactionRecord.id.in_(all_evidence_ids),
            )
        ).all()
    }

    max_severity_by_control: dict[str, dict[str, str]] = defaultdict(dict)
    finding_count: dict[str, int] = defaultdict(int)
    severity_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"high": 0, "medium": 0, "low": 0})

    for f in relevant:
        control_run = control_run_by_id[f.control_run_id]
        control_version = control_versions.get(control_run.control_version_id)
        control_definition = control_definitions.get(control_version.control_definition_id) if control_version else None
        code = control_definition.code if control_definition else "unknown"

        suppliers_touched = {
            supplier_name
            for rid in f.evidence_record_ids
            if (supplier_name := tx_supplier.get(uuid.UUID(rid))) is not None
        }
        for supplier in suppliers_touched:
            finding_count[supplier] += 1
            severity_breakdown[supplier][f.severity] += 1
            current = max_severity_by_control[supplier].get(code)
            if current is None or _SEVERITY_WEIGHT[f.severity] > _SEVERITY_WEIGHT[current]:
                max_severity_by_control[supplier][code] = f.severity

    results = [
        SupplierRiskOut(
            supplier_name=supplier,
            risk_score=sum(_SEVERITY_WEIGHT[sev] for sev in control_severities.values()),
            controls_hit=sorted(control_severities.keys()),
            total_finding_count=finding_count[supplier],
            severity_breakdown=severity_breakdown[supplier],
        )
        for supplier, control_severities in max_severity_by_control.items()
    ]
    return sorted(results, key=lambda r: r.risk_score, reverse=True)


def _build_supplier_summary(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    dataset_version_id: uuid.UUID,
    findings: list[Finding],
    control_run_by_id: dict[uuid.UUID, ControlRun],
    latest_dataset_version_id: uuid.UUID,
) -> list[SupplierSummaryOut]:
    rows = db.execute(
        select(
            TransactionRecord.supplier_name,
            TransactionRecord.currency,
            func.count().label("count"),
            func.sum(TransactionRecord.amount).label("total"),
        )
        .where(
            TransactionRecord.tenant_id == tenant_id,
            TransactionRecord.dataset_version_id == dataset_version_id,
        )
        .group_by(TransactionRecord.supplier_name, TransactionRecord.currency)
    ).all()

    by_supplier: dict[str, dict] = {}
    for supplier_name, currency, count, total in rows:
        key = supplier_name or _MISSING_SUPPLIER
        entry = by_supplier.setdefault(key, {"transaction_count": 0, "by_currency": {}, "flagged": 0})
        entry["transaction_count"] += count
        currency_key = currency or _MISSING_CURRENCY
        existing = entry["by_currency"].get(currency_key, Decimal("0"))
        entry["by_currency"][currency_key] = existing + (total or Decimal("0"))

    flagged_record_ids: set[str] = set()
    for f in findings:
        control_run = control_run_by_id.get(f.control_run_id)
        if control_run and control_run.dataset_version_id == latest_dataset_version_id:
            flagged_record_ids.update(f.evidence_record_ids)

    if flagged_record_ids:
        flagged_rows = db.execute(
            select(TransactionRecord.supplier_name, func.count())
            .where(
                TransactionRecord.tenant_id == tenant_id,
                TransactionRecord.dataset_version_id == dataset_version_id,
                TransactionRecord.id.in_([uuid.UUID(rid) for rid in flagged_record_ids]),
            )
            .group_by(TransactionRecord.supplier_name)
        ).all()
        for supplier_name, count in flagged_rows:
            key = supplier_name or _MISSING_SUPPLIER
            if key in by_supplier:
                by_supplier[key]["flagged"] = count

    return [
        SupplierSummaryOut(
            supplier_name=name,
            transaction_count=data["transaction_count"],
            total_amount_by_currency={k: str(v) for k, v in data["by_currency"].items()},
            flagged_transaction_count=data["flagged"],
        )
        for name, data in sorted(by_supplier.items(), key=lambda kv: kv[1]["transaction_count"], reverse=True)
    ]
