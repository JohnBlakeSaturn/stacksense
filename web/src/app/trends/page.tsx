"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
type Row = {
  skill: string;
  rank_slope: number;
  latest_adoption: number;
  years_observed: number;
  desire_gap?: number;
};
import { api } from "@/lib/api";
const rise: Row[] = [
  {
    skill: "Torch/PyTorch",
    rank_slope: 0.122,
    latest_adoption: 0.106,
    years_observed: 7,
    desire_gap: 0.041,
  },
  {
    skill: "Kubernetes",
    rank_slope: 0.052,
    latest_adoption: 0.285,
    years_observed: 6,
    desire_gap: 0.031,
  },
  {
    skill: "Rust",
    rank_slope: 0.049,
    latest_adoption: 0.141,
    years_observed: 7,
    desire_gap: 0.144,
  },
  {
    skill: "Go",
    rank_slope: 0.041,
    latest_adoption: 0.162,
    years_observed: 7,
    desire_gap: 0.07,
  },
  {
    skill: "Zig",
    rank_slope: 0.032,
    latest_adoption: 0.021,
    years_observed: 4,
    desire_gap: 0.055,
  },
];
const fall: Row[] = [
  {
    skill: "jQuery",
    rank_slope: -0.081,
    latest_adoption: 0.173,
    years_observed: 7,
  },
  {
    skill: "VBA",
    rank_slope: -0.052,
    latest_adoption: 0.047,
    years_observed: 7,
  },
  {
    skill: "AngularJS",
    rank_slope: -0.044,
    latest_adoption: 0.031,
    years_observed: 7,
  },
];
export default function Trends() {
  const [rising, setRising] = useState(rise);
  const [falling, setFalling] = useState(fall);
  const [preview, setPreview] = useState(false);
  useEffect(() => {
    Promise.all([api.trends("rising"), api.trends("falling")])
      .then(([a, b]) => {
        setRising(a.skills);
        setFalling(b.skills);
      })
      .catch(() => setPreview(true));
  }, []);
  return (
    <section className="section">
      <div className="shell">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "start",
          }}
        >
          <div>
            <div className="kicker">Seven years of survey rank</div>
            <h1 className="display serif">How the market is moving</h1>
          </div>
          {preview && <span className="preview">API fallback active</span>}
        </div>
        <p className="quiet" style={{ maxWidth: 690, fontSize: 18 }}>
          Rank makes years comparable despite changing respondent counts.
          Employer demand and developer sentiment are different signals—and
          their disagreement matters.
        </p>
        <div className="split" style={{ marginTop: 48 }}>
          <TrendList title="Rising" rows={rising} />
          <TrendList title="Falling" rows={falling} />
        </div>
        <div className="section">
          <h2 className="section-title serif">The desire gap</h2>
          <p className="quiet" style={{ maxWidth: 620 }}>
            Wanted minus used since 2023: technologies developers want to work
            with more than they currently do.
          </p>
          <div style={{ maxWidth: 740 }}>
            {rising
              .filter((x) => x.desire_gap != null)
              .sort((a, b) => (b.desire_gap ?? 0) - (a.desire_gap ?? 0))
              .map((x) => (
                <div
                  key={x.skill}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 3fr 70px",
                    gap: 14,
                    alignItems: "center",
                    padding: "11px 0",
                    borderBottom: "1px solid var(--rule)",
                  }}
                >
                  <span>{x.skill}</span>
                  <span style={{ height: 9, background: "var(--wash)" }}>
                    <span
                      style={{
                        display: "block",
                        height: "100%",
                        width: `${Math.min(100, (x.desire_gap ?? 0) * 600)}%`,
                        background: "var(--rise)",
                      }}
                    />
                  </span>
                  <strong style={{ textAlign: "right" }}>
                    +{((x.desire_gap ?? 0) * 100).toFixed(1)}%
                  </strong>
                </div>
              ))}
          </div>
        </div>
        <aside
          style={{
            borderLeft: "4px solid var(--signal)",
            background: "var(--wash)",
            padding: "22px 26px",
            maxWidth: 840,
          }}
        >
          <strong>Read this signal carefully.</strong>
          <p style={{ marginBottom: 0 }}>
            These figures describe Stack Overflow survey respondents, not
            employer demand. 222 of 457 surveyed technologies never appear in
            the job-posting dataset. Use trends as sentiment, and role profiles
            as demand.
          </p>
        </aside>
      </div>
    </section>
  );
}
function TrendList({ title, rows }: { title: string; rows: Row[] }) {
  return (
    <div>
      <h2 className="serif" style={{ fontSize: 32, marginTop: 0 }}>
        {title}
      </h2>
      {rows.map((r, i) => (
        <Link
          href={`/skills/${encodeURIComponent(r.skill)}`}
          key={r.skill}
          style={{
            display: "grid",
            gridTemplateColumns: "28px 1fr auto",
            gap: 10,
            padding: "13px 0",
            borderBottom: "1px solid var(--rule)",
          }}
        >
          <span className="quiet">{i + 1}</span>
          <span>
            {r.skill}
            <small className="quiet" style={{ display: "block" }}>
              {r.years_observed} years · {(r.latest_adoption * 100).toFixed(1)}%
              adoption
            </small>
          </span>
          <strong
            style={{
              color: r.rank_slope > 0 ? "var(--rise)" : "var(--signal)",
            }}
          >
            {r.rank_slope > 0 ? "↑" : "↓"} {Math.abs(r.rank_slope).toFixed(3)}
          </strong>
        </Link>
      ))}
    </div>
  );
}
