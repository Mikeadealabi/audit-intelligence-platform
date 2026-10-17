"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiGet, getToken, ApiError, type AuditEvent } from "@/lib/api";
import AppShell from "@/components/AppShell";
import EmptyState from "@/components/EmptyState";
import { AlertIcon, ActivityIcon } from "@/components/icons";

const PAGE_SIZE = 50;

const EVENT_LABELS: Record<string, string> = {
  "engagement.created": "Engagement created",
  "import.preview_created": "Import previewed",
  "import.committed": "Dataset version committed",
  "control.run_completed": "Control run completed",
  "finding.disposition_recorded": "Finding disposition recorded",
  "investigation.requested": "AI investigation requested",
  "investigation.completed": "AI investigation completed",
  "investigation.failed": "AI investigation failed",
  "llm_tool.invoked": "AI investigation tool call",
  "report.exported": "Report exported",
};

function describe(event: AuditEvent): string {
  const label = EVENT_LABELS[event.event_type] ?? event.event_type;
  const p = event.payload;
  if (event.event_type === "finding.disposition_recorded" && typeof p.new_status === "string") {
    return `${label}: ${String(p.new_status).replace(/_/g, " ")}`;
  }
  if (event.event_type === "control.run_completed" && typeof p.finding_count === "number") {
    return `${label} — ${p.finding_count} finding${p.finding_count === 1 ? "" : "s"}`;
  }
  if (event.event_type === "import.committed" && typeof p.row_count === "number") {
    return `${label} — ${p.row_count} row${p.row_count === 1 ? "" : "s"}`;
  }
  return label;
}

export default function ActivityPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    load(0, true);
  }, [id]);

  async function load(offset: number, replace: boolean) {
    try {
      const page = await apiGet<AuditEvent[]>(`/engagements/${id}/activity?limit=${PAGE_SIZE}&offset=${offset}`);
      setEvents((prev) => (replace ? page : [...(prev ?? []), ...page]));
      setHasMore(page.length === PAGE_SIZE);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load activity.");
    } finally {
      setLoadingMore(false);
    }
  }

  function loadMore() {
    setLoadingMore(true);
    load(events?.length ?? 0, false);
  }

  return (
    <AppShell title="Activity" eyebrow="Audit log" icon={<ActivityIcon size={17} />}>
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      <p className="page-lede">
        Every action in this engagement, read from the append-only audit log — the database
        itself rejects edits or deletes on these rows, so this view can&rsquo;t be out of date
        or tampered with.
      </p>

      {events === null && !error && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton" style={{ height: 44 }} />
          ))}
        </div>
      )}

      {events?.length === 0 && (
        <div className="card">
          <EmptyState icon={<ActivityIcon size={20} />} title="No activity recorded yet" />
        </div>
      )}

      {events && events.length > 0 && (
        <div className="activity-timeline">
          {events.map((event) => (
            <div key={event.id} className="activity-item">
              <div className="activity-dot" />
              <div className="activity-body">
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                  <strong style={{ fontSize: 13.5 }}>{describe(event)}</strong>
                  <span className="muted mono" style={{ fontSize: 11, whiteSpace: "nowrap" }}>
                    {new Date(event.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="muted" style={{ fontSize: 12 }}>
                  {event.actor_email ?? "system"}
                </div>
              </div>
            </div>
          ))}

          {hasMore && (
            <button className="btn secondary sm" onClick={loadMore} disabled={loadingMore} style={{ marginTop: 10 }}>
              {loadingMore ? <span className="spinner dark" /> : null} Load more
            </button>
          )}
        </div>
      )}
    </AppShell>
  );
}
