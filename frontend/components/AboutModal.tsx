"use client";

import { useEffect } from "react";
import { ShieldIcon, CheckCircleIcon, FileSearchIcon, LockIcon, CloseIcon } from "./icons";

const FEATURES = [
  {
    icon: <CheckCircleIcon size={16} />,
    tone: "",
    title: "Deterministic controls",
    text: "Not AI guesses — every finding is driven by a versioned, repeatable control.",
  },
  {
    icon: <FileSearchIcon size={16} />,
    tone: "tone-violet",
    title: "Evidence-grounded",
    text: "Every claim traces back to source rows and the exact dataset version.",
  },
  {
    icon: <LockIcon size={16} />,
    tone: "tone-amber",
    title: "Tenant-isolated",
    text: "Append-only, database-enforced audit log on every action.",
  },
];

export default function AboutModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(11, 15, 23, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
        padding: 20,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-modal-title"
        style={{
          maxWidth: 440,
          width: "100%",
          background: "var(--surface)",
          borderRadius: 28,
          padding: 32,
          position: "relative",
        }}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="btn ghost sm"
          style={{
            position: "absolute",
            top: 18,
            right: 18,
            padding: 6,
            background: "var(--surface-sunken)",
            borderRadius: "50%",
          }}
        >
          <CloseIcon size={15} />
        </button>

        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 14,
            background: "var(--accent-600)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: 18,
          }}
        >
          <ShieldIcon size={24} style={{ color: "#fff" }} />
        </div>

        <h2 id="about-modal-title" style={{ fontSize: 22, marginBottom: 8, letterSpacing: "-0.02em" }}>
          Audit Intelligence Platform
        </h2>

        <p style={{ fontSize: 14, lineHeight: 1.6, color: "var(--ink-600)", marginBottom: 22 }}>
          Evidence-grounded audit intelligence for Nigerian accounting and audit firms —
          upload transaction data, run deterministic controls, and route every finding
          through human review with a full evidence trail.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
          {FEATURES.map((item) => (
            <div
              key={item.title}
              style={{
                display: "flex",
                gap: 12,
                alignItems: "center",
                padding: "10px 12px",
                borderRadius: 16,
                border: "1px solid var(--ink-100)",
              }}
            >
              <span
                className={`stat-card-icon ${item.tone}`}
                style={{ width: 34, height: 34, borderRadius: 10 }}
              >
                {item.icon}
              </span>
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--ink-950)" }}>{item.title}</div>
                <div style={{ fontSize: 12.5, color: "var(--ink-600)" }}>{item.text}</div>
              </div>
            </div>
          ))}
        </div>

        <button type="button" className="btn primary" onClick={onClose} style={{ width: "100%" }}>
          Got it
        </button>

        <p style={{ fontSize: 11, color: "var(--ink-500)", margin: "14px 0 0", textAlign: "center" }}>
          Development build — a vertical slice, not a finished product.
        </p>
      </div>
    </div>
  );
}
