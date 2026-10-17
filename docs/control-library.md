# Control Library

## Status

Six controls implemented: `duplicate_invoice_candidates`, `threshold_splitting_candidates`,
`new_vendor_candidates`, `round_number_transfers`, `tax_calculation_variance`, and
`benford_digit_analysis`. Everything else in the brief's candidate list (approval-policy
exceptions, PO/invoice/receipt mismatch, supplier bank-detail change, missing supporting
documents) requires data this slice doesn't have yet (policy tables, PO data, change
history, document checklists) and is **not implemented** — do not run them, they
don't exist. Every control here runs *within* a single `dataset_version` — none of
them compare against a second, independently-sourced dataset. Multi-source
reconciliation (matching a bank/gateway statement against an internal ledger) now
has a separate, basic implementation — exact-match only, no fuzzy/tolerance
matching yet — see `docs/reconciliation.md`. It is not a "control" in this
registry; it has its own data model, service, and router.

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

## Running a control automatically on every dataset commit

A control can be configured, per engagement, to run automatically every time a new
`dataset_version` is committed — see `app/services/control_automation.py`,
`app/models.py::ControlConfiguration`, and `PUT/GET
.../control-configurations`. This is additive to, not a replacement for, the
manual `POST .../control-runs` endpoint: the same `execute_control_run` function
(`app/services/control_execution.py`) backs both paths, so a control behaves
identically either way and every run (manual or automatic) is still one
`ControlRun` row with one `control.run_completed` audit event.

If a configured control's saved `parameters` are missing or invalid for that
control (e.g. `threshold_splitting_candidates` enabled with no
`threshold_amount`), the commit **still succeeds** — that one control is skipped
and a `control.autorun_skipped` audit event is recorded with the reason. Failing
an entire import commit because one auto-run control is misconfigured would be
strictly worse than silently running one fewer control; see `DECISIONS.md`.

## Supplier risk score

`GET /engagements/{id}/analytics` returns `supplier_risk_scores`: a composite,
explainable score per supplier computed from the findings already on record for
the latest `dataset_version` — no new judgment is introduced, it only aggregates
existing findings differently. For each supplier, for every *distinct* control
that produced at least one finding touching that supplier, take that control's
highest-severity finding for the supplier (`high` = 3, `medium` = 2, `low` = 1)
and sum across controls. A supplier flagged once each by three different controls
scores higher than one flagged ten times by the same control — the point is to
reward *breadth* of independent signals over *volume* of one signal, which is a
much stronger basis for "look here first" than either a raw finding count or a
single control's output alone. A supplier with zero findings does not appear in
the list at all (never a zero-score entry). **This is a triage aid, not a
verdict** — the same "candidate for review, never proof" rule that applies to
every individual control applies doubly to a number that aggregates several of
them. See `app/routers/analytics.py::_build_supplier_risk_scores` and
`DECISIONS.md`.

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

---

## `new_vendor_candidates` — v1 (ghost-vendor check)

**Code**: `backend/app/services/controls/new_vendor_candidates.py`
**Control definition code**: `new_vendor_candidates`
**Control version**: 1

### What it flags

Transactions to a supplier with **no prior transaction history anywhere else in
this engagement** — a candidate for verifying the vendor is real and legitimately
onboarded (business registration, banking details, prior relationship), addressing
the brief's "ghost vendor" fraud pattern. It is **not** evidence that a vendor is
fictitious: it only knows what this platform has previously ingested for this
engagement, nothing about the outside world.

### Parameters (optional — this control has a safe default)

Unlike `threshold_splitting_candidates`, whether a supplier is new is a plain fact
about the data, not a policy choice, so this control runs with no parameters at
all by default (every first-seen-supplier transaction is flagged, severity `low`).
An optional narrowing pair lets a firm restrict this to large first-time payments
only:

| Parameter | Type | Meaning |
|---|---|---|
| `min_amount` | decimal string/number | Only flag a new vendor's transaction if its amount is at least this |
| `currency` | string | Which currency `min_amount` is denominated in |

Both must be supplied together or neither — supplying one without the other is a
400. When both are supplied, matching findings are severity `medium` instead of
`low` (more targeted, so weighted higher).

### Cross-dataset-version history

This is the only control that needs visibility beyond the single dataset version
it's checking. The caller (`app/services/control_execution.py`) queries every
`transaction_record.supplier_name` from **earlier** `dataset_version`s of the same
engagement (ordered by `version_number`, not wall-clock time — immune to two
commits landing in the same instant) and passes that set in as
`history_supplier_names`, plus a `has_prior_history` flag.

### Behaviour on an engagement's first-ever dataset version

If there is no prior dataset version at all (`has_prior_history=False`), the
control is a documented no-op: every supplier would be "new" by definition, which
would flag 100% of transactions and tell a reviewer nothing. All records are
counted as skipped, zero findings — this is deliberate, not a bug.

### Assumptions / limitations

- Exact supplier-name match only (case/whitespace-insensitive), same limitation as
  the other controls — a supplier onboarded once under a slightly different name
  spelling will be flagged again as "new."
