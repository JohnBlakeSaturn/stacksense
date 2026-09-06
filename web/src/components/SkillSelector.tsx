"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
export default function SkillSelector({ current }: { current: string }) {
  const router = useRouter();
  const [skills, setSkills] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { api.vocabulary().then(r => setSkills(r.skills.map(s => s.canonical))).catch(() => setError("Skill list unavailable. Refresh to try again.")); }, []);
  const matches = skills.filter(s => s.toLowerCase().includes(query.toLowerCase()));
  return <div style={{ maxWidth: 620, marginBottom: 32 }}>
    <label htmlFor="skill-search" className="kicker">Explore a skill</label>
    <input id="skill-search" type="search" placeholder="Search skills…" value={query} onChange={e => setQuery(e.target.value)} style={{ display: "block", width: "100%", padding: "10px 12px", border: "1px solid var(--rule)", background: "var(--paper)", marginTop: 8 }} />
    <select aria-label="Select skill" value={current} onChange={e => { router.push(`/skills/${encodeURIComponent(e.target.value)}`); setQuery(""); }} style={{ width: "100%", padding: "10px 12px", border: "1px solid var(--rule)", background: "var(--paper)", color: "var(--ink)", font: "inherit", marginTop: 8 }}>
      <option value={current}>{current}</option>
      {matches.filter(s => s !== current).map(s => <option key={s} value={s}>{s}</option>)}
    </select>
    <p className="quiet" role="status" style={{ fontSize: 13, marginTop: 6 }}>{error || (skills.length ? `${matches.length.toLocaleString()} matching skills` : "Loading skills…")}</p>
  </div>;
}
