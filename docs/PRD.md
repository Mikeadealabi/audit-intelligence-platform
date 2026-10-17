# PRD — Audit Intelligence Platform (working name)

## Problem

Finance and audit teams at Nigerian banks, fintechs, distributors, retailers and
pharmacies review transactions and stock movements largely by hand or in spreadsheets.
Leakage and fraud (duplicate payments, split transactions, round-number/off-hours
transfers, vendor-detail changes, ghost stock, self-approval) surface late or never.

## Who this is for (v1)

Nigerian audit/accounting firms and internal audit teams who already export
transaction/ledger data as CSV/XLSX from their ERP, core banking, or POS system and
want a repeatable, evidence-backed first pass before a human reviews exceptions.

## What v1 is

1. A firm creates tenant workspaces and engagements.
2. An authorised user uploads a CSV export, maps columns to a canonical schema, and
   commits it as an immutable, hashed dataset version.
3. Deterministic, versioned controls run against that dataset version and produce
   findings with evidence references (never a bare score or verdict).
4. A human reviewer records a disposition (confirmed / false positive / needs more
   evidence) with rationale. Every transition is audited.
5. (Later phase) A reviewer can request a Claude-assisted investigation that explains
   evidence and proposes next steps through allow-listed, read-only tools — it never
   closes a finding or takes an irreversible action itself.

## What v1 explicitly is not

- Not a general ledger, ERP, or accounting system of record.
- Not a fraud-proof system — findings are "candidates requiring review," never proven
  fraud, and are labelled as such everywhere in the UI, API, and exports.
- Not NDPA/NDPR, CBN, or FIRS compliant by virtue of existing — see
  `docs/privacy-and-compliance-checklist.md`. No certification or legal-compliance claim
  is made anywhere in this repo.
- Not yet connected to any live ERP/core-banking API — CSV/XLSX upload only.

## v1 success criteria (this vertical slice)

- A user can go from CSV upload to a reviewed finding end-to-end, with every step
  traceable back to source rows, dataset version, and control version.
- A user from Tenant A cannot read, list, or infer the existence of Tenant B's
  engagements, datasets, or findings through any API response, error message, or
  object storage path — enforced in the service layer and covered by tests.
- Money is never compared or summed using binary floats.
- No step in the pipeline silently swallows a parse/validation error — it is either a
  per-row validation error the user sees before committing, or a hard rejection.

## Nigerian context baked in (not yet enforced as business rules)

- Currency default: NGN. Amount fields are currency-aware (multi-currency supported at
  the schema level since many firms reconcile NGN against USD/GBP invoices).
- `PolicyVersion` and tax-rate fields (VAT 7.5%, WHT, PAYE bands) are modelled as
  **configurable data**, not hard-coded constants, and are explicitly flagged in
  `README.md` and `.env.example` as "verify with a current Nigerian tax/compliance
  professional before relying on this for a real filing or audit opinion."
- Reference fields accommodate NIBSS/NIP-style transfer references as free-text —
  no NIBSS integration exists.