- Only ever compares within one engagement. A supplier that's well-established
  with this firm on a *different* engagement is still "new" here.
- Says nothing about whether the vendor is legitimate — only that this is its
  first appearance in this engagement's records.

### Test cases

See `backend/tests/test_new_vendor_control.py`: first dataset version is a no-op,
a supplier not in history is flagged, a supplier in history (case/whitespace
variations) is not, missing supplier name is skipped, `min_amount` requires
`currency` to be paired with it, the amount/currency filter excludes small
payments and other currencies correctly.

---

## `round_number_transfers` — v1

**Code**: `backend/app/services/controls/round_number_transfers.py`
**Control definition code**: `round_number_transfers`
**Control version**: 1

### What it flags

Individual transactions whose amount is an **exact multiple** of a configured
unit (e.g. every multiple of ₦10,000). Round-number amounts are a classic
fabricated/estimated-figure signal in fraud literature, but they are also entirely
normal for legitimate rent, fixed fees, or round contract values — this control is
deliberately low-confidence (`severity = "low"` on every finding) and is meant to
be combined with other review steps, never read as evidence on its own.

### Required parameters (no safe default)

| Parameter | Type | Meaning |
|---|---|---|
| `round_to` | decimal string/number | The unit a "round" amount must be an exact multiple of, e.g. `"10000.00"` |
| `currency` | string | Which currency `round_to` is denominated in |

What counts as "suspiciously round" depends on this firm's normal transaction
sizes — the same reasoning as `threshold_splitting_candidates`'s required
parameters, see `DECISIONS.md`. Missing either parameter is a 400.

### Assumptions / limitations

- Single-currency per run, same limitation as `threshold_splitting_candidates`.
- Flags **every** matching transaction individually — does not group or
  deduplicate, and is expected to produce many findings on datasets with
  naturally round fixed costs (rent, salaries). This is a known, documented
  tradeoff of a per-transaction screening signal, not a bug.
- Zero and negative amounts are never flagged (not meaningful "round transfers").

### Test cases

See `backend/tests/test_round_number_control.py`: missing/invalid parameters
reject, an exact multiple is flagged, a non-multiple isn't, wrong currency and
missing amount are skipped (not miscounted as clean), zero amount isn't flagged.

---

## `tax_calculation_variance` — v1 (VAT/WHT)

**Code**: `backend/app/services/controls/tax_calculation_variance.py`
**Control definition code**: `tax_calculation_variance`
**Control version**: 1

### What it flags

Computes the VAT (and, where a row's `tax_category` matches a configured rate,
WHT) expected on each transaction at the **caller-supplied rate(s)**, and compares
it to any recorded tax amount on the same row — `transaction_record.tax_category`
/ `recorded_vat_amount` / `recorded_wht_amount`, three **optional** fields only
populated when the source file maps a column to them (see
`docs/data-dictionary.md`). Two kinds of finding:

- **No recorded amount to check against** (`severity = "low"`): a coverage-gap
  signal, not a confirmed miscalculation.
- **Recorded amount differs from expected by more than the configured tolerance**
  (`severity = "high"`): a candidate for a tax/finance professional to review.

**This control never asserts a transaction is or isn't tax-compliant.** It
computes a variance against a rate the caller supplied, full stop — consistent
with this platform's non-negotiable rule (established from the project's first
session) against claiming legal/compliance status anywhere in code or docs. See
`DECISIONS.md`.

### Required / optional parameters

| Parameter | Required? | Type | Meaning |
|---|---|---|---|
| `vat_rate_percent` | **Required, no default** | decimal string/number | The VAT rate the caller believes currently applies, e.g. `"7.5"` |
| `vat_exempt_categories` | optional | list of strings | `tax_category` values to exclude from the VAT check entirely |
| `wht_rates_by_category` | optional | object, category → rate percent | e.g. `{"services": "10", "goods": "5"}`. A row whose category isn't a key here has no WHT check performed — not guessed at |
| `tolerance_amount` | optional, default `"0.01"` | decimal string/number | Rounding allowance. This *does* have a safe default — it's a precision fact matching this platform's `NUMERIC(18,2)` everywhere else, not a policy choice |

`vat_rate_percent` has no built-in default and never will: Nigerian VAT/WHT rates
are statutory facts that change over time, and this platform is not a qualified
authority on current tax law. Omitting it is a 400 with a message saying exactly
that.

### Assumptions / limitations

- A flat VAT rate per run — no per-category VAT rate variation beyond the
  exempt-category list (real VAT regimes sometimes have zero-rated vs
  standard-rated categories beyond a simple exempt/not-exempt split; this is a
  known simplification).
- Rows whose `tax_category` doesn't match any key in `wht_rates_by_category`
  silently skip the WHT check for that row (not an error, not a finding) — the
  caller must enumerate every category it wants checked.
