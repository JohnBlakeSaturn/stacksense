"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import SkillInput, { type Chip } from "@/components/SkillInput";
import MechanismBadge from "@/components/MechanismBadge";
import SupportBar from "@/components/SupportBar";
import { api, fallback, type Recommendation } from "@/lib/api";
export default function Home() {
  const [chips, setChips] = useState<Chip[]>([]);
  const [health, setHealth] = useState(fallback.health);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setPreview(true));
  }, []);
  async function submit() {
    const skills = chips.map((c) => c.canonical ?? c.input);
    setBusy(true);
    try {
      const r = await api.recommend(skills);
      setRecs(r.recommendations);
      setNote(r.note);
      setPreview(false);
    } catch {
      /* FALLBACK: intentionally visible preview supports UI review before the API is wired. */ setRecs(
        fallback.recommendations(skills),
      );
      setNote(
        "Preview rankings only — start the API to see learned recommendations and measured posting counts.",
      );
      setPreview(true);
    } finally {
      setBusy(false);
    }
  }
  function example(values: string[]) {
    setChips(values.map((v) => ({ input: v, canonical: v })));
    setTimeout(
      () =>
        document
          .getElementById("skill-input")
          ?.scrollIntoView({ behavior: "smooth" }),
      0,
    );
  }
  return (
    <>
      <section className="section">
        <div className="shell">
          <div className="kicker">Market evidence for technical careers</div>
          <h1 className="display serif">What the market asks for next</h1>
          <p className="quiet" style={{ fontSize: 20, maxWidth: 620 }}>
            Enter what you know. See adjacent skills ranked from real
            job-posting patterns—not invented salaries or vague confidence
            scores.
          </p>
          <div id="skill-input" style={{ maxWidth: 820, marginTop: 38 }}>
            <SkillInput
              value={chips}
              onChange={setChips}
              onSubmit={() => void submit()}
              busy={busy}
            />
            <div
              style={{
                display: "flex",
                gap: 8,
                marginTop: 14,
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <span className="quiet" style={{ fontSize: 14 }}>
                Try
              </span>
              {[
                ["React", "TypeScript"],
                ["Python", "SQL"],
                ["Docker", "Kubernetes"],
              ].map((x) => (
                <button
                  key={x[0]}
                  onClick={() => example(x)}
                  style={{
                    border: 0,
                    background: "none",
                    color: "var(--graph)",
                    padding: 4,
                  }}
                >
                  {x.join(" · ")}
                </button>
              ))}
            </div>
          </div>
          <div
            className="meta-row rule-top"
            style={{ marginTop: 56, paddingTop: 20 }}
          >
            <span>
              <strong>{health.skills.toLocaleString()}</strong> skills
            </span>
            <span>
              <strong>{health.roles.toLocaleString()}</strong> roles
            </span>
            <span>
              <strong>{health.trends.toLocaleString()}</strong> surveyed
              technologies
            </span>
            {preview && <span className="preview">Preview data</span>}
          </div>
        </div>
      </section>
      {recs.length > 0 && (
        <section className="section" style={{ background: "var(--wash)" }}>
          <div className="shell">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "start",
                gap: 20,
              }}
            >
              <div>
                <MechanismBadge predicted />
                <h2
                  className="section-title serif"
                  style={{ margin: "14px 0 8px" }}
                >
                  Useful skills nearby
                </h2>
              </div>
              {preview && <span className="preview">API fallback active</span>}
            </div>
            <div style={{ maxWidth: 850 }}>
              {recs.map((r, i) => (
                <SupportBar
                  key={r.skill}
                  skill={r.skill}
                  support={Math.min(1, r.postings_mentioning / 7000)}
                  count={r.postings_mentioning}
                  total={34663}
                  trend={r.trend}
                  delay={i * 30}
                />
              ))}
            </div>
            <p
              className="quiet"
              style={{ maxWidth: 720, fontSize: 14, marginTop: 22 }}
            >
              {note}
            </p>
          </div>
        </section>
      )}
      <section className="section">
        <div className="shell split">
          <div>
            <h2 className="section-title serif">Measured, not guessed.</h2>
          </div>
          <div>
            <p>
              StackSense aggregates skill mentions across job postings, then
              learns which technologies tend to appear together. Gap analysis is
              exact aggregation; recommendations are rankings from a learned
              model.
            </p>
            <p className="quiet">
              Every percentage includes its denominator. Relative model scores
              are never presented as probabilities.
            </p>
            <Link className="button secondary" href="/roles">
              Explore roles
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
