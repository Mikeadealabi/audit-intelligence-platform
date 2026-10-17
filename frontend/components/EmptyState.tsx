import type { ReactNode } from "react";

export default function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h3 style={{ marginBottom: 4 }}>{title}</h3>
      {description && <p className="muted" style={{ maxWidth: 360, margin: "0 auto" }}>{description}</p>}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}
