"use client";
const levels = ["junior", "mid", "senior", "staff", "lead", "principal"];
export default function SeniorityToggle({
  counts,
  value,
  onChange,
}: {
  counts: Record<string, number>;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        overflowX: "auto",
        borderBottom: "1px solid var(--rule)",
      }}
    >
      {levels.map((l) => {
        const disabled = (counts[l] ?? 0) < 20;
        return (
          <button
            title={
              disabled
                ? `Only ${counts[l] ?? 0} postings — too few for a reliable split`
                : `${counts[l].toLocaleString()} postings`
            }
            disabled={disabled}
            onClick={() => onChange(l)}
            key={l}
            style={{
              flex: 1,
              minWidth: 90,
              border: 0,
              borderBottom:
                value === l
                  ? "3px solid var(--graph)"
                  : "3px solid transparent",
              background: "transparent",
              padding: "14px 8px",
              fontWeight: value === l ? 700 : 400,
              color: disabled ? "var(--rule)" : "var(--ink)",
            }}
          >
            {l}
          </button>
        );
      })}
    </div>
  );
}
