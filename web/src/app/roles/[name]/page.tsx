"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import SkillInput, { type Chip } from "@/components/SkillInput";
import SupportBar from "@/components/SupportBar";
import SeniorityToggle from "@/components/SeniorityToggle";
import MechanismBadge from "@/components/MechanismBadge";
import LiftScatter from "@/components/LiftScatter";
import { api, type Role, type SkillRef } from "@/lib/api";
type Gap = {
  role: string;
  postings_analysed: number;
  coverage: number;
  you_have: SkillRef[];
  gaps: SkillRef[];
  note: string;
};
export default function RolePage() {
  const params = useParams<{ name: string }>();
  const name = decodeURIComponent(params.name);
  const [chips, setChips] = useState<Chip[]>([
    { input: "Python", canonical: "Python" },
    { input: "SQL", canonical: "SQL" },
  ]);
  const [role, setRole] = useState<Role | undefined>();
  const [data, setData] = useState<Gap | null>(null);
  const [level, setLevel] = useState("all");
  const [submitted, setSubmitted] = useState(["Python", "SQL"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    api.roles().then(r => { if (!cancelled) setRole(r.roles.find(x => x.name === name)); }).catch(() => {});
    return () => { cancelled = true; };
  }, [name]);
  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    setError("");
    api.gap(submitted, name, level === "all" ? undefined : level)
      .then(r => { if (!cancelled) setData(r); })
      .catch(() => { if (!cancelled) { setData(null); setError("Could not load role evidence. Try another seniority or submit your skills again."); } })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [submitted, name, level]);
  const scatter = { held: data?.you_have ?? [], gaps: data?.gaps ?? [] };
  return (
    <section className="section">
      <div className="shell">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 20,
            alignItems: "start",
          }}
        >
          <div>
            <div className="kicker">Role gap analysis</div>
            <h1
              className="display serif"
              style={{ fontSize: "clamp(42px,6vw,64px)" }}
            >
              {name}
            </h1>
            <div className="meta-row" style={{ gap: "12px 32px", marginTop: 16 }}>
              <span>
                <strong>
                  {(
                    data?.postings_analysed ??
                    role?.postings ??
                    0
                  ).toLocaleString()}
                </strong>{" "}
                postings
              </span>
              {role &&
                Object.entries(role.by_seniority).map(([k, v]) => (
                  <span key={k} style={{ display: "inline-flex", gap: 10 }}>
                    <span>{k}</span><span style={{ letterSpacing: ".025em" }}>{v.toLocaleString()}</span>
                  </span>
                ))}
            </div>
          </div>

        </div>
        <div style={{ margin: "44px 0 22px" }}>
          <SkillInput
            value={chips}
            onChange={setChips}
            onSubmit={() => setSubmitted(chips.map(c => c.canonical ?? c.input))}
            busy={busy}
          />
        </div>
        {role && (
          <SeniorityToggle
            counts={role.by_seniority}
            value={level}
            onChange={setLevel}
          />
        )}{" "}
        {busy && <p role="status">Updating role evidence…</p>}
        {error && <p role="alert" className="empty">{error}</p>}
        {data && !busy && (
          <>
            <div className="split">
              <div>
                <div className="kicker">You have</div>
                <p>
                  <strong>{data.you_have.length}</strong> recognised skills ·{" "}
                  <strong>{Math.round(data.coverage * 100)}%</strong> role skill
                  coverage
                </p>
                {scatter.held.length ? (
                  scatter.held.map((r, i) => (
                    <SupportBar
                      key={r.skill}
                      {...r}
                      held
                      total={data.postings_analysed}
                      count={Math.round(r.support * data.postings_analysed)}
                      delay={i * 30}
                    />
                  ))
                ) : (
                  <div className="empty">
                    None of the entered skills appear in this role profile.
                  </div>
                )}
              </div>
              <div>
                <MechanismBadge />
                <h2
                  className="serif"
                  style={{ fontSize: 28, margin: "10px 0" }}
                >
                  Missing
                </h2>
                <p className="quiet" style={{ fontSize: 13, lineHeight: 1.7, margin: "0 0 20px" }}>
                  Ranked by prevalence and role distinctiveness. Bars show the share
                  of postings mentioning each skill, so longer bars may appear lower.
                </p>
                {scatter.gaps.map((r, i) => (
                  <SupportBar
                    key={r.skill}
                    {...r}
                    total={data.postings_analysed}
                    count={Math.round(r.support * data.postings_analysed)}
                    delay={i * 30}
                  />
                ))}
              </div>
            </div>
            <p className="quiet" style={{ fontSize: 13 }}>
              {data.note}
            </p>
            <div className="section">
              <h2 className="section-title serif">What defines this role</h2>
              <LiftScatter held={scatter.held} gaps={scatter.gaps} />
            </div>

          </>
        )}
      </div>
    </section>
  );
}
