# Data Dictionary

## Status

Reflects tables actually created by the Alembic migration in this repo
(`backend/alembic/versions/0001_initial.py`). Entities from the full target model that
are **not yet created** are listed at the bottom so this file doesn't imply more exists
than does.

## Conventions

- All primary keys are `UUID` (not sequential integers) — avoids leaking record counts
  and makes IDOR guessing infeasible.
- All money columns are `NUMERIC(18,2)` with an explicit `currency` column alongside —
  never a float, never an implicit currency.
- All tables have `created_at` (UTC). Mutable tables also have `updated_at`.
- `tenant_id` is denormalized onto every table that is reachable from a tenant, even
  where it could be derived through a join, specifically so every query can filter on
  it directly without relying on a join being written correctly.

## Tables (implemented)

### tenant
`id, name, created_at`

### app_user
`id, email (unique), password_hash, created_at`

### tenant_membership
`id, tenant_id -> tenant, user_id -> app_user, role (member|admin), created_at`
Unique on `(tenant_id, user_id)`. Previously created only at signup; as of
2026-10-27 a row can also be created by accepting a `tenant_invite`, and an admin
can remove one (`POST /team/members/{id}/revoke`) — a hard delete, not a status
flag, since `get_current_principal` already re-checks this table on every
request, so removal takes effect immediately with no extra code path needed. The
tenant's last remaining `role="admin"` row cannot be removed.

