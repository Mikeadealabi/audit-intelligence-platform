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

## TLS stance

This app never terminates TLS itself — that's a reverse-proxy/load-balancer/platform
job, not something `uvicorn`/FastAPI should do. Two common ways to get it: a managed
hosting platform's built-in TLS, or a self-managed reverse proxy (nginx/Caddy) with
Let's Encrypt in front of this app. Local dev deliberately runs over plain HTTP
(`http://localhost:8020`) and that's fine for dev — just never expose this app
directly to the public internet without TLS termination in front of it.

Once TLS termination is confirmed to be in place, set `ENABLE_HSTS=true`
(`backend/app/config.py`'s `enable_hsts`) to make the app emit a
`Strict-Transport-Security` header (`app/middleware/hsts.py`) telling browsers to keep
using HTTPS for future requests. Leave it `false` until then — turning it on while
still serving plain HTTP would tell browsers to refuse to connect at all.

## Encryption-at-rest key management

Uploaded file bytes and `raw_row` content are encrypted with a Fernet key
(`FILE_ENCRYPTION_KEY`, `backend/app/services/encryption.py`). Generate a real
production key with:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
and store it in a managed secret store, never a `.env` file, in production.
**Rotating this key makes all previously-written ciphertext (files + `raw_row`)
permanently unreadable** — there is no key-versioning in this slice
(`cryptography.fernet.MultiFernet` would solve that but is deliberately not built
here; see `DECISIONS.md`). If a key must change, treat it the same as losing that
data: plan for it, don't do it casually.

This is app-level encryption, compensating specifically for the local filesystem
storage adapter having none of its own. It is not a substitute for infra-level
encryption (e.g. an encrypted disk/EBS volume, or Postgres-level encryption) of the
whole database — defense in depth, not either/or.

## Production (not built)

Before any production deployment: secrets out of `.env` files and into a managed
secret store, object storage adapter swapped from local filesystem to a private
S3-compatible bucket (keeping the same app-level encryption, or relying on the
bucket's own server-side encryption instead), a real backup schedule (see
`docs/backup-restore.md`), and the full `docs/privacy-and-compliance-checklist.md`
resolved.
