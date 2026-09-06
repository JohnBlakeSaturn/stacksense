import type { Trend } from "@/lib/api";
export default function TrendLine({
  name,
  trend,
}: {
  name?: string;
  trend: Trend;
}) {
  if (trend.years_observed < 4)
    return <p className="quiet">Too few survey years for a reliable trend.</p>;
  const entries = Object.entries(trend.rank_series ?? {}).filter(([,v]) => Number.isFinite(v)).sort(([a],[b]) => Number(a)-Number(b));
  if (entries.length < 2) return <p className="quiet">No survey series available for this skill.</p>;
  const vals = entries.map(([, v]) => v);
  const min = Math.min(...vals),
    max = Math.max(...vals);
  const points = entries
    .map(
      ([, v], i) =>
        `${entries.length === 1 ? 0 : (i / (entries.length - 1)) * 240},${60 - ((v - min) / (max - min || 1)) * 50}`,
    )
    .join(" ");
  return (
    <div>
      <svg
        viewBox="0 0 240 68"
        role="img"
        aria-label={`${name ?? "Skill"} rank trend`}
        style={{ width: "100%", maxWidth: 300 }}
      >
        <line x1="0" y1="61" x2="240" y2="61" stroke="var(--rule)" />
        <polyline
          fill="none"
          stroke={
            trend.direction === "falling" ? "var(--signal)" : "var(--rise)"
          }
          strokeWidth="2.5"
          points={points}
        />
      </svg>
      <div className="quiet" style={{ fontSize: 12 }}>
        {trend.rank_slope >= 0 ? "rank ↑" : "rank ↓"}{" "}
        {Math.abs(trend.rank_slope).toFixed(3)}/yr
        {trend.latest_adoption != null
          ? ` · ${(trend.latest_adoption * 100).toFixed(1)}% adoption`
          : ""}{" "}
        · {trend.years_observed} years observed
      </div>
    </div>
  );
}
