from fastapi import FastAPI

from app.routers import auth, controls, engagements, findings, imports, investigations, reports

app = FastAPI(
    title="Audit Intelligence Platform API",
    description=(
        "Tenant-scoped engagements, CSV import with immutable dataset versioning, "
        "deterministic controls, findings, Claude-assisted investigation (disabled "
        "unless ANTHROPIC_API_KEY/ANTHROPIC_MODEL_ID are configured), evidence-backed "
        "report export, and audit events."
    ),
)

app.include_router(auth.router)
app.include_router(engagements.router)
app.include_router(imports.router)
app.include_router(controls.router)
app.include_router(findings.router)
app.include_router(investigations.router)
app.include_router(reports.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
