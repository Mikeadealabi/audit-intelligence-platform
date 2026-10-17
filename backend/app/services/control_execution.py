from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlDefinition, ControlRun, ControlVersion, DatasetVersion, Engagement, Finding, TransactionRecord
from app.services.audit import record_audit_event
from app.services.controls import (
    benford_digit_analysis,
    duplicate_invoices,
    new_vendor_candidates,
    round_number_transfers,
    tax_calculation_variance,
    threshold_splitting,
)
from app.services.controls.base import ControlResult, InvalidControlParameters

__all__ = [
    "CONTROL_REGISTRY",
    "ControlSpec",
    "InvalidControlParameters",
    "UnknownControlCode",
    "execute_control_run",
]


class UnknownControlCode(ValueError):
    """Raised when a control_code doesn't match anything in CONTROL_REGISTRY. A
    client error (400), not a server fault."""


class ControlModule(Protocol):
    CONTROL_CODE: str
    CONTROL_VERSION: int

    def run(self, records: list, parameters: dict | None = None) -> ControlResult: ...


@dataclass(frozen=True)
class ControlSpec:
    module: ControlModule
    name: str
    description: str
    required_parameters_hint: tuple[str, ...] = ()
    needs_engagement_history: bool = False


CONTROL_REGISTRY: dict[str, ControlSpec] = {
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
        required_parameters_hint=("threshold_amount", "currency", "window_days"),
    ),
    new_vendor_candidates.CONTROL_CODE: ControlSpec(
        module=new_vendor_candidates,
        name="New vendor candidates (ghost-vendor check)",
        description=(
            "Flags transactions to a supplier with no prior transaction history "
            "elsewhere in this engagement. Optional parameters: min_amount, "
            "currency (narrows to large first-time payments only). See "
            "docs/control-library.md."
        ),
        needs_engagement_history=True,
    ),
    round_number_transfers.CONTROL_CODE: ControlSpec(
        module=round_number_transfers,
        name="Round-number transfers",
        description=(
            "Flags transactions whose amount is an exact multiple of a configured "
            "unit — a low-confidence screening signal. Requires parameters: "
            "round_to, currency. See docs/control-library.md."
        ),
        required_parameters_hint=("round_to", "currency"),
    ),
    tax_calculation_variance.CONTROL_CODE: ControlSpec(
        module=tax_calculation_variance,
        name="Tax calculation variance (VAT/WHT)",
        description=(
            "Computes expected VAT/WHT at caller-supplied rates and compares to "
            "any recorded tax amount in the source data. Requires parameter: "
            "vat_rate_percent. Never asserts compliance. See "
            "docs/control-library.md."
        ),
        required_parameters_hint=("vat_rate_percent",),
    ),
    benford_digit_analysis.CONTROL_CODE: ControlSpec(
        module=benford_digit_analysis,
        name="Benford's Law digit analysis",
        description=(
            "Tests whether the leading-digit distribution of transaction amounts "
            "in this dataset deviates significantly from Benford's Law, a classic "
            "forensic-accounting screen for fabricated or estimated figures. No "
            "required parameters — min_sample_size and significance_level have "
            "safe statistical defaults. See docs/control-library.md."
        ),
    ),
}


def _get_or_create_control_version(db: Session, control_code: str) -> ControlVersion:
    spec = CONTROL_REGISTRY[control_code]
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


def _history_supplier_names(db: Session, *, tenant_id: UUID, engagement_id: UUID, before_version_number: int) -> frozenset[str]:
    # Ordered by version_number, not committed_at — version_number is the
    # engagement's actual monotonic sequence, immune to any two commits landing
    # within the same clock tick.
    rows = db.execute(
        select(TransactionRecord.supplier_name)
        .join(DatasetVersion, DatasetVersion.id == TransactionRecord.dataset_version_id)
        .where(
            TransactionRecord.tenant_id == tenant_id,
            TransactionRecord.engagement_id == engagement_id,
            TransactionRecord.supplier_name.isnot(None),
            DatasetVersion.version_number < before_version_number,
        )
        .distinct()
    ).scalars().all()
    return frozenset(s.strip().lower() for s in rows if s)


