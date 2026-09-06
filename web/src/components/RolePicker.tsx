import Link from "next/link";
import styles from "./RolePicker.module.css";
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
    <div className={styles.grid}>
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
                className={styles.role}
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

    </div>
  );
}