### tenant_invite
`id, tenant_id -> tenant, email, role (member|admin — the role granted on accept), token_hash (sha256, unique), invited_by -> app_user, created_at, expires_at, accepted_at (nullable), accepted_by -> app_user (nullable), revoked_at (nullable), revoked_by -> app_user (nullable)`
Lets an admin invite a new teammate into their tenant — there is no email-sending
infrastructure in this repo, so `POST /team/invites` returns a link the admin
copies and sends themselves. `token_hash` is a plain sha256 hex digest (not
bcrypt — a 256-bit random token needs an indexable exact-match lookup, not
bcrypt's slow/salted design meant for low-entropy secrets; see `DECISIONS.md`),
the plaintext token is returned exactly once, at creation. Accepting an invite
always creates a **brand-new** `app_user` — it is not a way for an existing user
to join a second tenant (see `DECISIONS.md` on why that scope choice keeps
`auth.py`'s login membership lookup safe).

### engagement
`id, tenant_id -> tenant, name, client_name, status (active|closed), created_by -> app_user, created_at, data_purged_at (nullable), data_purged_by -> app_user (nullable)`
`data_purged_at`/`data_purged_by` are set by `POST .../purge-data` (2026-10-27,
admin-only) — a soft purge that deletes raw uploaded file bytes and redacts
`raw_row` content for this engagement's `source_file`/`transaction_record`/
`external_record` rows, while leaving canonical fields, findings, dispositions,
sign-offs, and the audit trail untouched. The engagement stays active afterward —
calling the endpoint again purges anything newly un-purged (e.g. a file uploaded
after an earlier purge) rather than permanently refusing a second call.

### source_file
`id, tenant_id, engagement_id -> engagement, uploaded_by -> app_user, original_filename, storage_path, sha256_hash, byte_size, content_type, created_at, content_purged_at (nullable)`
The uploaded file is written once, hashed, and never overwritten. File bytes are
encrypted at rest with an app-level Fernet key (2026-10-27, see
`app/services/encryption.py`) before being written to storage; the SHA-256 hash is
computed on the plaintext and is an integrity check, not a confidentiality
control. `content_purged_at` is set when `POST .../purge-data` deletes this
file's bytes from storage — metadata (filename, hash, size) is kept for
provenance even after the content itself is gone.

### import_run
`id, tenant_id, engagement_id, source_file_id -> source_file, column_mapping (JSON), source_label (nullable), status (pending|previewed|committed|rejected), row_count, error_count, created_by, created_at`
`column_mapping` records exactly which source column fed which canonical field —
required to reproduce a finding later. `source_label` is only used by the
external-record (reconciliation) import flow — a free-text caller-supplied label,
never a real connector identity; null for the transaction-record import flow. See
`docs/reconciliation.md`.

### dataset_version
`id, tenant_id, engagement_id, import_run_id -> import_run (unique), version_number, source_file_sha256, mapping_snapshot (JSON), committed_by, committed_at`
Created exactly once, when an `import_run` is committed. Immutable: no update
endpoint exists for this table. `version_number` is per-engagement and monotonically
increasing.

### transaction_record
`id, tenant_id, engagement_id, dataset_version_id -> dataset_version, source_row_number, supplier_name, invoice_reference, currency, amount (NUMERIC 18,2), transaction_date, tax_category (nullable), recorded_vat_amount (NUMERIC 18,2, nullable), recorded_wht_amount (NUMERIC 18,2, nullable), raw_row (JSON), created_at`
`raw_row` keeps the original mapped values for provenance even though only a subset
is promoted to typed columns in this slice. It is stored encrypted
(`{"_encrypted": "<fernet-token>"}`, 2026-10-27, see `app/services/encryption.py`)
and is write-only — nothing in the app ever reads it back. After
`POST .../purge-data` it becomes `{"_purged": true}` instead; the typed canonical
fields below are unaffected either way. The three tax fields are **optional** —
`NULL` unless the source file's column mapping actually maps a column to them (see
`app/services/csv_parser.py::OPTIONAL_CANONICAL_FIELDS`); this platform never
computes or fills in a tax amount itself, only compares a recorded one against an
expected one in `tax_calculation_variance` (`docs/control-library.md`).

### external_record_batch
`id, tenant_id, engagement_id, import_run_id -> import_run (unique), source_label, version_number, source_file_sha256, mapping_snapshot (JSON), committed_by, committed_at`
The reconciliation subsystem's second, independently-sourced data source — the
external-record mirror of `dataset_version`. `version_number` is its own
per-engagement sequence, independent of `dataset_version.version_number`. See
`docs/reconciliation.md`.

### external_record
`id, tenant_id, engagement_id, external_record_batch_id -> external_record_batch, source_row_number, counterparty_name (nullable), reference (nullable), currency (nullable), amount (NUMERIC 18,2, nullable), transaction_date (nullable), raw_row (JSON), created_at`
The external-record mirror of `transaction_record`. `reference` is matched
against `transaction_record.invoice_reference` during reconciliation. `raw_row`
is encrypted and write-only, and becomes `{"_purged": true}` after a purge, same
as `transaction_record.raw_row` above.

### reconciliation_run
`id, tenant_id, engagement_id, dataset_version_id -> dataset_version, external_record_batch_id -> external_record_batch, method, status, started_at, finished_at, run_by, matched_count, unmatched_transaction_count, unmatched_external_count, parameters (JSON)`
One execution of matching a `dataset_version` against an `external_record_batch`.
`method` and `parameters` exist so a future tolerance-based/fuzzy method can be
added without a schema change — only `"exact_match"` has an implementation
today. See `docs/reconciliation.md`.

### reconciliation_match
`id, tenant_id, engagement_id, reconciliation_run_id -> reconciliation_run, transaction_record_id (nullable), external_record_id (nullable), match_status (matched|unmatched_transaction|unmatched_external), match_basis (nullable), created_at`
One row per outcome: a matched pair (both FKs set) or a one-sided unmatched
record (exactly one FK set). `match_basis` always explains why — see
`docs/reconciliation.md`.

### control_definition
`id, code (unique, e.g. "duplicate_invoice_candidates"), name, description, created_at`

### control_version
`id, control_definition_id -> control_definition, version_number, logic_doc_ref, parameters (JSON), created_at`
Unique on `(control_definition_id, version_number)`. `docs/control-library.md`
describes what each version actually does — this row is metadata, not code.

### control_run
`id, tenant_id, engagement_id, dataset_version_id -> dataset_version, control_version_id -> control_version, status (completed|failed), started_at, finished_at, run_by, finding_count, skipped_row_count, parameters (JSON)`
`skipped_row_count` is rows excluded from evaluation because a required field was
missing — tracked so "0 findings" and "couldn't evaluate most rows" are distinguishable.
`parameters` is the exact configuration the caller supplied for this specific run
(e.g. `threshold_splitting_candidates`'s `threshold_amount`/`currency`/`window_days`)
— stored per-run rather than on `control_version` so different tenants/engagements
can use different thresholds without each needing its own control version. See
`docs/control-library.md`.

### finding
`id, tenant_id, engagement_id, control_run_id -> control_run, severity (low|medium|high), status (open|confirmed|false_positive|needs_more_evidence), summary, evidence_record_ids (JSON array of transaction_record.id), sign_off_status (not_required|pending_review|signed_off|rejected), signed_off_by -> app_user (nullable), signed_off_at (nullable), disposition_recorded_by -> app_user (nullable), created_at`
`status` starts at `open` and only changes through a reviewer disposition, which is
itself an `audit_event`. `sign_off_status` is a second, additive layer on top of
`status`: every disposition resets it to `pending_review`; a second-person
`POST .../sign-off` (`finding.signed_off` / `finding.signoff_rejected` audit events)
moves it to `signed_off` or `rejected`. `disposition_recorded_by` (added
2026-10-27) records who recorded the current disposition; `record_sign_off`
rejects (409) an attempt to sign off your own disposition using this column —
**real segregation of duties**, now that a teammate/invite flow exists (see
`tenant_invite` above). `NULL` on a finding dispositioned before this column
existed, which skips the enforcement check for that finding (an honest
transitional gap, see `DECISIONS.md`).

### engagement_plan
`id, tenant_id, engagement_id (unique), materiality_amount (nullable), materiality_currency (nullable), scope_notes (nullable), risk_assessment (nullable), risk_rating (low|medium|high, nullable), updated_by -> app_user, updated_at`
Captured once per engagement, usually before fieldwork — scope, a materiality
threshold, and a free-text risk assessment. **Capture only**: no control or finding
currently reads or weighs against this (see `DECISIONS.md`, 2026-10-27) — this is
the first step toward the deferred "materiality-aware findings" idea, not that
feature itself. No row exists until the first `PUT .../plan`; a `GET` before that
returns an all-null default rather than a 404.

### investigation_run
`id, tenant_id, engagement_id, finding_id -> finding, status (pending|completed|failed), model_id, requested_by, requested_at, completed_at, result (JSON, nullable), tool_call_log (JSON array), token_usage (JSON), error_message (nullable)`
`result` is the grounded, schema-validated `InvestigationResult` (see
`docs/claude-tool-contract.md`) — null until `status = "completed"`. `tool_call_log`
is a redacted record of every tool call made (name, arguments, a safe summary, not
full record payloads). See `docs/claude-tool-contract.md` for the full contract.

### control_configuration
`id, tenant_id, engagement_id -> engagement, control_code, enabled, parameters (JSON), updated_by -> app_user, updated_at`
Unique on `(engagement_id, control_code)`. Drives auto-run-on-commit (see
`app/services/control_automation.py` and `docs/control-library.md`) — one row per
control a firm has opted into automating for a given engagement, with whatever
`parameters` that control needs stored the same way a manual `control_run.parameters`
is. Changing it is audited (`control_configuration.updated`).

### audit_event
`id, tenant_id, engagement_id (nullable), actor_user_id (nullable for system events), event_type, payload (JSON, redacted — see below), created_at`
Insert-only at the application layer (no update/delete route exists for this table)
**and at the database level** — a trigger (`backend/app/db_triggers.py`, applied by
migration `f2a72435b50d`) rejects any `UPDATE`/`DELETE` on this table outright, not
just "no route for it." `payload` must never contain a password, token, or full
`raw_row` dump — only identifiers and the specific fields relevant to the event
(e.g. a finding's new status, not every field on it).

## Entities in the target model NOT yet created

`SupplierRecord` (as its own entity — supplier is currently just a text field on
`transaction_record`), `EvidenceItem` (evidence is currently just the list of
`transaction_record.id` on a finding, not a richer entity), `CaseEvent` (case
commentary/assignment beyond a single disposition), `PolicyVersion` (needed once an
approval-policy-exception control is built — `check_approval_against_policy`
already exists as a Claude tool and always reports itself unsupported until this
table does).

`ReviewDecision` as a proper history table (one row per disposition *and* per
sign-off decision, each with its own rationale/comment column) is still not built —
the rationale/comment text for both still lives only in `audit_event.payload`, not
as a queryable column on `finding` or a dedicated table; `finding.status` and the
new `finding.sign_off_status` (2026-10-27) are still single current-value fields,
not a history. This remains a known simplification, now one step closer: the
sign-off workflow is the "review workflow needs more than one disposition per
finding" trigger this note originally anticipated, but it was implemented as two
additive status fields on `finding` rather than the richer table — revisit if a
firm needs to see the *history* of dispositions/sign-offs, not just the current one.
