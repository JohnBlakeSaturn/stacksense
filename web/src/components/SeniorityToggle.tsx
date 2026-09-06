"use client";
const levels = ["all", "junior", "mid", "senior", "staff", "lead", "principal"];
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
        const count = l === "all" ? Object.values(counts).reduce((a,b) => a+b,0) : (counts[l] ?? 0);
        const disabled = count < 20;
        return (
          <button
            title={
              disabled
                ? `Only ${count} postings — too few for a reliable split`
                : `${count.toLocaleString()} postings`
            }
            disabled={disabled}
            aria-pressed={value === l}
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
