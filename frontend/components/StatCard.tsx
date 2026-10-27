import type { ReactNode } from "react";

export default function StatCard({
  label,
  value,
  accent,
  danger,
  icon,
  tone,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
  danger?: boolean;
  icon?: ReactNode;
  tone?: "blue" | "violet" | "amber" | "rose";
}) {
  return (
    <div className={`stat-card ${accent ? "accent" : ""} ${danger ? "danger" : ""}`}>
      <div>
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
      </div>
      {icon && <div className={`stat-card-icon ${tone ? `tone-${tone}` : ""}`}>{icon}</div>}
    </div>
  );
}
