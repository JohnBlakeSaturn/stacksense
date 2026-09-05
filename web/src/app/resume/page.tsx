"use client";
import { useState } from "react";
import { Upload } from "lucide-react";
import MechanismBadge from "@/components/MechanismBadge";
import SupportBar from "@/components/SupportBar";
import { api, type Recommendation, type RoleMatch } from "@/lib/api";
type Result = {
  sections_found: Record<string, number>;
  skills: Array<{
    skill: string;
    weight: number;
    section: string;
    matched_text: string;
    elementary: boolean;
  }>;
  unmatched_terms: string[];
  recommendations: Recommendation[];
  role_match: RoleMatch[];
};
export default function Resume() {
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(false);
  async function analyze(file: File) {
    setBusy(true);
    try {
      setResult(await api.resume(file));
      setPreview(false);
    } catch {
      /* FALLBACK: visible sample extraction tests the result flow until /resume/analyze exists. */ setResult(
        {
          sections_found: {
            projects: 5,
            skills: 4,
            experience: 3,
            coursework: 2,
          },
          skills: [
            {
              skill: "Python",
              weight: 1,
              section: "projects",
              matched_text: "Python",
              elementary: false,
            },
            {
              skill: "React",
              weight: 1,
              section: "experience",
              matched_text: "React",
              elementary: false,
            },
            {
              skill: "SQL",
              weight: 0.85,
              section: "skills",
              matched_text: "SQL",
              elementary: false,
            },
            {
              skill: "Docker",
              weight: 0.6,
              section: "coursework",
              matched_text: "Docker*",
              elementary: true,
            },
          ],
          unmatched_terms: ["MediaPipe", "PyQt", "YOLOv11"],
          recommendations: [
            {
              rank: 1,
              skill: "TypeScript",
              score: 3.2,
              category: "Language",
              postings_mentioning: 4321,
            },
            {
              rank: 2,
              skill: "Kubernetes",
              score: 2.8,
              category: "Tool",
              postings_mentioning: 3802,
            },
          ],
          role_match: [
            {
              role: "Developer, Front-end",
              coverage: 0.34,
              matched_skills: ["React"],
              top_missing: ["JavaScript", "TypeScript"],
              postings: 593,
            },
            {
              role: "Data Engineer",
              coverage: 0.28,
              matched_skills: ["Python", "SQL"],
              top_missing: ["Apache Spark", "Airflow"],
              postings: 1330,
            },
          ],
        },
      );
      setPreview(true);
    } finally {
      setBusy(false);
    }
  }
  const groups = result
    ? Object.entries(Object.groupBy(result.skills, (s) => s.section))
    : [];
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
            <div className="kicker">Resume evidence</div>
            <h1 className="display serif">See what your work already proves</h1>
          </div>
          {preview && <span className="preview">API fallback active</span>}
        </div>
        <p className="quiet" style={{ maxWidth: 650, fontSize: 18 }}>
          Upload PDF, DOCX, or TXT. The analysis groups skills by where they
          appear, shows unresolved terms, and compares all 21 roles.
        </p>
        <label className="drop">
          <Upload size={32} />
          <strong>
            {busy
              ? "Reading evidence…"
              : "Drop a resume here, or choose a file"}
          </strong>
          <span className="quiet">PDF · DOCX · TXT</span>
          <input
            disabled={busy}
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={(e) =>
              e.target.files?.[0] && void analyze(e.target.files[0])
            }
          />
        </label>
        {result && (
          <div style={{ marginTop: 52 }}>
            <div className="split">
              <div>
                <h2 className="serif" style={{ fontSize: 32 }}>
                  Evidence found
                </h2>
                {groups.map(([section, skills]) => (
                  <div key={section} style={{ marginBottom: 24 }}>
                    <strong style={{ textTransform: "capitalize" }}>
                      {section}{" "}
                      <span className="quiet">
                        · {result.sections_found[section] ?? skills?.length}
                      </span>
                    </strong>
                    <div
                      style={{
                        display: "flex",
                        gap: 7,
                        flexWrap: "wrap",
                        marginTop: 8,
                      }}
                    >
                      {skills?.map((s) => (
                        <span
                          key={s.skill}
                          style={{
                            border: "1px solid var(--graph-dim)",
                            padding: "4px 8px",
                            color: "var(--graph)",
                          }}
                        >
                          {s.skill}
                          {s.elementary ? " *" : ""}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <div>
                <h2 className="serif" style={{ fontSize: 32 }}>
                  Not resolved
                </h2>
                <p className="quiet">
                  These terms are outside the job-posting vocabulary, which
                  often misses niche and academic tools. They were not silently
                  discarded.
                </p>
                <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
                  {result.unmatched_terms.map((t) => (
                    <span
                      key={t}
                      style={{
                        padding: "4px 8px",
                        background: "var(--wash)",
                        color: "var(--quiet)",
                        textDecoration: "line-through",
                      }}
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <div className="section">
              <MechanismBadge />
              <h2 className="section-title serif">Closest role profiles</h2>
              {result.role_match.slice(0, 6).map((r) => (
                <div
                  key={r.role}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr auto",
                    gap: 18,
                    padding: "16px 0",
                    borderBottom: "1px solid var(--rule)",
                  }}
                >
                  <div>
                    <strong>{r.role}</strong>
                    <div className="quiet" style={{ fontSize: 13 }}>
                      Missing: {r.top_missing.join(", ")}
                    </div>
                  </div>
                  <span>
                    {Math.round(r.coverage * 100)}% weighted coverage ·{" "}
                    {r.postings.toLocaleString()} postings
                  </span>
                </div>
              ))}
            </div>
            <div>
              <MechanismBadge predicted />
              <h2 className="section-title serif">What to learn next</h2>
              <div style={{ maxWidth: 820 }}>
                {result.recommendations.map((r, i) => (
                  <SupportBar
                    key={r.skill}
                    skill={r.skill}
                    support={Math.min(1, r.postings_mentioning / 7000)}
                    count={r.postings_mentioning}
                    total={34663}
                    delay={i * 30}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
        <style jsx>{`
          .drop {
            margin-top: 42px;
            border: 1px dashed var(--graph);
            min-height: 210px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 8px;
            background: var(--wash);
            position: relative;
          }
          .drop input {
            position: absolute;
            inset: 0;
            opacity: 0;
            cursor: pointer;
          }
        `}</style>
      </div>
    </section>
  );
}
