"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPut, ApiError, type EngagementPlan } from "@/lib/api";

type Draft = {
  materialityAmount: string;
  materialityCurrency: string;
  scopeNotes: string;
  riskAssessment: string;
  riskRating: "" | "low" | "medium" | "high";
};

function draftFromPlan(plan: EngagementPlan): Draft {
  return {
    materialityAmount: plan.materiality_amount ?? "",
    materialityCurrency: plan.materiality_currency ?? "",
    scopeNotes: plan.scope_notes ?? "",
    riskAssessment: plan.risk_assessment ?? "",
    riskRating: plan.risk_rating ?? "",
  };
}

export default function EngagementPlanPanel({ engagementId }: { engagementId: string }) {
  const [plan, setPlan] = useState<EngagementPlan | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiGet<EngagementPlan>(`/engagements/${engagementId}/plan`).then((p) => {
      setPlan(p);
      setDraft((prev) => prev ?? draftFromPlan(p));
    });
  }, [engagementId]);

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await apiPut<EngagementPlan>(`/engagements/${engagementId}/plan`, {
        materiality_amount: draft.materialityAmount.trim() ? draft.materialityAmount.trim() : null,
        materiality_currency: draft.materialityCurrency.trim() ? draft.materialityCurrency.trim() : null,
        scope_notes: draft.scopeNotes.trim() ? draft.scopeNotes.trim() : null,
        risk_assessment: draft.riskAssessment.trim() ? draft.riskAssessment.trim() : null,
        risk_rating: draft.riskRating || null,
      });
      setPlan(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the engagement plan.");
    } finally {
      setBusy(false);
    }
  }

  if (!plan || !draft) return null;

  return (
    <div className="card">
      <div className="card-header">
        <h3>Engagement plan</h3>
        {plan.updated_at && (
          <span className="muted" style={{ fontSize: 12.5 }}>
            Last updated {new Date(plan.updated_at).toLocaleString()}
          </span>
        )}
      </div>
      <p className="muted" style={{ marginTop: -4 }}>
        Scope, materiality threshold, and risk assessment for this engagement — captured once up
        front, before fieldwork. This is capture only today; no control currently weighs a finding
        against this materiality threshold.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div>
          <label htmlFor="materiality-amount">Materiality threshold</label>
          <input
            id="materiality-amount"
            inputMode="decimal"
            placeholder="e.g. 5000000.00"
            value={draft.materialityAmount}
            onChange={(e) => setDraft({ ...draft, materialityAmount: e.target.value })}
          />
        </div>
        <div>
          <label htmlFor="materiality-currency">Currency</label>
          <input
            id="materiality-currency"
            placeholder="e.g. NGN"
            maxLength={10}
            value={draft.materialityCurrency}
            onChange={(e) => setDraft({ ...draft, materialityCurrency: e.target.value.toUpperCase() })}
          />
        </div>
      </div>

      <label htmlFor="risk-rating">Overall risk rating</label>
      <select
        id="risk-rating"
        value={draft.riskRating}
        onChange={(e) => setDraft({ ...draft, riskRating: e.target.value as Draft["riskRating"] })}
      >
        <option value="">Not set</option>
        <option value="low">Low</option>
        <option value="medium">Medium</option>
        <option value="high">High</option>
      </select>

      <label htmlFor="scope-notes">Scope notes</label>
      <textarea
        id="scope-notes"
        rows={3}
        placeholder="What's in and out of scope for this engagement."
        value={draft.scopeNotes}
        onChange={(e) => setDraft({ ...draft, scopeNotes: e.target.value })}
      />

      <label htmlFor="risk-assessment">Risk assessment</label>
      <textarea
        id="risk-assessment"
        rows={3}
        placeholder="Key risk areas identified before fieldwork."
        value={draft.riskAssessment}
        onChange={(e) => setDraft({ ...draft, riskAssessment: e.target.value })}
        style={{ marginBottom: 14 }}
      />

      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button className="btn primary" onClick={save} disabled={busy}>
          {busy ? <span className="spinner" /> : null} Save plan
        </button>
        {error && <span style={{ color: "var(--danger)", fontSize: 12.5 }}>{error}</span>}
        {saved && !error && <span style={{ color: "var(--success)", fontSize: 12.5 }}>Saved.</span>}
      </div>
    </div>
  );
}
