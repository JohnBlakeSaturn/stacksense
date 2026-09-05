"use client";
import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Menu, X } from "lucide-react";
const links = [
  { label: "Skills", href: "/skills/Docker" },
  { label: "Roles", href: "/roles" },
  { label: "Trends", href: "/trends" },
  { label: "Resume", href: "/resume" },
];
export default function Navbar() {
  const [open, setOpen] = useState(false);
  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 30,
        background: "rgba(251,250,247,.94)",
        backdropFilter: "blur(10px)",
        borderBottom: "1px solid var(--rule)",
      }}
    >
      <div
        className="shell"
        style={{
          height: 68,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Link
          href="/"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 9,
            fontWeight: 700,
            fontSize: 20,
          }}
        >
          <Image src="/test2.svg" alt="" width={27} height={27} />
          Stack
          <span style={{ color: "var(--graph)", marginLeft: -9 }}>Sense</span>
        </Link>
        <nav
          className="desktop-nav"
          style={{ display: "flex", gap: 28, alignItems: "center" }}
        >
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              style={{ fontSize: 14, fontWeight: 500 }}
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <button
          className="mobile-nav"
          aria-label="Toggle navigation"
          onClick={() => setOpen(!open)}
          style={{ border: 0, background: "none", padding: 8 }}
        >
          {open ? <X /> : <Menu />}
        </button>
      </div>
      {open && (
        <nav className="mobile-menu shell">
          {links.map((l) => (
            <Link onClick={() => setOpen(false)} key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
        </nav>
      )}
      <style jsx>{`
        .mobile-nav,
        .mobile-menu {
          display: none;
        }
        @media (max-width: 680px) {
          .desktop-nav {
            display: none !important;
          }
          .mobile-nav {
            display: block;
          }
          .mobile-menu {
            display: grid;
            padding: 12px 0 20px;
            gap: 8px;
          }
          .mobile-menu a {
            padding: 8px 0;
            border-bottom: 1px solid var(--rule);
          }
        }
      `}</style>
    </header>
  );
}
