"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiGet, apiPost, getToken, ApiError, type Engagement } from "@/lib/api";
import AppShell from "@/components/AppShell";
import EmptyState from "@/components/EmptyState";
import { AlertIcon, ArrowRightIcon, GridIcon } from "@/components/icons";

export default function EngagementsPage() {
  const router = useRouter();
  const [engagements, setEngagements] = useState<Engagement[] | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [clientName, setClientName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    load();
  }, []);

  async function load() {
    try {
      setEngagements(await apiGet<Engagement[]>("/engagements"));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.push("/");
      else setError(err instanceof ApiError ? err.message : "Could not load engagements.");
    }
  }

  async function createEngagement(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await apiPost("/engagements", { name, client_name: clientName });
      setName("");
      setClientName("");
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create engagement.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell
      title="Engagements"
      eyebrow="Workspace"
      actions={
        <button className="btn primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancel" : "+ New engagement"}
        </button>
      }
    >
      {error && (
        <div className="error-banner">
          <AlertIcon size={15} />
          {error}
        </div>
      )}

      {showForm && (
        <div className="card">
          <h3 style={{ marginBottom: 14 }}>New engagement</h3>
          <form onSubmit={createEngagement}>
            <div style={{ display: "flex", gap: 14 }}>
              <div style={{ flex: 1 }}>
                <label htmlFor="name">Engagement name</label>
                <input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div style={{ flex: 1 }}>
                <label htmlFor="clientName">Client name</label>
                <input id="clientName" required value={clientName} onChange={(e) => setClientName(e.target.value)} />
              </div>
            </div>
            <button className="btn primary" type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create engagement"}
            </button>
          </form>
        </div>
      )}

      {engagements === null && !error && (
        <div className="stat-grid">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" style={{ height: 96, borderRadius: "var(--radius-lg)" }} />
          ))}
        </div>
      )}

      {engagements?.length === 0 && (
        <div className="card">
          <EmptyState
            icon={<GridIcon size={22} />}
            title="No engagements yet"
            description="Create your first engagement to start uploading transaction data and running controls."
            action={
              <button className="btn primary" onClick={() => setShowForm(true)}>
                + New engagement
              </button>
            }
          />
        </div>
      )}

      {engagements && engagements.length > 0 && (
        <div className="stat-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
          {engagements.map((e) => (
            <Link key={e.id} href={`/engagements/${e.id}`} className="card" style={{ display: "block", color: "inherit", textDecoration: "none", marginBottom: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <h3 style={{ marginBottom: 3 }}>{e.name}</h3>
                  <p className="muted" style={{ marginBottom: 0 }}>{e.client_name}</p>
                </div>
                <span className="badge neutral">{e.status}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 16, color: "var(--accent-600)", fontSize: 12.5, fontWeight: 600 }}>
                Open engagement <ArrowRightIcon size={13} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </AppShell>
  );
}
