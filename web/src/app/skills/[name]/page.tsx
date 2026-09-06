"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import styles from "./neighbours.module.css";
import SkillSelector from "@/components/SkillSelector";
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
    category: string | null;
    pmi: number;
    postings: number;
  }>;
  co_occurring_frequent: Array<{
    skill: string;
    category: string | null;
    pmi: number;
    postings: number;
  }>;
  roles_requiring: Array<{ role: string; support: number; lift: number }>;
};
export default function SkillPage() {
  const { name } = useParams<{ name: string }>();
  const label = decodeURIComponent(name);
  const [data, setData] = useState<Data | null>(null);
  const [loadedLabel, setLoadedLabel] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    api.skill(label).then(value => { if (!cancelled) { setData(value); setLoadedLabel(label); setError(""); } })
      .catch(() => { if (!cancelled) { setData(null); setError("Could not load this skill. Choose another skill or refresh to try again."); } });
    return () => { cancelled = true; };
  }, [label]);
  if (error || !data || loadedLabel !== label)
    return <div className="shell section"><SkillSelector current={label} /><p role="status">{error || "Loading skill evidence…"}</p></div>;
  return (
    <section className="section">
      <div className="shell">
        <SkillSelector current={label} />
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
                href={`/roles/${encodeURIComponent(r.role)}`}
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
  rows: Array<{ skill: string; category: string | null; pmi: number; postings: number }>;
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
          className={styles.row}
        >
          <span className={styles.identity}>
            <span>{r.skill}</span>
            {r.category && <span className={styles.category}>{r.category.replaceAll("/", " / ")}</span>}
          </span>
          <span className={styles.metrics}>
            <span className={styles.metric} title="Pointwise mutual information: how much more often these skills co-occur than expected by chance">
              <strong>{r.pmi.toFixed(2)}</strong><span className={styles.unit}>PMI</span>
            </span>
            <span className={styles.metric}>
              <strong>{r.postings.toLocaleString()}</strong><span className={styles.unit}>postings</span>
            </span>
          </span>
        </Link>
      ))}
    </div>
  );
}
