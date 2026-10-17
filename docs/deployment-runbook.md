# Deployment Runbook

## Status

**Nothing in this repo is deployed anywhere.** This describes local development only.
Production deployment (hosting target, TLS termination, secrets manager, object
storage provider, backup schedule) is a Phase 6 decision not yet made — do not infer a
hosting choice from anything in this file.

## Local development

Prerequisites: Docker, Node 20+, Python 3.11+.

```bash
cp .env.example .env            # fill in local-only placeholder values
docker compose up -d db         # Postgres on localhost:5460 (see docker-compose.yml)
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8020
```

```bash
cd frontend
npm install
npm run dev                     # http://localhost:3080, proxies API calls to :8020
```

## Running tests

```bash
cd backend
pytest
```

Tests require the same local Postgres as above (a disposable `audit_test` database is
created/dropped per test session by `tests/conftest.py` — it does not touch the dev
database).

## CI

`.github/workflows/ci.yml` runs backend lint (ruff), type-check (mypy), and pytest
against a Postgres service container on every push/PR. Frontend CI runs `tsc --noEmit`
and `next build`. Neither pipeline deploys anything.

## Production (not built)

Before any production deployment: TLS everywhere, secrets out of `.env` files and into
a managed secret store, object storage adapter swapped from local filesystem to a
private S3-compatible bucket, a real backup schedule (see
`docs/backup-restore.md`), and the full `docs/privacy-and-compliance-checklist.md`
resolved.
