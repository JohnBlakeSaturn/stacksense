/* The role name is route state; rerun analysis only when that state changes. */
/* eslint-disable react-hooks/exhaustive-deps */
/* eslint-disable react-hooks/set-state-in-effect */
"use client";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import SkillInput, { type Chip } from "@/components/SkillInput";
import SupportBar from "@/components/SupportBar";
import SeniorityToggle from "@/components/SeniorityToggle";
import MechanismBadge from "@/components/MechanismBadge";
import LiftScatter from "@/components/LiftScatter";
import { api, fallback, type Role, type SkillRef } from "@/lib/api";
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
  const [level, setLevel] = useState("mid");
  const [preview, setPreview] = useState(false);
  useEffect(() => {
    api
      .roles()
      .then((r) => setRole(r.roles.find((x) => x.name === name)))
      .catch(() => {
        setRole(fallback.roles.find((x) => x.name === name));
        setPreview(true);
      });
  }, [name]);
  async function analyse() {
    const skills = chips.map((c) => c.canonical ?? c.input);
    try {
      setData(await api.gap(skills, name));
      setPreview(false);
    } catch {
      /* FALLBACK: visible sample data verifies the full gap-analysis UI without a server. */ setData(
        fallback.gap(skills, name),
      );
      setPreview(true);
    }
  }
  useEffect(() => {
    void analyse();
  }, [name]);
  const atLevel = (x: SkillRef) => ({
    ...x,
    support: x.by_seniority?.[level] ?? x.support,
  });
  const scatter = useMemo(
    () =>
      data
        ? { held: data.you_have.map(atLevel), gaps: data.gaps.map(atLevel) }
        : { held: [], gaps: [] },
    [data, level],
  );
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
            <div className="meta-row">
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
                  <span key={k}>
                    {k} {v.toLocaleString()}
                  </span>
                ))}
            </div>
          </div>
          {preview && <span className="preview">API fallback active</span>}
        </div>
        <div style={{ margin: "44px 0 22px" }}>
          <SkillInput
            value={chips}
            onChange={setChips}
            onSubmit={() => void analyse()}
          />
        </div>
        {role && (
          <SeniorityToggle
            counts={role.by_seniority}
            value={level}
            onChange={setLevel}
          />
        )}{" "}
        {data && (
          <>
            <div className="split">
              <div>
                <div className="kicker">You have</div>
                <p>
                  <strong>{data.you_have.length}</strong> recognised skills ·{" "}
                  <strong>{Math.round(data.coverage * 100)}%</strong> weighted
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
            <div className="rule-top" style={{ paddingTop: 42 }}>
              <h2 className="section-title serif">Nearest role comparison</h2>
              <p className="quiet">
                Sibling comparisons call the same gap endpoint for two roles.
                Choose another role from the role index once the API is
                connected to compare their distinctive gaps.
              </p>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
