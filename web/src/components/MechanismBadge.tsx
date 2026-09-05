export default function MechanismBadge({
  predicted = false,
}: {
  predicted?: boolean;
}) {
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 12,
        fontWeight: 700,
        color: predicted ? "var(--quiet)" : "var(--graph)",
        border: `1px solid ${predicted ? "var(--rule)" : "var(--graph-dim)"}`,
        padding: "3px 7px",
        borderRadius: 2,
      }}
    >
      {predicted ? "Predicted" : "From postings"}
    </span>
  );
}
