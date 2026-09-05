import Link from "next/link";
export default function Footer() {
  return (
    <footer
      className="rule-top"
      style={{ marginTop: 80, padding: "34px 0 44px" }}
    >
      <div
        className="shell"
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 24,
          flexWrap: "wrap",
        }}
      >
        <div>
          <strong>StackSense</strong>
          <div className="quiet" style={{ fontSize: 14 }}>
            Evidence from postings, made useful.
          </div>
        </div>
        <div style={{ display: "flex", gap: 22, fontSize: 14 }}>
          <Link href="/roles">Roles</Link>
          <Link href="/trends">Trends</Link>
          <Link href="/resume">Resume</Link>
        </div>
      </div>
    </footer>
  );
}
