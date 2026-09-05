"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import SupportBar from "@/components/SupportBar";
import TrendLine from "@/components/TrendLine";
import { api, type Trend } from "@/lib/api";
type Data = {
  canonical: string;
  category: string;
  in_survey: boolean;
  postings_mentioning: number;
  degree: number;
  trend?: Trend | null;
  co_occurring_distinctive: Array<{
    skill: string;
    pmi: number;
    postings: number;
  }>;
  co_occurring_frequent: Array<{
    skill: string;
    pmi: number;
    postings: number;
  }>;
  roles_requiring: Array<{ role: string; support: number; lift: number }>;
};
export default function SkillPage() {
  const { name } = useParams<{ name: string }>();
  const label = decodeURIComponent(name);
  const [data, setData] = useState<Data | null>(null);
  const [preview, setPreview] = useState(false);
  useEffect(() => {
    api
      .skill(label)
      .then(setData)
      .catch(() => {
        /* FALLBACK: clearly labelled representative shape for offline visual testing. */ setData(
          {
            canonical: label,
            category: "Tool",
            in_survey: true,
            postings_mentioning: 5049,
            degree: 412,
            trend: {
              rank_slope: 0.052,
              direction: "rising",
              years_observed: 6,
              latest_adoption: 0.285,
            },
            co_occurring_distinctive: [
              { skill: "Docker Compose", pmi: 4.82, postings: 61 },
              { skill: "Podman", pmi: 3.91, postings: 48 },
              { skill: "Containerization", pmi: 3.21, postings: 244 },
            ],
            co_occurring_frequent: [
              { skill: "Kubernetes", pmi: 2.07, postings: 1738 },
              { skill: "AWS", pmi: 1.42, postings: 1481 },
              { skill: "Linux", pmi: 1.31, postings: 1290 },
            ],
            roles_requiring: [
              { role: "DevOps Engineer", support: 0.62, lift: 1.94 },
              { role: "Cloud Infrastructure", support: 0.51, lift: 1.63 },
              { role: "Software Engineer", support: 0.27, lift: 0.88 },
            ],
          },
        );
        setPreview(true);
      });
  }, [label]);
  if (!data)
    return <div className="shell section">Loading skill evidence…</div>;
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
            <div className="kicker">{data.category}</div>
            <h1 className="display serif">{data.canonical}</h1>
            <div className="meta-row">
              <span>
                <strong>{data.postings_mentioning.toLocaleString()}</strong>{" "}
                postings
              </span>
              <span>
                <strong>{data.degree.toLocaleString()}</strong> network
                neighbours
              </span>
              <span>
                {data.in_survey ? "Survey trend available" : "No survey trend"}
              </span>
            </div>
          </div>
          {preview && <span className="preview">API fallback active</span>}
        </div>
        <div className="split" style={{ marginTop: 52 }}>
          <Neighbour
            title="Most distinctive"
            subtitle="Unusually likely to appear with this skill"
            rows={data.co_occurring_distinctive}
          />
          <Neighbour
            title="Most frequent"
            subtitle="Largest raw co-occurrence counts"
            rows={data.co_occurring_frequent}
          />
        </div>
        <div className="section">
          <h2 className="section-title serif">Roles that ask for it</h2>
          <div style={{ maxWidth: 840 }}>
            {data.roles_requiring.map((r, i) => (
              <SupportBar
                key={r.role}
                skill={r.role}
                support={r.support}
                count={Math.round(r.support * 1000)}
                total={1000}
                delay={i * 30}
              />
            ))}
          </div>
        </div>
        {data.trend && (
          <div className="rule-top" style={{ paddingTop: 36 }}>
            <h2 className="section-title serif">Survey movement</h2>
            <TrendLine name={data.canonical} trend={data.trend} />
            <p className="quiet" style={{ maxWidth: 700, fontSize: 13 }}>
              {data.trend.caveat ??
                "Rank is plotted instead of raw adoption because survey respondent counts vary between years."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
function Neighbour({
  title,
  subtitle,
  rows,
}: {
  title: string;
  subtitle: string;
  rows: Array<{ skill: string; pmi: number; postings: number }>;
}) {
  return (
    <div>
      <h2 className="serif" style={{ fontSize: 28, margin: 0 }}>
        {title}
      </h2>
      <p className="quiet">{subtitle}</p>
      {rows.map((r) => (
        <Link
          href={`/skills/${encodeURIComponent(r.skill)}`}
          key={r.skill}
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto",
            padding: "12px 0",
            borderBottom: "1px solid var(--rule)",
          }}
        >
          <span>{r.skill}</span>
          <span>
            <strong>{r.pmi.toFixed(2)}</strong> lift index ·{" "}
            {r.postings.toLocaleString()}
          </span>
        </Link>
      ))}
    </div>
  );
}
