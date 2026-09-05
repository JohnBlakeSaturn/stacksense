"use client";
import Link from "next/link";
import type { Trend } from "@/lib/api";
export default function SupportBar({
  skill,
  support,
  count,
  total,
  held = false,
  trend,
  delay = 0,
}: {
  skill: string;
  support: number;
  count?: number;
  total?: number;
  held?: boolean;
  trend?: Trend | null;
  delay?: number;
}) {
  return (
    <Link href={`/skills/${encodeURIComponent(skill)}`} className="bar">
      <span className="track">
        <span
          className="fill"
          style={{
            width: `${Math.min(100, support * 100)}%`,
            background: held ? "var(--graph-dim)" : "var(--signal)",
            animationDelay: `${delay}ms`,
          }}
        />
      </span>
      <span className="name">{skill}</span>
      <span className="value">
        <span className="pct">{Math.round(support * 100)}%</span>
        {count != null && total ? (
          <span className="denom">
            {count.toLocaleString()} of {total.toLocaleString()}
          </span>
        ) : null}
      </span>
      <span
        style={{
          color:
            trend?.direction === "rising"
              ? "var(--rise)"
              : trend?.direction === "falling"
                ? "var(--signal)"
                : "transparent",
        }}
      >
        {trend?.direction === "rising"
          ? "↑"
          : trend?.direction === "falling"
            ? "↓"
            : "·"}
      </span>
      <style jsx>{`
        .bar {
          display: grid;
          grid-template-columns: minmax(80px, 1fr) minmax(
              110px,
              1.1fr
            ) 92px 15px;
          gap: 12px;
          align-items: center;
          padding: 9px 0;
          border-bottom: 1px solid var(--rule);
          font-size: 14px;
        }
        .track {
          height: 8px;
          background: var(--wash);
          overflow: hidden;
        }
        .fill {
          height: 100%;
          display: block;
          transform-origin: left;
          animation: draw 0.4s cubic-bezier(0.2, 0, 0, 1) both;
        }
        .value {
          text-align: right;
        }
        .denom {
          display: none;
        }
        .bar:hover .pct {
          display: none;
        }
        .bar:hover .denom {
          display: inline;
        }
        @keyframes draw {
          from {
            transform: scaleX(0);
          }
          to {
            transform: scaleX(1);
          }
        }
        @media (max-width: 560px) {
          .bar {
            grid-template-columns: 70px 1fr 70px 12px;
            gap: 8px;
          }
          .denom {
            font-size: 11px;
          }
        }
      `}</style>
    </Link>
  );
}
