# Threat Model

## Status

Covers auth, tenancy, CSV upload/import, deterministic controls, findings, audit log,
report export, and Claude-assisted investigation (Phase 5, disabled unless
`ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL_ID` are configured — see
`docs/claude-tool-contract.md`).

## Assets

- Client financial/transaction data (uploaded files + parsed records) — highest
  sensitivity; may include personal data under NDPA/NDPR.
- Tenant/engagement/finding metadata — reveals who is auditing whom.
- Credentials (password hashes, JWT secret).
- Audit log integrity — must be trustworthy for an audit platform to be credible.

## Actors / trust boundaries

- **Unauthenticated internet client** → API: zero trust, all input validated.
- **Authenticated user of Tenant A** → data belonging to Tenant B: must be
  impossible, not just hidden in the UI.
- **Uploaded file content** → parser / DB / (future) LLM: untrusted at every hop. A
  cell value is data, never a column name, a SQL fragment, a shell argument, or (once
  Phase 5 exists) an instruction to a model.
- **Reviewer** → audit log: can write new events, cannot edit or delete prior ones.

## Key threats and current status

| # | Threat | Status |
|---|---|---|
| T1 | Cross-tenant data access via guessable/sequential IDs (IDOR) | Mitigated: UUID primary keys + tenant filter baked into every query; tested in `test_tenant_isolation.py` |
| T2 | CSV content used to inject formulas/macros if later opened in Excel, or to break the parser (huge files, malformed quoting, encoding tricks, zip bombs for a future XLSX path) | Partially mitigated: row/column/size caps enforced before parsing; XLSX not implemented yet so macro/formula risk for XLSX is **not yet applicable, but also not yet solved** — flagged as a blocker before XLSX support ships |
| T3 | Password/credential compromise | Mitigated: bcrypt hashing, short-lived JWT, plus a sliding-window rate limit on `/auth/login` (10 attempts / 5 min per IP+email — see `app/services/rate_limit.py`). **Gap**: the limiter is in-process memory, so it resets on restart and doesn't coordinate across multiple server replicas — fine for this single-process dev slice, not for a scaled deployment |
| T4 | Audit log tampering | Mitigated at two layers: insert-only at the ORM layer (no update/delete endpoint exists) **and** DB-enforced — a Postgres trigger (`app/db_triggers.py`, migration `f2a72435b50d`) rejects any `UPDATE`/`DELETE` on `audit_event` outright, tested in `test_audit_immutability.py` |
| T5 | Sensitive data in logs | Mitigated for this slice: request logging excludes request/response bodies; no raw file content or full records are logged; LLM tool-call audit events store only redacted summaries, never full record payloads. Needs re-verification every time a new endpoint is added |
| T6 | Prompt injection via uploaded file content reaching Claude | Mitigated structurally, not red-teamed: tool results travel as `tool_result` content blocks (never concatenated into the system prompt), and the system prompt explicitly tells the model that tool output is untrusted data that cannot change its tools/policy/access — see `docs/claude-tool-contract.md`. **Gap**: no adversarial prompt-injection eval has been run against the real model yet (requires a configured API key) |
| T7 | A malicious upload containing malware (not CSV-parser abuse, an actual payload file) | **Not implemented.** No antivirus/malware-scanning integration exists. This is a known, explicitly-flagged gap — do not treat uploads as scanned |
| T8 | Privilege escalation (a normal member acting as an engagement reviewer/admin) | Mitigated for the two roles that exist (`member`, `admin`) via a role check in `deps.py`; needs expansion as more roles are added |
| T9 | Denial of service via oversized or pathological uploads | Mitigated: hard row-count and byte-size caps, rejected before parsing begins |

## Known gaps (do not claim these exist)

- Rate limiting exists only on `/auth/login`, in-process memory only — every other
  endpoint is unprotected, and the login limiter itself won't scale past one process.
- No malware scanning.
- No CSRF protection middleware (API is bearer-token JSON, not cookie-session based,
  which removes most CSRF risk for this slice, but this has not been reviewed against
  the eventual frontend auth cookie approach if that changes).
- No secrets manager integration — `.env`/environment variables only.
- No adversarial prompt-injection red-team eval against the real Anthropic API
  (structural defenses are in place and unit-tested — see T6 above).
