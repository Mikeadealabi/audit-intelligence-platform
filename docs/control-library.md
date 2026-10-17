# Control Library

## Status

Two controls implemented: `duplicate_invoice_candidates` and
`threshold_splitting_candidates`. Everything else in the brief's candidate list
(approval-policy exceptions, PO/invoice/receipt mismatch, supplier bank-detail change,
missing supporting documents) requires data this slice doesn't have yet (policy
tables, PO data, change history, document checklists) and is **not implemented** — do
not run them, they don't exist.

## How a control's parameters work

A `ControlVersion` (e.g. `duplicate_invoice_candidates` v1) is a fixed piece of
*logic* — its code never changes without a new version number. Some controls also
need a *configuration value* that's a business/policy decision, not a code fact (an
approval threshold, a grouping window). Those are supplied by the caller on every
`POST .../control-runs` request as `parameters`, and are stored verbatim on the
resulting `ControlRun` row (`control_run.parameters`) — so any run is fully
reproducible from its own record without needing a separate `ControlVersion` per
tenant per threshold choice. A control with no configuration (duplicate-invoice
candidates) simply ignores whatever `parameters` it's given.

---

## `duplicate_invoice_candidates` — v1

**Code**: `backend/app/services/controls/duplicate_invoices.py`
**Control definition code**: `duplicate_invoice_candidates`
**Control version**: 1

### What it flags

Groups of two or more `transaction_record` rows within the same `dataset_version`
that share all of:

- `supplier_name` (case-insensitive, whitespace-trimmed exact match — no fuzzy
  matching in v1)
- `invoice_reference` (exact match, trimmed)
- `currency` (exact match)
- `amount` (exact `Decimal` equality — never float comparison)
- `transaction_date` (exact match)

Each group becomes one `Finding` with `severity = "medium"` and
`evidence_record_ids` set to every `transaction_record.id` in the group.

### Required fields

`supplier_name`, `invoice_reference`, `currency`, `amount`, `transaction_date` must
all be present and non-null on a row for that row to be eligible. Rows missing any of
these fields are **excluded from this control** and counted in the control run's
`finding_count`-adjacent skip count (logged, not silently dropped) — see
`ControlRun` — rather than guessed at.

### Assumptions / limitations

- Exact match only. A supplier name typo, a reformatted invoice reference, or a
  rounding difference of ₦0.01 will **not** be caught by v1 — that is a known
  limitation, not a bug, and is stated here so it isn't discovered the hard way later.
- A legitimate duplicate (e.g. a corrected re-issue of the same invoice with the same
  reference, which some suppliers do) will also be flagged — this is a *candidate*
  for human review, not a conclusion. The UI and API must never describe this as
  "duplicate payment confirmed."
- Does not check whether either invoice in the pair was actually *paid* — it compares
  invoice records, not payment/settlement records. "Possible duplicate payments" from
  the brief's candidate list is a **separate, not-yet-implemented** control that would
  need payment/settlement identifiers.
- Runs within a single `dataset_version` only. It does not compare across dataset
  versions or across engagements.

### Test cases

See `backend/tests/test_duplicate_invoice_control.py`:
- Exact duplicate pair → 1 finding, 2 evidence IDs.
- Three-way duplicate → 1 finding, 3 evidence IDs.
- Same supplier/date/amount but different invoice reference → no finding.
- Same everything except currency → no finding.
- Row missing `amount` → excluded, does not crash the run, does not false-positive.
- Decimal precision: `100.10` vs `100.1` stored as `NUMERIC(18,2)` → treated as equal
  (no float drift either way).

### Behaviour when data is insufficient

If a `dataset_version` has zero eligible rows (e.g. every row is missing a required
field), the control run completes with `finding_count = 0` and status `completed` —
it does not fail, and it does not report that the dataset is "clean"; the UI must show
the skip count alongside the zero-findings result so a reviewer can tell "nothing to
find" apart from "couldn't check."

---

## `threshold_splitting_candidates` — v1

**Code**: `backend/app/services/controls/threshold_splitting.py`
**Control definition code**: `threshold_splitting_candidates`
**Control version**: 1

### What it flags

Clusters of two or more sub-threshold `transaction_record` rows, to the same
supplier, close enough together in time that their combined amount reaches a
configured approval threshold — a candidate for "payments split to stay under an
approval limit," not proof of it.

### Required parameters (no safe default — see below)

| Parameter | Type | Meaning |
|---|---|---|
| `threshold_amount` | decimal string/number | The approval threshold being potentially evaded, e.g. `"500000.00"` |
| `currency` | string | Which currency `threshold_amount` is denominated in, e.g. `"NGN"` |
| `window_days` | integer ≥ 1 | How many days apart two transactions can be and still count as "the same splitting attempt" |

Calling this control without all three raises a 400 — there is deliberately no
built-in Nigerian-naira default threshold baked into the code, because an approval
limit is each firm's own policy fact, not something this platform can know or
assume. See `DECISIONS.md`.

### Algorithm

1. Exclude rows missing `supplier_name`, `currency`, `amount`, or `transaction_date`
   (counted as skipped).
2. Exclude rows whose `currency` doesn't match the parameter `currency` (also
   skipped) — amounts in a different currency cannot be summed against the
   threshold without an FX conversion this control does not perform.
3. Exclude rows whose `amount` is already ≥ `threshold_amount` — only sub-threshold
   transactions are candidates for "splitting."
4. Remaining rows are grouped by supplier (case/whitespace-insensitive, same as the
   duplicate-invoice control), sorted by date, and **chain-clustered**: a new
   cluster starts whenever the gap to the previous transaction in the (sorted)
   sequence exceeds `window_days`.
5. A cluster becomes a `Finding` (`severity = "high"`) only if it has ≥ 2 records
   *and* its amounts sum to ≥ `threshold_amount`.

### Assumptions / limitations

- **Chain clustering can span longer than `window_days` overall.** Three
  transactions 2 days apart each (day 1, day 3, day 6 with `window_days=3`) form one
  cluster spanning 5 days, because each *consecutive* gap is within the window even
  though the first and last are not. This is a deliberate, documented choice, not a
  bug — see `test_three_way_chain_within_window_clusters_transitively`.
- Exact supplier-name match only, same limitation as the duplicate-invoice control.
- Single-currency per run. A supplier split across NGN and USD transactions in the
  same window will not be caught — each currency must be checked with its own run.
- Does not know which transactions share a common requester/approver — it only has
  supplier and date in this schema. A true "same person split this" signal would
  need a requester/approver field this canonical schema doesn't carry yet.
- A flagged cluster is a **candidate for review**, never a "confirmed
  threshold-splitting" claim — multiple small, independent, legitimate payments to
  the same regular supplier within a few days of each other will also match this
  pattern.

### Test cases

See `backend/tests/test_threshold_splitting_control.py` (13 cases) and the API-level
tests in `backend/tests/test_control_run_flow.py`: missing/invalid parameters reject
with a clear error (not a silent default), a transitive three-way chain clusters
correctly, transactions outside the window don't merge, wrong-currency rows are
skipped (not miscounted as clean), and a single at-or-above-threshold transaction is
never flagged.

### Behaviour when data is insufficient

Same as `duplicate_invoice_candidates`: zero eligible rows → `finding_count = 0`,
`status = "completed"`, with the skip count visible alongside it.
