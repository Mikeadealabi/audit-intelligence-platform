export default function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
}) {
  return (
    <div className={`stat-card ${accent ? "accent" : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}
