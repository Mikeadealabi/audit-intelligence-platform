"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiGet, getToken, ApiError, type EngagementAnalytics, type SupplierSummary, type SupplierRisk } from "@/lib/api";
import AppShell from "@/components/AppShell";
import EmptyState from "@/components/EmptyState";
import { AlertIcon, BuildingIcon } from "@/components/icons";

type SortKey = "transaction_count" | "flagged_transaction_count" | "supplier_name" | "risk_score";

export default function SuppliersPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [analytics, setAnalytics] = useState<EngagementAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("transaction_count");
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    apiGet<EngagementAnalytics>(`/engagements/${id}/analytics`)
      .then(setAnalytics)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load supplier data."));
  }, [id]);

  const riskBySupplier = useMemo(() => {
    const map: Record<string, SupplierRisk> = {};
    for (const r of analytics?.supplier_risk_scores ?? []) map[r.supplier_name] = r;
    return map;
  }, [analytics]);

  const suppliers = useMemo(() => {
    const list = analytics?.supplier_summary ?? [];
    const filtered = query.trim()
      ? list.filter((s) => s.supplier_name.toLowerCase().includes(query.trim().toLowerCase()))
      : list;
    return [...filtered].sort((a, b) => {
      if (sortKey === "supplier_name") return a.supplier_name.localeCompare(b.supplier_name);
      if (sortKey === "risk_score") {
        return (riskBySupplier[b.supplier_name]?.risk_score ?? 0) - (riskBySupplier[a.supplier_name]?.risk_score ?? 0);
      }
      return (b[sortKey] as number) - (a[sortKey] as number);
    });
  }, [analytics, sortKey, query, riskBySupplier]);

  function formatAmounts(s: SupplierSummary): string {
    const entries = Object.entries(s.total_amount_by_currency);
    if (entries.length === 0) return "—";
    return entries.map(([currency, amount]) => `${currency} ${Number(amount).toLocaleString()}`).join(" · ");
  }

  return (
    <AppShell title="Suppliers" eyebrow="Risk profile" icon={<BuildingIcon size={17} />}>
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      <p className="page-lede">
        Transaction volume and flagged-transaction counts per supplier, computed from the
        latest committed dataset version. This surfaces concentration and flag patterns —
        it is not itself a finding, and a high count here is not an accusation. The risk
        score rewards being flagged by several <em>different</em> controls over being
        flagged many times by one — it is a triage aid for where to look first, never a
        verdict.
      </p>

      {!analytics && !error && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" style={{ height: 56 }} />
          ))}
        </div>
      )}

      {analytics && analytics.supplier_summary.length === 0 && (
        <div className="card">
          <EmptyState
            icon={<BuildingIcon size={22} />}
            title="No transaction data yet"
            description="Upload a file and commit a dataset version to see supplier breakdowns here."
          />
        </div>
      )}

      {analytics && analytics.supplier_summary.length > 0 && (
        <div className="card flush">
          <div
            className="card-header"
            style={{ padding: "18px 22px 10px", display: "flex", gap: 12, flexWrap: "wrap" }}
          >
            <h3 style={{ marginBottom: 0 }}>{suppliers.length} supplier{suppliers.length === 1 ? "" : "s"}</h3>
            <input
              placeholder="Search suppliers…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ marginBottom: 0, maxWidth: 220 }}
            />
          </div>
          <table>
            <thead>
              <tr>
                <th>
                  <button className="th-sort" onClick={() => setSortKey("supplier_name")}>
                    Supplier
                  </button>
                </th>
                <th>
                  <button className="th-sort" onClick={() => setSortKey("transaction_count")}>
                    Transactions
                  </button>
                </th>
                <th>Total amount</th>
                <th>
                  <button className="th-sort" onClick={() => setSortKey("flagged_transaction_count")}>
                    Flagged
                  </button>
                </th>
                <th>
                  <button className="th-sort" onClick={() => setSortKey("risk_score")}>
                    Risk score
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {suppliers.map((s) => {
                const risk = riskBySupplier[s.supplier_name];
                return (
                  <tr key={s.supplier_name}>
                    <td style={{ fontWeight: 600, color: "var(--ink-900)" }}>{s.supplier_name}</td>
                    <td className="mono">{s.transaction_count}</td>
                    <td className="mono">{formatAmounts(s)}</td>
                    <td>
                      {s.flagged_transaction_count > 0 ? (
                        <span className="badge severity-high">{s.flagged_transaction_count} flagged</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      {risk ? (
                        <span className="mono" title={risk.controls_hit.join(", ")}>
                          {risk.risk_score} ({risk.controls_hit.length} control{risk.controls_hit.length === 1 ? "" : "s"})
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </AppShell>
  );
}
