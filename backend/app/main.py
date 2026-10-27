from fastapi import FastAPI

from app.config import settings
from app.middleware.hsts import HSTSMiddleware
from app.routers import (
    activity,
    analytics,
    auth,
    control_configurations,
    controls,
    data_purge,
    engagement_plan,
    engagements,
    external_imports,
    findings,
    imports,
    investigations,
    invites,
    reconciliation,
    reports,
    team,
)

app = FastAPI(
    title="Audit Intelligence Platform API",
    description=(
        "Tenant-scoped engagements, CSV import with immutable dataset versioning, "
        "deterministic controls, findings, Claude-assisted investigation (disabled "
        "unless ANTHROPIC_API_KEY/ANTHROPIC_MODEL_ID are configured), evidence-backed "
        "report export, and audit events."
    ),
)

# Opt-in only — must stay off in local dev (plain HTTP). See docs/deployment-runbook.md.
if settings.enable_hsts:
    app.add_middleware(HSTSMiddleware)

app.include_router(auth.router)
app.include_router(team.router)
app.include_router(invites.router)
app.include_router(engagements.router)
app.include_router(engagement_plan.router)
app.include_router(data_purge.router)
app.include_router(imports.router)
app.include_router(external_imports.router)
app.include_router(reconciliation.router)
app.include_router(controls.router)
app.include_router(control_configurations.router)
app.include_router(findings.router)
app.include_router(investigations.router)
app.include_router(reports.router)
app.include_router(analytics.router)
app.include_router(activity.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
