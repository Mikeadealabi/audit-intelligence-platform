# ADR-0001: Initial stack

## Status
Accepted (2026-10-17)

## Context
No existing repository/stack to inherit. The brief proposes Next.js+TS frontend,
FastAPI backend, PostgreSQL, a CSV/XLSX import pipeline, and a server-side Claude
adapter, and says to use these defaults "unless a clear repository constraint
justifies another option." There is no such constraint — this is a new repo.

## Decision
- Frontend: Next.js (App Router) + TypeScript.
- Backend: FastAPI + SQLAlchemy 2.0, **sync** engine (psycopg3 driver), Alembic for
  migrations.
- DB: PostgreSQL 16, `NUMERIC(18,2)` for all money columns, never `float`.
- Auth: first-party email+password (`bcrypt` directly — `passlib` was tried first and
  dropped, see `DECISIONS.md`) + JWT (`python-jose`),
  explicitly flagged as a pre-production item to reconsider in favour of managed
  OIDC — see `DECISIONS.md`.
- File storage: adapter interface, local filesystem implementation for dev; no S3
  adapter built yet.
- Background jobs: none yet — synchronous, row-capped control runs. A queue is a
  deliberately deferred decision, not an oversight (see `DECISIONS.md`).
- LLM: no call exists yet; `docs/claude-tool-contract.md` is the spec Phase 5 must
  satisfy.

## Why sync SQLAlchemy over async
FastAPI is often paired with an async stack, but for this first slice — where the
hardest correctness risk is tenant-scoped query construction and exact decimal
arithmetic, not throughput — a sync engine keeps the query-building code and its
tests simpler to read and verify. Nothing in the API contract (JSON over HTTP) commits
us to sync forever; switching the DB layer to async later doesn't change any router
signature in a way clients would notice.

## Consequences
- Control runs block the request thread for the duration of the run; the row cap
  (`MAX_ROWS_PER_IMPORT`) exists specifically to keep that bounded until a queue is
  introduced.
- Revisit this ADR (new ADR, don't edit this one) if/when imports need to exceed a
  single request lifetime.
