"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { apiGet, apiPost, getToken, ApiError, type Finding } from "@/lib/api";
import AppShell from "@/components/AppShell";
import EmptyState from "@/components/EmptyState";
import StatCard from "@/components/StatCard";
import { AlertIcon, FileSearchIcon, UploadIcon, CheckCircleIcon, ClockIcon } from "@/components/icons";

const SEVERITY_ICON: Record<string, typeof AlertIcon> = {
  high: AlertIcon,
  medium: ClockIcon,
  low: CheckCircleIcon,
};

const STATUS_FILTERS = ["all", "open", "confirmed", "false_positive", "needs_more_evidence"] as const;

const BULK_DISPOSITIONS = [
  { value: "confirmed", label: "Confirmed exception" },
  { value: "false_positive", label: "False positive" },
  { value: "needs_more_evidence", label: "Needs more evidence" },
] as const;

export default function FindingsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");

  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkStatus, setBulkStatus] = useState<(typeof BULK_DISPOSITIONS)[number]["value"]>("confirmed");
  const [bulkRationale, setBulkRationale] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    load();
  }, [id]);

  function load() {
    apiGet<Finding[]>(`/engagements/${id}/findings`)
      .then(setFindings)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load findings."));
  }

  function toggleSelected(findingId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(findingId)) next.delete(findingId);
      else next.add(findingId);
      return next;
    });
  }

  function exitSelectMode() {
    setSelectMode(false);
    setSelected(new Set());
    setBulkError(null);
    setBulkRationale("");
  }

  async function applyBulkDisposition() {
    if (selected.size === 0 || bulkRationale.trim().length === 0) return;
    setBulkBusy(true);
    setBulkError(null);
    const ids = [...selected];
    const results = await Promise.allSettled(
      ids.map((findingId) =>
        apiPost(`/engagements/${id}/findings/${findingId}/disposition`, {
          status: bulkStatus,
          rationale: bulkRationale,
        })
      )
    );
    const failures = results.filter((r) => r.status === "rejected").length;
    setBulkBusy(false);
    if (failures > 0) {
      setBulkError(`${failures} of ${ids.length} update(s) failed. The rest were recorded — review and retry the rest.`);
    } else {
      exitSelectMode();
    }
    load();
  }

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

  const severityCounts = useMemo(() => {
    const map: Record<string, number> = { high: 0, medium: 0, low: 0 };
    for (const f of findings ?? []) map[f.severity] = (map[f.severity] ?? 0) + 1;
    return map;
  }, [findings]);

  return (
    <AppShell
      title="Findings"
      eyebrow="Review queue"
      icon={<FileSearchIcon size={17} />}
      actions={
        findings &&
        findings.length > 0 && (
          <button className="btn secondary sm" onClick={() => (selectMode ? exitSelectMode() : setSelectMode(true))}>
            {selectMode ? "Cancel selection" : "Select findings"}
          </button>
        )
      }
    >
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      <p className="page-lede">
        Every finding below is a <strong>candidate for human review</strong>, not a confirmed
        exception. See each finding&rsquo;s evidence before acting on it.
      </p>

      {findings && findings.length > 0 && (
        <div className="stat-grid">
          <StatCard label="Total findings" value={findings.length} icon={<FileSearchIcon size={15} />} />
          <StatCard
            label="High severity"
            value={severityCounts.high}
            danger={severityCounts.high > 0}
            icon={<AlertIcon size={15} />}
          />
          <StatCard label="Open" value={counts.open ?? 0} icon={<ClockIcon size={15} />} />
          <StatCard
            label="Confirmed exceptions"
            value={counts.confirmed ?? 0}
            icon={<CheckCircleIcon size={15} />}
          />
        </div>
      )}

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
          {selectMode && (
            <div className="card" style={{ background: "var(--accent-50)", borderColor: "var(--accent-100)" }}>
              <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <strong style={{ fontSize: 13.5 }}>
                  {selected.size} finding{selected.size === 1 ? "" : "s"} selected
                </strong>
                <select
                  value={bulkStatus}
                  onChange={(e) => setBulkStatus(e.target.value as typeof bulkStatus)}
                  style={{ marginBottom: 0, width: 200 }}
                >
                  {BULK_DISPOSITIONS.map((d) => (
                    <option key={d.value} value={d.value}>
                      {d.label}
                    </option>
                  ))}
                </select>
                <input
                  placeholder="Rationale (required, applied to all selected)"
                  value={bulkRationale}
                  onChange={(e) => setBulkRationale(e.target.value)}
                  style={{ marginBottom: 0, flex: 1, minWidth: 220 }}
                />
                <button
                  className="btn primary sm"
                  disabled={selected.size === 0 || bulkRationale.trim().length === 0 || bulkBusy}
                  onClick={applyBulkDisposition}
                >
                  {bulkBusy ? <span className="spinner" /> : null} Apply to {selected.size}
                </button>
              </div>
              {bulkError && (
                <div className="error-banner" style={{ marginTop: 10, marginBottom: 0 }}>
                  <AlertIcon size={15} />
                  {bulkError}
                </div>
              )}
            </div>
          )}

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
            filtered.map((f) => {
              const SeverityIcon = SEVERITY_ICON[f.severity] ?? AlertIcon;
              return (
                <Link
                  key={f.id}
                  href={`/engagements/${id}/findings/${f.id}`}
                  className={`finding-card severity-${f.severity}`}
                  onClick={(e) => {
                    if (selectMode) {
                      e.preventDefault();
                      toggleSelected(f.id);
                    }
                  }}
                >
                  {selectMode && (
                    <input
                      type="checkbox"
                      checked={selected.has(f.id)}
                      onChange={() => toggleSelected(f.id)}
                      onClick={(e) => e.stopPropagation()}
                      style={{ marginTop: 10, marginBottom: 0, width: 16, flexShrink: 0 }}
                    />
                  )}
                  <div className={`finding-card-icon severity-${f.severity}`}>
                    <SeverityIcon size={16} />
                  </div>
                  <div className="finding-card-body">
                    <div className="finding-card-top">
                      <span className={`badge severity-${f.severity}`}>{f.severity}</span>
                      <span className={`badge status-${f.status}`}>{f.status.replace(/_/g, " ")}</span>
                      {f.sign_off_status !== "not_required" && (
                        <span className={`badge signoff-${f.sign_off_status}`}>
                          {f.sign_off_status.replace(/_/g, " ")}
                        </span>
                      )}
                      <span className="muted" style={{ marginLeft: "auto", fontSize: 11.5 }}>
                        {new Date(f.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-700)" }}>{f.summary}</p>
                    <div style={{ marginTop: 8, display: "flex", gap: 6, alignItems: "center" }}>
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
                  </div>
                </Link>
              );
            })
          )}
        </>
      )}
    </AppShell>
  );
}
