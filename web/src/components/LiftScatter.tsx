"use client";
import { useState } from "react";
import Link from "next/link";
import type { SkillRef } from "@/lib/api";
export default function LiftScatter({ held, gaps }: { held: SkillRef[]; gaps: SkillRef[] }) {
  const [active, setActive] = useState<string | null>(null);
  const rows = [...held.map(x => ({ ...x, held: true })), ...gaps.map(x => ({ ...x, held: false }))].slice(0, 18);
  if (!rows.length) return <p className="empty">No skills to plot for this selection.</p>;
  const min = Math.min(0, Math.floor(Math.min(...rows.map(r => r.lift))));
  const max = Math.max(1, Math.ceil(Math.max(...rows.map(r => r.lift))));
  const y = (v: number) => 280 - ((v - min) / (max - min)) * 240;
  // Keep the data coordinates exact; move only the numbered labels.
  const labels: { x: number; y: number }[] = [];
  const points = rows.map(r => {
    const px = 65 + Math.max(0, Math.min(1, r.support)) * 535;
    const py = y(r.lift);
    let label = { x: px, y: py };
    search: for (let radius = 0; radius <= 240; radius += 14) {
      for (let angle = 0; angle < Math.PI * 2; angle += Math.PI / 8) {
        const candidate = { x: px + radius * Math.cos(angle), y: py + radius * Math.sin(angle) };
        if (candidate.x < 78 || candidate.x > 587 || candidate.y < 53 || candidate.y > 267) continue;
        if (labels.every(other => Math.hypot(candidate.x - other.x, candidate.y - other.y) >= 29)) {
          label = candidate;
          break search;
        }
      }
    }
    labels.push(label);
    return { px, py, ...label };
  });
  const selected = rows.find(r => r.skill === active);
  return <div>
    <p className="quiet">How often a skill appears, and how distinctive it is for this role. Select a numbered point or skill to highlight it.</p>
    <div style={{ overflowX: "auto" }}>
      <svg viewBox="0 0 640 340" role="group" aria-label="Skill support and log lift scatter plot" style={{ width: "100%", minWidth: 480, display: "block" }}>
        {[0, .25, .5, .75, 1].map(v => <g key={v}><line x1={65+v*535} x2={65+v*535} y1="40" y2="280" stroke="var(--rule)"/><text x={65+v*535} y="305" textAnchor="middle" fontSize="14" fill="var(--quiet)">{v*100}%</text></g>)}
        {Array.from({length:max-min+1},(_,i)=>min+i).map(v => <g key={v}><line x1="65" x2="600" y1={y(v)} y2={y(v)} stroke={v===0 ? "var(--ink)" : "var(--rule)"} strokeDasharray={v===0 ? "4 4" : undefined}/><text x="52" y={y(v)+5} textAnchor="end" fontSize="14" fill="var(--quiet)">{v}</text></g>)}
        <text x="65" y="20" fontSize="14" fill="var(--quiet)">Distinctiveness (log lift)</text>
        <text x="330" y="333" textAnchor="middle" fontSize="14" fill="var(--quiet)">Share of selected postings</text>
        {rows.map((r,i)=><g key={r.skill} role="button" tabIndex={0} aria-label={`${r.skill}: ${Math.round(r.support*100)}% support, ${r.lift.toFixed(2)} log lift`} onFocus={()=>setActive(r.skill)} onClick={()=>setActive(r.skill)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setActive(r.skill);}}} style={{cursor:"pointer"}}>
          <line x1={points[i].px} y1={points[i].py} x2={points[i].x} y2={points[i].y} stroke="var(--quiet)" />
          <circle cx={points[i].px} cy={points[i].py} r="3" fill={r.held ? "var(--graph)" : "var(--signal)"} />
          <circle cx={points[i].x} cy={points[i].y} r={active===r.skill ? 14 : 11} fill={r.held ? "var(--graph)" : "var(--signal)"} stroke="var(--paper)" strokeWidth="2" />
          <text x={points[i].x} y={points[i].y+4} textAnchor="middle" fontSize="11" fill="white" pointerEvents="none">{i+1}</text>
          <title>{r.skill}</title>
        </g>)}
      </svg>
    </div>
    <p role="status" style={{minHeight:26,fontSize:14}}>{selected ? `${selected.skill}: ${(selected.support*100).toFixed(1)}% support · ${selected.lift.toFixed(2)} log lift` : "Blue: you have · Orange: missing. Above zero means more distinctive than the corpus average."}</p>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit, minmax(min(100%, 250px), 1fr))",gap:"8px 24px"}}>
      {rows.map((r,i)=><div key={r.skill} style={{display:"flex",gap:8,alignItems:"baseline",fontSize:14}}><button aria-label={`Highlight ${r.skill}`} onClick={()=>setActive(r.skill)} style={{background:r.held ? "var(--graph)" : "var(--signal)",color:"white",border:0,borderRadius:20,minWidth:26,fontSize:12}}>{i+1}</button><Link href={`/skills/${encodeURIComponent(r.skill)}`} style={{textDecoration:active===r.skill ? "underline" : "none",overflowWrap:"anywhere"}}>{r.skill}</Link></div>)}
    </div>
    <p className="quiet" style={{fontSize:13}}>Log lift uses the whole role profile; support reflects the selected seniority. Leader lines connect displaced labels to their exact values. Scroll the chart horizontally on small screens.</p>
  </div>;
}
