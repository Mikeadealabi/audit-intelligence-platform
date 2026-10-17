# Reconciliation

## Status

Basic, working implementation: a second, independently-sourced data source can be
uploaded and versioned the same way transaction data is, and matched against a
committed `dataset_version` by **exact match only**. There is no fuzzy/tolerance
matching (date windows, amount-within-fee-tolerance, partial-payment splitting)
yet, and no real gateway/ERP connector of any kind — every "source" here is a
CSV file a human uploads, with a free-text label the firm chooses, never a live
feed. See `DECISIONS.md` for why this scope was chosen (the user explicitly
deferred the fuzzy-matching business rules pending a conversation with an
accountant, and ruled out building any real connector for now).

## What problem this solves

Pillar 2 of this platform's brief ("the reconciliation nightmare") is matching an
internal ledger against an external record of the same transactions — a bank
statement, a payment gateway export — to find what doesn't line up: payments
recorded but never received, receipts with no matching ledger entry, duplicates,
timing differences. This is the first slice of that: it can ingest the second
source and tell you, with full traceability, what matched and what didn't.

## Data model

- `external_record_batch` / `external_record` — the external-record mirror of
  `dataset_version` / `transaction_record`: immutable, hashed, versioned per
  engagement (its own `version_number` sequence, independent of
  `dataset_version.version_number`, since a firm may re-upload a corrected bank
  statement without re-uploading the ledger side, or vice versa). Uploaded and
  committed through the existing `import_run`/`source_file` tables, reusing the
  same immutability/hash-verification machinery as the transaction-record import
  flow. `source_label` (e.g. "GTBank NGN statement — Jan 2026") is a free-text
  caller-supplied label — it is not, and must never be presented as, a connector
  identity.
- `reconciliation_run` — one execution of matching a `dataset_version` against
  an `external_record_batch`. Carries `method` (only `"exact_match"` exists
  today) and a `parameters` JSON column that is empty today but exists
  specifically so a future tolerance-based method can be added **without a
  schema change** — see "The fuzzy-matching skeleton" below.
- `reconciliation_match` — one row per outcome: a matched pair (both
  `transaction_record_id` and `external_record_id` set) or a one-sided unmatched
  record (exactly one set). `match_status` is `matched` / `unmatched_transaction`
  / `unmatched_external`. `match_basis` always explains *why* — see below — so a
  reviewer is never left guessing.

See `docs/data-dictionary.md` for full column listings.

## Required / optional fields on the external side

| Field | Required? | Meaning |
|---|---|---|
| `reference` | required | The identifier matched against `transaction_record.invoice_reference` |
| `currency` | required | |
| `amount` | required | |
| `transaction_date` | required | Parsed and stored, but **not** part of the match key (see below) |
| `counterparty_name` | optional | Free text; not used in matching, shown for reviewer context only |

## The exact-match algorithm

A transaction and an external record are matched if and only if their
`(currency, reference, amount)` key — `currency` upper-cased, `reference`
lower-cased and trimmed, `amount` compared as exact `Decimal` — is **unique on
both sides**. Concretely, for every key present in either population:

- Exactly one transaction and exactly one external record share the key → a
  matched pair, `match_basis = "exact:amount+currency+reference"`.
- The key exists on both sides but not as a clean 1:1 (e.g. two transactions
  legitimately share a reference, or an external statement has two lines with
  the same reference/amount) → **every** record sharing that key on both sides
  is left unmatched, `match_basis = "ambiguous_duplicate_key"`. This control
  deliberately never guesses which one pairs with which — see `DECISIONS.md`.
- The key exists only on the transaction side → `match_basis =
  "no_matching_external_record"`.
- The key exists only on the external side → `match_basis =
  "no_matching_transaction_record"`.
- A record missing `reference`/`currency`/`amount` outright can't form a key at
  all → `match_basis = "missing_required_field"` (in practice unreachable
  through the normal upload pipeline, since these are required fields at parse
  time on both sides — kept as a defensive fallback, not dead-letter silence).

`transaction_date` is deliberately **not** part of the match key: a payment's
settlement date on a bank statement routinely differs from its ledger date by a
few days, and that gap is exactly the kind of business-rule judgment (how many
days is normal?) this platform should not guess at — see "The fuzzy-matching
skeleton."

Every transaction and every external record in the run ends up in exactly one
`reconciliation_match` row — matched or unmatched — so the full picture is
always visible, never a partial result.

## The fuzzy-matching skeleton

`reconciliation_run.method` and `.parameters` exist today specifically so a
second, tolerance-based method (e.g. "match within N days and within a currency
fee-tolerance amount," or handling a single payment split across several
invoices) can be added later **without a schema migration** — it would be a new
branch in `app/services/reconciliation.py::execute_reconciliation`, validated
`parameters`, and a new `match_basis` value, nothing more. Calling the endpoint
with any `method` other than `"exact_match"` today raises
`UnsupportedReconciliationMethod`, surfaced as a 400 — it never silently falls
back to exact match or guesses at a default tolerance. This was deliberately
left unimplemented pending the firm's own accountant input on what "close
enough" should mean (date window, fee allowance, partial-payment handling) —
exactly the kind of policy judgment this platform refuses to invent on its own,
consistent with every other "no safe default" control in `docs/control-library.md`.

## API

- `POST /engagements/{id}/external-imports/preview` / `.../{import_run_id}/commit`
  — upload and commit the external side, mirroring
  `POST /engagements/{id}/imports/preview` / `.../commit` for the transaction
  side.
- `GET /engagements/{id}/external-imports/batches` — list committed batches for
  this engagement (to pick one to reconcile against).
- `POST /engagements/{id}/reconciliation-runs` — body: `dataset_version_id`,
  `external_record_batch_id`, optional `method` (default `"exact_match"`),
  optional `parameters` (unused today).
- `GET /engagements/{id}/reconciliation-runs/{id}` — run summary (matched /
  unmatched counts).
- `GET /engagements/{id}/reconciliation-runs/{id}/matches` — every outcome row,
  optionally filtered by `match_status`, with the matched/referenced
  `transaction_record`/`external_record` resolved inline.

## Assumptions / limitations

- Single-currency comparison per key, same limitation as every amount-comparing
  control in `docs/control-library.md` — no FX conversion is performed anywhere.
- No partial-payment or many-to-one/one-to-many matching (e.g. one bank credit
  covering three invoices) — that is exactly the kind of business rule deferred
  to the fuzzy-matching skeleton above.
- Reconciliation is triggered on demand, not automatically on commit — unlike
  controls, which can auto-run on every dataset commit, a reconciliation run
  needs the user to have *also* committed a matching external batch, so there is
  no single natural trigger point. The user explicitly picks both sides and runs
  it.
