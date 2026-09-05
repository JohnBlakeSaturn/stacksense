"""
Derive role and seniority from job titles.

Run and inspect this before building the heterogeneous graph -- if role
coverage or assignment quality is off, everything built on top inherits it.

Role vocabulary is seeded from the Stack Overflow survey's DevType field
(externally curated, same provenance argument as the skill taxonomy). DevType
entries are descriptions ("Developer, back-end"), not titles, so each maps to
a set of title patterns.

Seniority comes from the title text, not the dataset's own fields -- job_level
is 89% one value and job_type is 99% "Onsite", so neither carries signal.

Outputs graph/postings_roles.parquet and prints coverage diagnostics.

Usage:
    python extract_roles.py
    python extract_roles.py --show-unmatched 60
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

import pandas as pd

# Ordered: first match wins, so specific roles must precede general ones (a
# "Machine Learning Engineer" shouldn't fall through to "Software Engineer").
ROLE_PATTERNS: list[tuple[str, str]] = [
    ("AI/ML Engineer",
     r"machine learning|\bml engineer|\bmlops\b|\bai engineer|deep learning"
     r"|applied scientist|\bnlp\b|computer vision|generative ai|\bllm\b"
     r"|research scientist|ai/ml"),
    ("Data Scientist",
     r"data scientist|decision scientist"),
    ("Data Engineer",
     r"data engineer|etl (developer|engineer)|analytics engineer|big data"
     r"|data pipeline|data platform engineer"),
    ("Data or Business Analyst",
     r"data analyst|business intelligence|\bbi (analyst|developer)|reporting analyst"
     r"|business analyst"),
    ("Site Reliability Engineer",
     r"site reliability|\bsre\b|production engineer"),
    ("DevOps Engineer",
     r"devops|devsecops|platform engineer|release engineer|build engineer"
     r"|infrastructure automation"),
    ("Cloud Infrastructure Engineer",
     r"cloud engineer|cloud infrastructure|cloud solution|cloud operations"
     r"|infrastructure engineer|\baws engineer|\bazure engineer"),
    ("Security Professional",
     r"security engineer|cyber ?security|infosec|application security|penetration test"
     r"|incident response|security analyst|security operations|\bsoc analyst"),
    ("Database Administrator",
     r"database administrator|\bdba\b|database engineer|database developer"),
    ("Developer, Mobile",
     r"\bmobile\b|\bandroid\b|\bios\b|react native|flutter developer|swiftui"),
    ("Developer, Embedded",
     r"\bembedded\b|\bfirmware\b|device driver|\brtos\b"),
    ("Developer, Game or Graphics",
     r"game (developer|engineer|programmer|play)|graphics (developer|engineer|programmer)"
     r"|unity developer|unreal engine"),
    ("Developer, QA or Test",
     # narrowed: bare "automation engineer"/"test engineer" caught network
     # automation and thermal-vacuum testing, not QA
     r"\bqa\b|quality assurance|\bsdet\b|test automation|automation test"
     r"|software test|\btester\b|test engineer.*softwar|software.*test engineer"),
    ("Developer, Front-end",
     r"front[- ]?end|\bui developer|\bui engineer|web developer|react developer"
     r"|angular developer|vue developer"),
    ("Developer, Back-end",
     r"back[- ]?end|server[- ]side"),
    ("Developer, Full-stack",
     r"full[- ]?stack"),
    ("Network Engineer",
     r"network (engineer|architect|administrator|automation|operations)|\bddi\b"
     r"|routing and switching|\bnoc\b"),
    ("System Administrator",
     r"system(s)? administrator|sysadmin|windows (engineer|administrator)"
     r"|linux (engineer|administrator)"),
    ("Engineering Manager",
     r"engineering manager|development manager|technical lead|tech lead|team lead"
     r"|\bhead of engineering|director of engineering"),
    ("Developer, Desktop or Enterprise",
     r"salesforce|servicenow|\bsap\b|sharepoint|sailpoint|dynamics 365"
     r"|erp (developer|consultant)|\bpega\b|\bepic\b"),
    ("Architect, Software or Solutions",
     # placed after domain roles: "Systems Architect, Cybersecurity" is a
     # security role that happens to be senior
     r"\barchitect\b"),
    ("Software Engineer",   # catch-all, must stay last
     r"software (engineer|developer|architect)|programmer|application developer"
     r"|development engineer|\bsde\b|product engineer|\bdeveloper\b"
     r"|software.*engineer|engineer.*software|\bengineer\b"),
]

# Titles reaching the catch-all that aren't software roles -- the upstream
# tech-title filter is permissive about the word "engineer".
NON_SOFTWARE = re.compile(
    r"plant |turbomachinery|\bfire &|\bhvac\b|mechanical|facilities|manufacturing"
    r"|thermal|vacuum|chemical|civil |structural|aerospace|automotive|electrical"
    r"|biomedical|petroleum|\bfield service|maintenance (technician|engineer)"
    r"|sales engineer|account (executive|manager)|technical writer|recruiter",
    re.I,
)

# Most senior first, so "Senior Staff" resolves to Staff.
SENIORITY_PATTERNS: list[tuple[str, str]] = [
    # "architect"/"manager" were previously here; both are role markers rather
    # than rungs, and forced every architect to principal, every manager to lead.
    ("principal", r"\bprincipal\b|\bdistinguished\b|\bfellow\b|\bchief\b|\bvp\b"),
    ("staff",     r"\bstaff\b"),
    ("lead",      r"\blead\b|\bleading\b|\bhead of\b"),
    ("senior",    r"\bsenior\b|\bsr\.?\b|\bexperienced\b"),
    ("junior",    r"\bjunior\b|\bjr\.?\b|\bentry[- ]level\b|\bgraduate\b"
                  r"|\bassociate\b|\bintern\b|\btrainee\b|\bapprentice\b"),
]

MIN_POSTINGS = 200   # roles below this have too few postings for stable edges


def assign_role(title: str) -> str | None:
    if NON_SOFTWARE.search(title):
        return None
    t = title.lower()
    for role, pattern in ROLE_PATTERNS:
        if re.search(pattern, t):
            return role
    return None


def assign_seniority(title: str) -> str:
    t = title.lower()
    for level, pattern in SENIORITY_PATTERNS:
        if re.search(pattern, t):
            return level
    return "mid"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--postings", type=Path, default=Path("graph/postings_clean.parquet"))
    ap.add_argument("--out-dir", type=Path, default=Path("insights"))
    ap.add_argument("--show-unmatched", type=int, default=40)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(args.postings)
    print(f"postings {len(df):,}\n")

    df["role"] = df["job_title"].fillna("").map(assign_role)
    df["seniority"] = df["job_title"].fillna("").map(assign_seniority)

    matched = df["role"].notna()
    print(f"role assigned      {matched.sum():>8,}  ({matched.mean():.1%})")
    print(f"unassigned         {(~matched).sum():>8,}\n")

    print("--- role distribution ---")
    counts = df.loc[matched, "role"].value_counts()
    for role, n in counts.items():
        print(f"  {n:>7,}  {role}")

    print("\n--- seniority distribution ---")
    for level, n in df.loc[matched, "seniority"].value_counts().items():
        print(f"  {n:>7,}  {level}")

    print("\n--- role x seniority (postings per cell) ---")
    pivot = pd.crosstab(df.loc[matched, "role"], df.loc[matched, "seniority"])
    order = [c for c in ["junior", "mid", "senior", "staff", "lead", "principal"]
             if c in pivot.columns]
    print(pivot[order].to_string())

    print("\n--- sample titles per role (check these look right) ---")
    for role in counts.index[:12]:
        sample = df.loc[df["role"] == role, "job_title"].drop_duplicates().head(4).tolist()
        print(f"  {role}")
        for s in sample:
            print(f"      {s}")

    if args.show_unmatched:
        print(f"\n--- top {args.show_unmatched} unassigned titles ---")
        for title, n in df.loc[~matched, "job_title"].value_counts().head(
                args.show_unmatched).items():
            print(f"  {n:>5,}  {title}")

    thin = counts[counts < MIN_POSTINGS]
    if len(thin):
        print(f"\ndropping {len(thin)} roles with <{MIN_POSTINGS} postings "
              "(edge weights would be unstable):")
        print("  " + ", ".join(f"{r} ({n})" for r, n in thin.items()))
        df.loc[df["role"].isin(thin.index), "role"] = None

    kept = df["role"].notna()
    print(f"\nfinal: {kept.sum():,} postings across {df['role'].nunique()} roles "
          f"({kept.mean():.1%} coverage)")

    out = args.out_dir / "postings_roles.parquet"
    df.to_parquet(out, index=False)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