- Depends entirely on the source file actually carrying `tax_category` /
  `recorded_vat_amount` / `recorded_wht_amount` columns. On a dataset that never
  mapped these, every eligible row will get a "no recorded VAT amount" low-severity
  finding — this is an honest reflection of a real coverage gap, not a bug, but it
  means this control should only be enabled once those columns are actually
  populated, or the findings list will be dominated by coverage-gap noise.

### Test cases

See `backend/tests/test_tax_calculation_control.py`: missing `vat_rate_percent`
rejects, VAT within tolerance produces no finding, a real mismatch is flagged
high, a missing recorded VAT is flagged low, an exempt category skips the VAT
check, a recognized WHT category is checked and an unrecognized one is silently
not, missing amount/currency is skipped.

---

## `benford_digit_analysis` — v1

**Code**: `backend/app/services/controls/benford_digit_analysis.py`
**Control definition code**: `benford_digit_analysis`
**Control version**: 1

### What it flags

A classic forensic-accounting screen: tests whether the leading-digit distribution
of transaction amounts in this `dataset_version` deviates significantly from
Benford's Law — the mathematical fact that in most naturally-occurring numeric
data, the first digit is 1 far more often than 9 (specifically, digit *d* occurs
with probability log₁₀(1 + 1/*d*)). Fabricated, estimated, or manipulated figures
often fail to reproduce this pattern. A single run produces **at most one
finding** for the whole dataset — this control is not grouped by supplier (see
Assumptions below) — with `evidence_record_ids` set to every eligible transaction
that went into the test, so a reviewer can see exactly what was analyzed.

### Parameters (optional — this control has safe statistical defaults)

| Parameter | Default | Meaning |
|---|---|---|
| `min_sample_size` | `100` | Minimum eligible transactions required before the test runs at all; below this, the run is a documented no-op (see below). Must be ≥ 30 — a first-digit chi-square test is not considered meaningful below that by any commonly cited convention. |
| `significance_level` | `"0.05"` | Confidence threshold for the chi-square goodness-of-fit test. Must be one of `"0.10"`, `"0.05"`, `"0.01"` (critical values for 8 degrees of freedom: 13.362 / 15.507 / 20.090). |

Unlike `threshold_splitting_candidates` or `round_number_transfers`, both
parameters are **safe to default** — they are statistical conventions (a minimum
sample size, a standard confidence level), not business/policy judgments. They
are still overridable because `min_sample_size`/`significance_level` conventions
vary across forensic-accounting literature (some sources recommend a minimum of
300, not 100, for high confidence) — this platform picks a commonly used
practical default, not a universal standard.

### Algorithm

1. For each record with a non-null, non-zero `amount`, extract the leading
   (first nonzero) decimal digit of `abs(amount)`, exact on the `Decimal` value
   (no float conversion). Records with a null or zero amount are skipped — zero
   has no leading digit.
2. If fewer than `min_sample_size` eligible records exist, the whole run is a
   no-op: **zero findings, all records skipped** — this is "couldn't test," not
   "no anomaly found," same convention as `new_vendor_candidates`'s first-version
   no-op.
3. Otherwise compute a chi-square goodness-of-fit statistic comparing the
   observed digit-frequency distribution to Benford's expected distribution (8
   degrees of freedom for digits 1-9). If the statistic exceeds the critical
   value for the configured `significance_level`, one finding is produced,
   `severity = "medium"`, listing the full per-digit observed-vs-expected
   breakdown in its summary.

### Assumptions / limitations

- **Runs over the whole dataset_version, not per-supplier.** Benford's Law
  assumptions hold best over one coherent population; splitting into many small
  per-supplier sub-populations would mostly fall below any meaningful sample size
  and would overstate the test's precision at that granularity. A deviation
  concentrated in one supplier among many will still usually surface in the
  whole-dataset test if that supplier is a significant share of the population,
  but a mild deviation spread evenly across many small suppliers, none
  individually large enough to test, would not be caught. Per-supplier Benford
  testing is a documented possible future enhancement, not implemented v1.
- **A statistical deviation is a screening signal, never proof of manipulation.**
  Plenty of entirely legitimate populations deviate from Benford's Law too (prices
  clustered at fixed points, rounded fee schedules, a population dominated by one
  or two recurring contract values) — this is always `severity = "medium"`,
  never escalated to "high," and the finding text says so explicitly.
- Does not identify *which* transactions are driving the deviation beyond the
  per-digit breakdown — a reviewer narrowing this down by supplier or transaction
  type is expected to use the other controls and the supplier risk score
  (`GET /engagements/{id}/analytics`) alongside this one, not this control alone.
- `min_sample_size`/`significance_level` are documented conventions from
  first-digit-testing literature, not universal statistical law — see
  `DECISIONS.md`.

### Test cases

See `backend/tests/test_benford_control.py`: a distribution constructed to match
Benford's expected proportions produces no finding, a deliberately skewed
distribution is flagged medium with every eligible record as evidence, a
population below `min_sample_size` is a no-op (not a false "clean" result),
missing/zero amounts are skipped, invalid `min_sample_size`/`significance_level`
reject with a clear error, and a lowered `min_sample_size` allows testing a
smaller population.
