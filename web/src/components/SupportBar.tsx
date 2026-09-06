"use client";
import Link from "next/link";
import styles from "./SupportBar.module.css";
import type { Trend } from "@/lib/api";
export default function SupportBar({
  skill,
  href,
  support,
  count,
  total,
  held = false,
  trend,
  delay = 0,
}: {
  skill: string;
  href?: string;
  support: number;
  count?: number;
  total?: number;
  held?: boolean;
  trend?: Trend | null;
  delay?: number;
}) {
  return (
    <Link href={href ?? `/skills/${encodeURIComponent(skill)}`} className={styles.bar}>
      <span className={styles.track}>
        <span
          className={styles.fill}
          style={{
            width: `${Math.max(0, Math.min(100, support * 100))}%`,
            background: held ? "var(--graph-dim)" : "var(--signal)",
            animationDelay: `${delay}ms`,
          }}
        />
      </span>
      <span className={styles.name}>{skill}</span>
      <span className={styles.value}>
        <span className={styles.pct}>{Math.round(support * 100)}%</span>
        {count != null && total ? (
          <span className={styles.denom}>
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
    </Link>
  );
}
