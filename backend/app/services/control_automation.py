from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlConfiguration, DatasetVersion, Engagement
from app.services.audit import record_audit_event
from app.services.control_execution import InvalidControlParameters, UnknownControlCode, execute_control_run


@dataclass(frozen=True)
class AutoRunResult:
    control_code: str
    status: str  # "completed" | "skipped"
    finding_count: int | None = None
    skip_reason: str | None = None


def auto_run_configured_controls(
    db: Session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    engagement: Engagement,
    dataset_version: DatasetVersion,
) -> list[AutoRunResult]:
    """Runs every enabled ControlConfiguration for this engagement against the
    just-committed dataset_version, as part of the same commit. Never raises: a
    control whose saved parameters are missing/invalid, or whose code has since
    been removed, is skipped and recorded as a 'control.autorun_skipped' audit
    event instead — failing the entire import commit over one misconfigured
    control would be worse than silently running one fewer control. See
    docs/control-library.md and DECISIONS.md."""
    configs = db.execute(
        select(ControlConfiguration).where(
            ControlConfiguration.tenant_id == tenant_id,
            ControlConfiguration.engagement_id == engagement.id,
            ControlConfiguration.enabled.is_(True),
        )
    ).scalars().all()

    results: list[AutoRunResult] = []
    for cfg in configs:
        try:
            control_run = execute_control_run(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                engagement=engagement,
                dataset_version=dataset_version,
                control_code=cfg.control_code,
                parameters=cfg.parameters,
                triggered_by="dataset_commit",
            )
        except (InvalidControlParameters, UnknownControlCode) as exc:
            record_audit_event(
                db,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                engagement_id=engagement.id,
                event_type="control.autorun_skipped",
                payload={
                    "control_code": cfg.control_code,
                    "dataset_version_id": str(dataset_version.id),
                    "reason": str(exc),
                },
            )
            results.append(AutoRunResult(control_code=cfg.control_code, status="skipped", skip_reason=str(exc)))
            continue

        results.append(
            AutoRunResult(control_code=cfg.control_code, status="completed", finding_count=control_run.finding_count)
        )

    return results
