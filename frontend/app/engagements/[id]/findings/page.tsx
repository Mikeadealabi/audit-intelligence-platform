"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { apiGet, getToken, ApiError, type Finding } from "@/lib/api";
import AppShell from "@/components/AppShell";
import EmptyState from "@/components/EmptyState";
import { AlertIcon, FileSearchIcon, UploadIcon } from "@/components/icons";

const STATUS_FILTERS = ["all", "open", "confirmed", "false_positive", "needs_more_evidence"] as const;

export default function FindingsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    apiGet<Finding[]>(`/engagements/${id}/findings`)
      .then(setFindings)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load findings."));
  }, [id]);

  const filtered = useMemo(() => {
    if (!findings) return [];
    if (statusFilter === "all") return findings;
    return findings.filter((f) => f.status === statusFilter);
  }, [findings, statusFilter]);

  const counts = useMemo(() => {
    const map: Record<string, number> = { all: findings?.length ?? 0 };
    for (const f of findings ?? []) map[f.status] = (map[f.status] ?? 0) + 1;
    return map;
  }, [findings]);

  return (
    <AppShell title="Findings" eyebrow="Review queue">
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      <p className="muted" style={{ marginBottom: 18 }}>
        Every finding below is a <strong>candidate for human review</strong>, not a confirmed
        exception. See each finding&rsquo;s evidence before acting on it.
      </p>

      {findings === null && !error && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" style={{ height: 72 }} />
          ))}
        </div>
      )}

      {findings?.length === 0 && (
        <div className="card">
          <EmptyState
            icon={<FileSearchIcon size={22} />}
            title="No findings yet"
            description="Upload a file and run a control from the engagement page to see findings here."
            action={
              <Link className="btn primary" href={`/engagements/${id}/upload`}>
                <UploadIcon size={14} /> Upload transactions
              </Link>
            }
          />
        </div>
      )}

      {findings && findings.length > 0 && (
        <>
          <div className="pill-row">
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                className={`pill ${statusFilter === s ? "active" : ""}`}
                onClick={() => setStatusFilter(s)}
              >
                {s === "all" ? "All" : s.replace(/_/g, " ")} ({counts[s] ?? 0})
              </button>
            ))}
          </div>

          {filtered.length === 0 ? (
            <div className="card">
              <EmptyState icon={<FileSearchIcon size={20} />} title="No findings match this filter" />
            </div>
          ) : (
            filtered.map((f) => (
              <Link key={f.id} href={`/engagements/${id}/findings/${f.id}`} className="finding-card">
                <div className="finding-card-top">
                  <span className={`badge severity-${f.severity}`}>{f.severity}</span>
                  <span className={`badge status-${f.status}`}>{f.status.replace(/_/g, " ")}</span>
                  <span className="muted" style={{ marginLeft: "auto", fontSize: 11.5 }}>
                    {new Date(f.created_at).toLocaleDateString()}
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-700)" }}>{f.summary}</p>
                <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
                  {f.evidence_record_ids.slice(0, 3).map((eid) => (
                    <span key={eid} className="evidence-chip">
                      {eid.slice(0, 8)}
                    </span>
                  ))}
                  {f.evidence_record_ids.length > 3 && (
                    <span className="muted" style={{ fontSize: 11 }}>
                      +{f.evidence_record_ids.length - 3} more
                    </span>
                  )}
                </div>
              </Link>
            ))
          )}
        </>
      )}
    </AppShell>
  );
}
