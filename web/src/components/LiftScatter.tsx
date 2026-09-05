"use client";
import Link from "next/link";
import type { SkillRef } from "@/lib/api";
export default function LiftScatter({
  held,
  gaps,
}: {
  held: SkillRef[];
  gaps: SkillRef[];
}) {
  const rows = [
    ...held.map((x) => ({ ...x, held: true })),
    ...gaps.map((x) => ({ ...x, held: false })),
  ].slice(0, 18);
  const maxLift = Math.max(2, ...rows.map((r) => r.lift));
  return (
    <div>
      <svg
        viewBox="0 0 700 330"
        role="img"
        aria-label="Skill support and role lift scatter plot"
        style={{ width: "100%", overflow: "visible" }}
      >
        <line x1="55" y1="285" x2="680" y2="285" stroke="var(--ink)" />
        <line x1="55" y1="20" x2="55" y2="285" stroke="var(--ink)" />
        <text x="620" y="318" fontSize="12" fill="var(--quiet)">
          support
        </text>
        <text x="12" y="22" fontSize="12" fill="var(--quiet)">
          lift
        </text>
        {rows.map((r, i) => {
          const x = 55 + (Math.min(0.8, r.support) / 0.8) * 625,
            y = 285 - (r.lift / maxLift) * 255;
          return (
            <Link href={`/skills/${encodeURIComponent(r.skill)}`} key={r.skill}>
              <circle
                cx={x}
                cy={y}
                r="6"
                fill={r.held ? "var(--graph-dim)" : "var(--signal)"}
              />
              <text
                x={x + 9}
                y={y + (i % 2 ? 14 : -8)}
                fontSize="11"
                fill="var(--ink)"
              >
                {r.skill}
              </text>
              <title>
                {r.skill}: {Math.round(r.support * 100)}% support,{" "}
                {r.lift.toFixed(2)}× lift
              </title>
            </Link>
          );
        })}
      </svg>
      <p className="quiet" style={{ fontSize: 13 }}>
        Upper-left skills are unusually defining for this role. Blue is held;
        orange is missing.
      </p>
    </div>
  );
}
