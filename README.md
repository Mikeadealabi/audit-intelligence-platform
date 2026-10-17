# Audit Intelligence Platform (working name)

Evidence-grounded audit intelligence and back-office compliance platform, built for
Nigerian accounting/audit firms, starting from CSV/Excel uploads. See
`docs/PRD.md` for the product framing and `DECISIONS.md` for defaults picked
autonomously while building this.

## Status: a working vertical slice, not a finished product

End to end: a firm creates an engagement → uploads a CSV → the system validates it
and previews row-level errors → committing creates an immutable, hashed dataset
version → deterministic controls (`duplicate_invoice_candidates`,
`threshold_splitting_candidates`) run against it → findings appear with evidence
linked back to source rows → a reviewer can optionally request a Claude-assisted
investigation (read-only tools, every claim grounded back to evidence actually
returned, never auto-approved) → a reviewer records a disposition → an evidence-backed
report can be exported for the whole engagement → every step is in an
database-enforced, append-only audit log. Tenant isolation is enforced at the query
layer and covered by tests (88 passing as of 2026-10-17 — `docs/test-strategy.md`).

**Not implemented**: XLSX upload, the remaining controls from the brief's candidate
list that need data this schema doesn't carry (approval-policy exceptions, PO
mismatch, supplier bank-detail change, missing-document checklist — see
`docs/control-library.md`), background job processing (control/investigation runs
are synchronous, row/turn-capped), malware scanning, managed secrets/OIDC,
observability, backup/restore, and a prompt-injection red-team eval against the real
Anthropic API (no API key is configured in this environment — see
`docs/claude-tool-contract.md`). See `docs/privacy-and-compliance-checklist.md` for
compliance gaps — **no legal/compliance/certification claim is made anywhere in this
repo.**

## Local setup

```bash
cp .env.example .env
docker compose up -d db                 # Postgres on localhost:5460
cd backend && pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8020
```

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev                              # http://localhost:3090
```

Create a workspace at `http://localhost:3090` (sign-up tab), then create an
engagement and upload a CSV with columns for supplier, invoice reference, currency,
amount, and date.

To enable Claude-assisted investigation, set `ANTHROPIC_API_KEY` and
`ANTHROPIC_MODEL_ID` in `backend/.env` — without them, investigation requests return
`503` rather than a fake result (see `docs/claude-tool-contract.md`).

## Tests

```bash
cd backend && pytest
```

Requires the same local Postgres as above; tests create/drop a disposable
`audit_test` database and never touch your dev data. See `docs/test-strategy.md`.

## Architecture, controls, security

See `docs/architecture.md`, `docs/data-dictionary.md`, `docs/control-library.md`,
`docs/threat-model.md`, `docs/claude-tool-contract.md`, and
`docs/decisions/ADR-0001-stack.md`.

## Nigerian compliance note

Tax/compliance values (VAT, WHT, PAYE) referenced in `.env.example` are
**configurable placeholders only — not enforced by any code, and not verified**.
Confirm current rates and any legal-compliance question with a qualified Nigerian
tax/compliance professional before relying on this platform for anything real. See
`docs/privacy-and-compliance-checklist.md`.
