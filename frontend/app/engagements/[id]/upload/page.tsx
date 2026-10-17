"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  apiPostForm,
  apiPost,
  getToken,
  ApiError,
  type ImportPreviewResponse,
  type CommitImportResponse,
} from "@/lib/api";
import AppShell from "@/components/AppShell";
import { AlertIcon, UploadIcon, CheckCircleIcon, ArrowRightIcon } from "@/components/icons";

const REQUIRED_FIELDS = [
  "supplier_name",
  "invoice_reference",
  "currency",
  "amount",
  "transaction_date",
] as const;

// Not required to commit a dataset version at all — only used by the
// tax_calculation_variance control, which can't check anything without them.
const OPTIONAL_FIELDS = ["tax_category", "recorded_vat_amount", "recorded_wht_amount"] as const;

const CANONICAL_FIELDS = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS] as const;

const FIELD_LABELS: Record<(typeof CANONICAL_FIELDS)[number], string> = {
  supplier_name: "Supplier name",
  invoice_reference: "Invoice reference",
  currency: "Currency",
  amount: "Amount",
  transaction_date: "Transaction date",
  tax_category: "Tax category (optional)",
  recorded_vat_amount: "Recorded VAT amount (optional)",
  recorded_wht_amount: "Recorded WHT amount (optional)",
};

// First keyword that appears in a header wins — order matters (most specific first).
const FIELD_GUESS_KEYWORDS: Record<(typeof CANONICAL_FIELDS)[number], string[]> = {
  supplier_name: ["supplier", "vendor", "payee"],
  invoice_reference: ["invoice", "inv ref", "reference", "ref"],
  currency: ["currency", "ccy"],
  amount: ["amount", "value", "total"],
  transaction_date: ["date"],
  tax_category: ["tax category", "category"],
  recorded_vat_amount: ["vat"],
  recorded_wht_amount: ["wht", "withholding"],
};

function parseCsvHeaderLine(line: string): string[] {
  // Minimal CSV split — good enough for a header row, which the real parse
  // (on preview) will validate properly. Strips a wrapping quote pair and
  // the BOM a lot of spreadsheet exports prepend.
  return line
    .replace(/^﻿/, "")
    .split(",")
    .map((h) => h.trim().replace(/^"(.*)"$/, "$1"));
}

function buildColumnMappingPayload(mapping: Record<string, string>): Record<string, string> {
  // Required fields always go through as-is (even empty — the backend will
  // reject that clearly). Optional fields are only included when the user
  // actually mapped one: sending an empty string for an unmapped optional
  // field would make the backend look for a column literally named "" and
  // fail the whole preview.
  const payload: Record<string, string> = {};
  for (const field of REQUIRED_FIELDS) payload[field] = mapping[field];
  for (const field of OPTIONAL_FIELDS) if (mapping[field]) payload[field] = mapping[field];
  return payload;
}

function guessMapping(headers: string[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const field of CANONICAL_FIELDS) {
    const keywords = FIELD_GUESS_KEYWORDS[field];
    const match = headers.find((h) => keywords.some((kw) => h.toLowerCase().includes(kw)));
    result[field] = match ?? "";
  }
  return result;
}

function StepBadge({ n, done }: { n: number; done?: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 24,
        height: 24,
        borderRadius: "50%",
        background: done ? "var(--success-bg)" : "var(--accent-100)",
        color: done ? "var(--success)" : "var(--accent-600)",
        fontSize: 12,
        fontWeight: 700,
        marginRight: 10,
        flexShrink: 0,
      }}
    >
      {done ? <CheckCircleIcon size={14} /> : n}
    </span>
  );
}