def _has_prior_dataset_version(db: Session, *, tenant_id: UUID, engagement_id: UUID, before_version_number: int) -> bool:
    return (
        db.execute(
            select(DatasetVersion.id)
            .where(
                DatasetVersion.tenant_id == tenant_id,
                DatasetVersion.engagement_id == engagement_id,
                DatasetVersion.version_number < before_version_number,
            )
            .limit(1)
        ).first()
        is not None
    )


def execute_control_run(
    db: Session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    engagement: Engagement,
    dataset_version: DatasetVersion,
    control_code: str,
    parameters: dict | None,
    triggered_by: str = "manual",
) -> ControlRun:
    """Runs one control against one dataset version and persists the ControlRun +
    its Findings + an audit event. Shared by the manual control-run endpoint
    (routers/controls.py) and the dataset-commit auto-run path
    (app/services/control_automation.py) so there is exactly one place this logic
    lives. Flushes but does not commit — the caller owns the transaction boundary.

    Raises UnknownControlCode or InvalidControlParameters (never caught here) —
    callers decide whether that should fail the whole request (manual run) or be
    recorded as a skip (auto-run)."""
    spec = CONTROL_REGISTRY.get(control_code)
    if spec is None:
        raise UnknownControlCode(f"Unknown control code '{control_code}'")

    # This session is autoflush=False (app/db.py) — a caller that just added
    # TransactionRecord rows (e.g. the dataset-commit auto-run path, which calls
    # this before its own commit) would otherwise have those rows invisible to
    # the query below. Flush unconditionally so this function is correct
    # regardless of what the caller has pending.
    db.flush()

    control_version = _get_or_create_control_version(db, control_code)

    records = list(
        db.execute(
            select(TransactionRecord).where(
                TransactionRecord.tenant_id == tenant_id,
                TransactionRecord.dataset_version_id == dataset_version.id,
            )
        ).scalars()
    )

    extra_kwargs: dict = {}
    if spec.needs_engagement_history:
        extra_kwargs["history_supplier_names"] = _history_supplier_names(
            db, tenant_id=tenant_id, engagement_id=engagement.id, before_version_number=dataset_version.version_number
        )
        extra_kwargs["has_prior_history"] = _has_prior_dataset_version(
            db, tenant_id=tenant_id, engagement_id=engagement.id, before_version_number=dataset_version.version_number
        )

    result: ControlResult = spec.module.run(records, parameters, **extra_kwargs)

    control_run = ControlRun(
        tenant_id=tenant_id,
        engagement_id=engagement.id,
        dataset_version_id=dataset_version.id,
        control_version_id=control_version.id,
        status="completed",
        finished_at=datetime.now(UTC),
        run_by=user_id,
        finding_count=len(result.findings),
        skipped_row_count=result.skipped_row_count,
        parameters=parameters or {},
    )
    db.add(control_run)
    db.flush()

    for f in result.findings:
        db.add(
            Finding(
                tenant_id=tenant_id,
                engagement_id=engagement.id,
                control_run_id=control_run.id,
                severity=f.severity,
                summary=f.summary,
                evidence_record_ids=[str(rid) for rid in f.evidence_record_ids],
            )
        )

    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        engagement_id=engagement.id,
        event_type="control.run_completed",
        payload={
            "control_run_id": str(control_run.id),
            "control_code": control_code,
            "control_version": control_version.version_number,
            "dataset_version_id": str(dataset_version.id),
            "finding_count": control_run.finding_count,
            "skipped_row_count": control_run.skipped_row_count,
            "parameters": control_run.parameters,
            "triggered_by": triggered_by,
        },
    )

    return control_run
