import Link from "next/link";
import type { Role } from "@/lib/api";
const families = [
  {
    name: "Build software",
    keys: [
      "Software",
      "Front",
      "Back",
      "Full",
      "Mobile",
      "Embedded",
      "QA",
      "Test",
    ],
  },
  { name: "Work with data", keys: ["Data", "AI", "ML", "Analyst"] },
  {
    name: "Run systems",
    keys: [
      "Network",
      "System",
      "DevOps",
      "Security",
      "Database",
      "Reliability",
      "Cloud",
    ],
  },
  { name: "Design and lead", keys: ["Architect", "Manager"] },
];
export default function RolePicker({ roles }: { roles: Role[] }) {
  const used = new Set<string>();
  return (
    <div className="role-grid">
      {families.map((f) => {
        const group = roles.filter(
          (r) => !used.has(r.name) && f.keys.some((k) => r.name.includes(k)),
        );
        group.forEach((r) => used.add(r.name));
        return (
          <section key={f.name}>
            <h2 className="serif">{f.name}</h2>
            {group.map((r) => (
              <Link
                className="role"
                href={`/roles/${encodeURIComponent(r.name)}`}
                key={r.name}
              >
                <span>{r.name}</span>
                <strong>{r.postings.toLocaleString()}</strong>
              </Link>
            ))}
          </section>
        );
      })}
      <style jsx>{`
        .role-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 46px 72px;
        }
        .role-grid h2 {
          font-size: 24px;
          font-weight: 500;
          border-bottom: 1px solid var(--ink);
          padding-bottom: 10px;
        }
        .role {
          display: flex;
          justify-content: space-between;
          gap: 20px;
          padding: 10px 0;
          border-bottom: 1px solid var(--rule);
        }
        .role:hover span {
          color: var(--graph);
        }
        .role strong {
          font-size: 14px;
        }
        @media (max-width: 680px) {
          .role-grid {
            grid-template-columns: 1fr;
            gap: 28px;
          }
        }
      `}</style>
    </div>
  );
}