export default function UploadPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[] | null>(null);
  const [headerError, setHeaderError] = useState<string | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({
    supplier_name: "",
    invoice_reference: "",
    currency: "",
    amount: "",
    transaction_date: "",
    tax_category: "",
    recorded_vat_amount: "",
    recorded_wht_amount: "",
  });
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [commitResult, setCommitResult] = useState<CommitImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [splitThreshold, setSplitThreshold] = useState("500000.00");
  const [splitCurrency, setSplitCurrency] = useState("NGN");
  const [splitWindowDays, setSplitWindowDays] = useState("3");

  const [roundTo, setRoundTo] = useState("10000.00");
  const [roundCurrency, setRoundCurrency] = useState("NGN");

  const [vatRatePercent, setVatRatePercent] = useState("7.5");
  const [whtRatesJson, setWhtRatesJson] = useState('{\n  "services": "10",\n  "goods": "5"\n}');
  const [taxParamsError, setTaxParamsError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) router.push("/");
  }, []);

  async function handleFileChange(selected: File | null) {
    setFile(selected);
    setHeaders(null);
    setHeaderError(null);
    setPreview(null);
    setCommitResult(null);
    if (!selected) return;
    try {
      const firstChunk = await selected.slice(0, 8192).text();
      const firstLine = firstChunk.split(/\r?\n/)[0] ?? "";
      const parsedHeaders = parseCsvHeaderLine(firstLine).filter((h) => h.length > 0);
      if (parsedHeaders.length === 0) {
        setHeaderError("Could not find a header row in this file — check it's a CSV with a header line.");
        return;
      }
      setHeaders(parsedHeaders);
      setMapping(guessMapping(parsedHeaders));
    } catch {
      setHeaderError("Could not read this file's headers. You can still type column names manually below.");
    }
  }

  async function runPreview(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setBusy(true);
    setPreview(null);
    setCommitResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("column_mapping", JSON.stringify(buildColumnMappingPayload(mapping)));
      const result = await apiPostForm<ImportPreviewResponse>(`/engagements/${id}/imports/preview`, form);
      setPreview(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Preview failed.");
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!preview) return;
    setError(null);
    setBusy(true);
    try {
      const result = await apiPost<CommitImportResponse>(
        `/engagements/${id}/imports/${preview.import_run_id}/commit`,
        {}
      );
      setCommitResult(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Commit failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runControlAndGoToFindings(
    controlCode: string,
    parameters?: Record<string, string | number | Record<string, string>>
  ) {
    if (!commitResult) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost(`/engagements/${id}/control-runs`, {
        dataset_version_id: commitResult.dataset_version_id,
        control_code: controlCode,
        parameters: parameters ?? null,
      });
      router.push(`/engagements/${id}/findings`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not run control.");
      setBusy(false);
    }
  }

  async function runThresholdSplitting(e: React.FormEvent) {
    e.preventDefault();
    await runControlAndGoToFindings("threshold_splitting_candidates", {
      threshold_amount: splitThreshold,
      currency: splitCurrency,
      window_days: Number(splitWindowDays),
    });
  }

  async function runRoundNumberTransfers(e: React.FormEvent) {
    e.preventDefault();
    await runControlAndGoToFindings("round_number_transfers", {
      round_to: roundTo,
      currency: roundCurrency,
    });
  }

  async function runTaxCalculationVariance(e: React.FormEvent) {
    e.preventDefault();
    setTaxParamsError(null);
    let wht_rates_by_category: Record<string, string> = {};
    if (whtRatesJson.trim()) {
      try {
        wht_rates_by_category = JSON.parse(whtRatesJson);
      } catch {
        setTaxParamsError("WHT rates must be valid JSON, e.g. {\"services\": \"10\"}.");
        return;
      }
    }
    await runControlAndGoToFindings("tax_calculation_variance", {
      vat_rate_percent: vatRatePercent,
      wht_rates_by_category,
    });
  }

  return (
    <AppShell title="Upload transactions" eyebrow="Import" icon={<UploadIcon size={17} />}>
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", marginBottom: 6 }}>
          <StepBadge n={1} />
          <h3 style={{ marginBottom: 0 }}>Choose file and map columns</h3>
        </div>
        <p className="muted" style={{ marginLeft: 34 }}>
          CSV only in this build (XLSX isn&rsquo;t implemented yet). Pick a file and we&rsquo;ll
          read its header row and suggest a mapping — check it before previewing.
        </p>
        <form onSubmit={runPreview} style={{ marginLeft: 34, marginTop: 14 }}>
          <label htmlFor="file">CSV file</label>
          <input
            id="file"
            type="file"
            accept=".csv,text/csv"
            required
            onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
          />

          {headerError && (
            <p className="muted" style={{ color: "var(--danger)", marginTop: -6 }}>
              {headerError}
            </p>
          )}

          {file && (headers || headerError) && (
            <>
              {headers && (
                <p className="muted" style={{ marginTop: -6, marginBottom: 14 }}>
                  Detected {headers.length} column{headers.length === 1 ? "" : "s"} — matched where we could,
                  double-check the rest.
                </p>
              )}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 14px" }}>
                {REQUIRED_FIELDS.map((field) => (
                  <div key={field}>
                    <label htmlFor={field}>
                      {FIELD_LABELS[field]}{" "}
                      {!mapping[field] && <span style={{ color: "var(--danger)" }}>— not matched</span>}
                    </label>
                    {headers ? (
                      <select
                        id={field}
                        required
                        value={mapping[field]}
                        onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value }))}
                      >
                        <option value="" disabled>
                          Choose a column…
                        </option>
                        {headers.map((h) => (
                          <option key={h} value={h}>
                            {h}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={field}
                        required
                        placeholder="Exact column name"
                        value={mapping[field]}
                        onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value }))}
                      />
                    )}
                  </div>
                ))}
              </div>

              <p className="muted" style={{ marginTop: 10, marginBottom: 2, fontSize: 12.5 }}>
                Optional — only needed for the tax calculation variance control:
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 14px" }}>
                {OPTIONAL_FIELDS.map((field) => (
                  <div key={field}>
                    <label htmlFor={field}>{FIELD_LABELS[field]}</label>
                    {headers ? (
                      <select
                        id={field}
                        value={mapping[field]}
                        onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value }))}
                      >
                        <option value="">— not mapped —</option>
                        {headers.map((h) => (
                          <option key={h} value={h}>
                            {h}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={field}
                        placeholder="Exact column name (leave blank to skip)"
                        value={mapping[field]}
                        onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value }))}
                      />
                    )}
                  </div>
                ))}
              </div>
            </>
          )}

          <button className="btn primary" type="submit" disabled={busy || !file}>
            {busy && !preview ? <span className="spinner" /> : null}
            Preview file
          </button>
        </form>
      </div>

      {preview && (
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
            <StepBadge n={2} />
            <h3 style={{ marginBottom: 0 }}>Review and commit</h3>
          </div>
          <div style={{ marginLeft: 34 }}>
            <div className="pill-row" style={{ marginBottom: 14 }}>
              <span className="pill" style={{ cursor: "default" }}>{preview.total_rows} row(s) read</span>
              <span className="pill" style={{ cursor: "default", color: "var(--success)", borderColor: "#bfe3cb" }}>
                {preview.valid_row_count} valid
              </span>
              {preview.error_row_count > 0 && (
                <span className="pill" style={{ cursor: "default", color: "var(--danger)", borderColor: "#f3c1c8" }}>
                  {preview.error_row_count} with errors
                </span>
              )}
            </div>
            {preview.error_row_count > 0 && (
              <p className="muted" style={{ marginTop: -8 }}>
                Rows with errors will be excluded from the committed dataset version, not guessed at.
              </p>
            )}
            <div className="card flush" style={{ marginBottom: 16 }}>
              <table>
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Supplier</th>
                    <th>Invoice ref</th>
                    <th>Currency</th>
                    <th>Amount</th>
                    <th>Date</th>
                    <th>Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.sample_rows.map((r) => (
                    <tr key={r.row_number}>
                      <td className="mono">{r.row_number}</td>
                      <td>{r.mapped.supplier_name ?? "—"}</td>
                      <td>{r.mapped.invoice_reference ?? "—"}</td>
                      <td>{r.mapped.currency ?? "—"}</td>
                      <td className="mono">{r.mapped.amount ?? "—"}</td>
                      <td className="mono">{r.mapped.transaction_date ?? "—"}</td>
                      <td style={{ color: r.errors.length ? "var(--danger)" : undefined, fontSize: 12 }}>
                        {r.errors.join("; ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {!commitResult && (
              <button className="btn primary" onClick={commit} disabled={busy}>
                {busy ? <span className="spinner" /> : <UploadIcon size={14} />}
                Commit as dataset version
              </button>
            )}

            {commitResult && (
              <div>
                <div className="info-banner" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <CheckCircleIcon size={15} />
                  Committed as dataset version #{commitResult.version_number} ({commitResult.row_count} row(s)).
                </div>

                {commitResult.auto_run_control_results.length > 0 && (
                  <div className="info-banner" style={{ marginTop: 10 }}>
                    <strong style={{ fontSize: 13 }}>Automated controls ran on this commit:</strong>
                    <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12.5 }}>
                      {commitResult.auto_run_control_results.map((r) => (
                        <li key={r.control_code}>
                          <code>{r.control_code}</code> —{" "}
                          {r.status === "completed" ? (
                            <>completed, {r.finding_count ?? 0} finding(s)</>
                          ) : (
                            <span style={{ color: "var(--danger)" }}>skipped ({r.skip_reason})</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div style={{ display: "flex", alignItems: "center", marginTop: 20, marginBottom: 10 }}>
                  <StepBadge n={3} />
                  <h3 style={{ marginBottom: 0 }}>Run a control</h3>
                </div>

                <div style={{ marginLeft: 34, display: "flex", flexDirection: "column", gap: 14 }}>
                  <div className="card" style={{ marginBottom: 0 }}>
                    <h3 style={{ fontSize: 13.5 }}>Duplicate invoice candidates</h3>
                    <p className="muted">No configuration needed — exact match on supplier, invoice reference, currency, amount, and date.</p>
                    <button
                      className="btn secondary"
                      onClick={() => runControlAndGoToFindings("duplicate_invoice_candidates")}
                      disabled={busy}
                    >
                      Run control <ArrowRightIcon size={13} />
                    </button>
                  </div>

                  <div className="card" style={{ marginBottom: 0 }}>
                    <h3 style={{ fontSize: 13.5 }}>Threshold-splitting candidates</h3>
                    <p className="muted">
                      No built-in default — set your firm&rsquo;s approval threshold. See{" "}
                      <code>docs/control-library.md</code> for what this does and doesn&rsquo;t catch.
                    </p>
                    <form onSubmit={runThresholdSplitting}>
                      <div style={{ display: "flex", gap: 10 }}>
                        <div style={{ flex: 2 }}>
                          <label htmlFor="splitThreshold">Approval threshold</label>
                          <input id="splitThreshold" required value={splitThreshold} onChange={(e) => setSplitThreshold(e.target.value)} />
                        </div>
                        <div style={{ flex: 1 }}>
                          <label htmlFor="splitCurrency">Currency</label>
                          <input id="splitCurrency" required value={splitCurrency} onChange={(e) => setSplitCurrency(e.target.value)} />
                        </div>
                        <div style={{ flex: 1 }}>
                          <label htmlFor="splitWindowDays">Window (days)</label>
                          <input
                            id="splitWindowDays"
                            type="number"
                            min={1}
                            required
                            value={splitWindowDays}
                            onChange={(e) => setSplitWindowDays(e.target.value)}
                          />
                        </div>
                      </div>
                      <button className="btn secondary" type="submit" disabled={busy}>
                        Run control <ArrowRightIcon size={13} />
                      </button>
                    </form>
                  </div>

                  <div className="card" style={{ marginBottom: 0 }}>
                    <h3 style={{ fontSize: 13.5 }}>New vendor candidates (ghost-vendor check)</h3>
                    <p className="muted">
                      No configuration needed — flags transactions to a supplier with no prior
                      history elsewhere in this engagement. A candidate for verifying the vendor
                      is real, not evidence that it isn&rsquo;t.
                    </p>
                    <button
                      className="btn secondary"
                      onClick={() => runControlAndGoToFindings("new_vendor_candidates")}
                      disabled={busy}
                    >
                      Run control <ArrowRightIcon size={13} />
                    </button>
                  </div>

                  <div className="card" style={{ marginBottom: 0 }}>
                    <h3 style={{ fontSize: 13.5 }}>Round-number transfers</h3>
                    <p className="muted">
                      No built-in default — set what counts as &ldquo;suspiciously round&rdquo; for
                      this firm. A low-confidence screening signal, not evidence on its own.
                    </p>
                    <form onSubmit={runRoundNumberTransfers}>
                      <div style={{ display: "flex", gap: 10 }}>
                        <div style={{ flex: 2 }}>
                          <label htmlFor="roundTo">Round unit</label>
                          <input id="roundTo" required value={roundTo} onChange={(e) => setRoundTo(e.target.value)} />
                        </div>
                        <div style={{ flex: 1 }}>
                          <label htmlFor="roundCurrency">Currency</label>
                          <input
                            id="roundCurrency"
                            required
                            value={roundCurrency}
                            onChange={(e) => setRoundCurrency(e.target.value)}
                          />
                        </div>
                      </div>
                      <button className="btn secondary" type="submit" disabled={busy}>
                        Run control <ArrowRightIcon size={13} />
                      </button>
                    </form>
                  </div>

                  <div className="card" style={{ marginBottom: 0 }}>
                    <h3 style={{ fontSize: 13.5 }}>Benford&rsquo;s Law digit analysis</h3>
                    <p className="muted">
                      No configuration needed — tests whether transaction amounts&rsquo; leading-digit
                      distribution deviates from Benford&rsquo;s Law, a classic forensic-accounting
                      screen. Needs at least 100 eligible transactions to run at all; fewer than
                      that is reported as inconclusive, not &ldquo;clean.&rdquo;
                    </p>
                    <button
                      className="btn secondary"
                      onClick={() => runControlAndGoToFindings("benford_digit_analysis")}
                      disabled={busy}
                    >
                      Run control <ArrowRightIcon size={13} />
                    </button>
                  </div>

                  <div className="card" style={{ marginBottom: 0 }}>
                    <h3 style={{ fontSize: 13.5 }}>Tax calculation variance (VAT/WHT)</h3>
                    <p className="muted">
                      No built-in rate — this platform doesn&rsquo;t assume current tax law.
                      Computes expected VAT/WHT at the rate(s) you supply and compares to any
                      recorded tax amount in the data; never asserts compliance. Needs the
                      optional tax columns mapped in Step 1 to check anything.
                    </p>
                    <form onSubmit={runTaxCalculationVariance}>
                      <div style={{ marginBottom: 10 }}>
                        <label htmlFor="vatRatePercent">VAT rate (%)</label>
                        <input
                          id="vatRatePercent"
                          required
                          value={vatRatePercent}
                          onChange={(e) => setVatRatePercent(e.target.value)}
                          style={{ maxWidth: 160 }}
                        />
                      </div>
                      <div>
                        <label htmlFor="whtRatesJson">WHT rates by category (JSON, optional)</label>
                        <textarea
                          id="whtRatesJson"
                          rows={3}
                          style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
                          value={whtRatesJson}
                          onChange={(e) => setWhtRatesJson(e.target.value)}
                        />
                      </div>
                      {taxParamsError && (
                        <p style={{ color: "var(--danger)", fontSize: 12, marginTop: -4 }}>{taxParamsError}</p>
                      )}
                      <button className="btn secondary" type="submit" disabled={busy}>
                        Run control <ArrowRightIcon size={13} />
                      </button>
                    </form>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </AppShell>
  );
}
