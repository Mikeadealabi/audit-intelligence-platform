interface BarChartItem {
  label: string;
  value: number;
  color?: string;
  displayValue?: string;
}

export default function BarChart({ items }: { items: BarChartItem[] }) {
  const max = Math.max(1, ...items.map((i) => i.value));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {items.map((item) => (
        <div key={item.label}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 4 }}>
            <span style={{ color: "var(--ink-700)", fontWeight: 600 }}>{item.label}</span>
            <span className="mono" style={{ color: "var(--ink-500)" }}>{item.displayValue ?? item.value}</span>
          </div>
          <div style={{ background: "var(--surface-sunken)", borderRadius: 999, height: 8, overflow: "hidden" }}>
            <div
              style={{
                width: `${(item.value / max) * 100}%`,
                height: "100%",
                borderRadius: 999,
                background: item.color ?? "var(--accent-500)",
                transition: "width 0.3s ease",
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
