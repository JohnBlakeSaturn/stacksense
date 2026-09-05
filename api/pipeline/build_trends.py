"""
Per-technology adoption trends from the Stack Overflow survey.

The existing stack_scores_per_stack_year.csv works at the level of ten broad
stacks (Web, AI/ML, Cloud) -- too coarse to re-rank recommendations, since it
can't say Rust is rising while PHP falls when both sit in the same category.
This extracts a series per individual technology instead, at graph-node
granularity.

Three properties of the source data drive the design:

  Respondent counts swing by 2.7x across years (83k, 38k, 88k, 60k, 32k), so
  only percentages are comparable, never raw frequencies.

  Answer options appear and disappear across years. A technology missing from
  a year almost always means the survey didn't ask about it, not that
  adoption fell to zero, so gaps are left as gaps and the number of observed
  years is reported alongside every trend.

  Desire/admire data only exists from 2023, so it's kept separate from the
  adoption series rather than merged into one score.

This measures developer sentiment among survey respondents, not employer
demand -- that's what the job-posting graph is for.

Usage:
    python build_trends.py --archive path/to/packages/archive
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

YEARS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]
LEGACY_YEARS = {"2019", "2020"}   # nested SubSections layout

TECH_BLOCKS = {
    "Language": "Language",
    "Database": "Database",
    "Platform": "Platform",
    "Webframe": "WebFramework",
    "Embedded": "Embedded",
    "MiscTech": "Library/Framework",
    "ToolsTech": "Tool",
    "NEWCollabTools": "IDE",
    "DevEnvs": "IDE",
    "OpSys": "OS",
    "VersionControlSystem": "Tool",
    "AISearchDev": "AITool",
    "AIDev": "AITool",
    "AISearch": "AITool",
    "AIModels": "AIModel",
    "OfficeStackAsync": "Collaboration",
    "OfficeStackSync": "Collaboration",
}

MIN_YEARS = 3   # below this a slope isn't worth reporting


def normalize(name: str) -> str:
    """Same key as build_vocab.normalize, so survey labels collapse the way
    the graph vocabulary does."""
    s = name.strip().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9+#./ ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ", "").rstrip(".")


# Cross-year renames. Without these, "AWS" and "Amazon Web Services (AWS)"
# become two half-length series, which reads as a spurious decline.
MERGE = {
    "amazonwebservices": "aws",
    "googlecloudplatform": "googlecloud",
    "microsoftazure": "azure",
    "linodenowakamai": "linode",
    "ibmcloudorwatson": "ibmcloud",
    "jupyternb/jupyterlab": "jupyter",
    "jupyternotebook/jupyterlab": "jupyter",
    "ipython/jupyter": "jupyter",
    "windowssubsystemforlinux": "wsl",
    "linuxnonwsl": "linux",
    "otherlinuxbased": "linux",
    "linuxbased": "linux",
    "visualstudiocode": "vscode",
    "bash/shell/powershell": "bash/shell",
    "torch/pytorch": "pytorch",
    "reactjs": "react",
    "vuejs": "vue",
    "nodejs": "node.js",
    "angularjs": "angular.js",
}


def canon_key(name: str) -> str:
    k = normalize(name)
    return MERGE.get(k, k)


def load_legacy_year(path: Path) -> dict[str, float]:
    """2019/2020 nest under SubSections -> GraphCollections -> Graphs -> Data,
    and report percentages on a 0-100 scale."""
    data = json.loads(path.read_text())
    out: dict[str, float] = {}
    for section in data.get("SubSections", []):
        title = section.get("Title", "")
        if "Popular" not in title and "Environments" not in title:
            continue
        for collection in section.get("GraphCollections", []):
            for graph in collection.get("Graphs", []):
                if graph.get("Title") != "All Respondents":
                    continue
                for tech, pct in (graph.get("Data") or {}).items():
                    try:
                        out[tech] = float(pct) / 100.0
                    except (TypeError, ValueError):
                        continue
    return out


def load_series(archive: Path) -> tuple[dict, dict, dict]:
    adoption: dict[str, dict[str, float]] = defaultdict(dict)
    category: dict[str, str] = {}
    offered: dict[str, set[str]] = defaultdict(set)
    respondents: dict[str, int] = {}
    display: dict[str, str] = {}

    for year in YEARS:
        path = archive / year / "json" / "technology.json"
        if not path.exists():
            print(f"  skip {year} (no technology.json)")
            continue

        if year in LEGACY_YEARS:
            for tech, pct in load_legacy_year(path).items():
                key = canon_key(tech)
                if not key:
                    continue
                adoption[key][year] = pct
                offered[key].add(year)
                display.setdefault(key, tech)
            continue

        data = json.loads(path.read_text())

        for block, cat in TECH_BLOCKS.items():
            ds = data.get(block, {}).get("datasets", {})
            if block not in ds:
                continue
            rows = ds[block]
            respondents[year] = max(respondents.get(year, 0),
                                    rows.get("total_respondents", 0) or 0)
            for row in rows.get("data", []):
                if not isinstance(row, dict):
                    continue
                name = (row.get("response") or "").strip()
                pct = row.get("percent")
                if not name or pct is None:
                    continue
                key = canon_key(name)
                if not key:
                    continue
                # a technology can appear in two blocks one year; keep the
                # larger share rather than letting order decide
                adoption[key][year] = max(adoption[key].get(year, 0.0), float(pct))
                offered[key].add(year)
                category.setdefault(key, cat)
                display.setdefault(key, name)

    named_adoption = {display.get(k, k): v for k, v in adoption.items()}
    named_category = {display.get(k, k): v for k, v in category.items()}
    return named_adoption, named_category, respondents


def load_desire(archive: Path) -> dict[str, dict[str, float]]:
    """Desired-to-work-with share, available from 2023 only."""
    desire: dict[str, dict[str, float]] = defaultdict(dict)
    for year in YEARS:
        path = archive / year / "json" / "technology.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for block in [k for k in data if k.startswith("DA_")]:
            for name, rows in data[block].get("datasets", {}).items():
                for row in rows.get("data", []):
                    if not isinstance(row, dict):
                        continue
                    tech = (row.get("response") or "").strip()
                    pct = row.get("percent1")   # frequency1/percent1 = desired share
                    if tech and pct is not None:
                        desire[canon_key(tech)][year] = float(pct)
    return desire


def fit_trend(series: dict[str, float]) -> dict:
    """Least-squares slope over observed years plus first-to-last change.
    Gaps are skipped, not interpolated -- an absent year usually means the
    option wasn't offered, and interpolating would invent a trend."""
    years = sorted(series)
    if len(years) < 2:
        return {
            "n_years": len(years),
            "slope": None,
            "change": None,
            "r2": None,
            "latest": round(float(series[years[0]]), 4) if years else None,
            "first_year": years[0] if years else None,
            "last_year": years[-1] if years else None,
        }

    x = np.array([int(y) for y in years], dtype=float)
    y = np.array([series[k] for k in years], dtype=float)
    slope, intercept = np.polyfit(x, y, 1)

    first, last = y[0], y[-1]
    change = (last - first) / first if first > 0 else None

    pred = slope * x + intercept
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None

    return {
        "n_years": len(years),
        "first_year": years[0],
        "last_year": years[-1],
        "slope": round(float(slope), 6),
        "change": round(float(change), 4) if change is not None else None,
        # r2 on three points is close to meaningless, informative from four up
        "r2": round(r2, 3) if r2 is not None else None,
        "r2_meaningful": len(years) >= 4,
        "latest": round(float(last), 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--vocab", type=Path, default=Path("vocab/final_vocab.json"))
    ap.add_argument("--out", type=Path, default=Path("insights/trends.json"))
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    adoption, category, respondents = load_series(args.archive)
    desire = load_desire(args.archive)
    print("respondents per year:", {y: f"{n:,}" for y, n in sorted(respondents.items())})
    print(f"technologies with an adoption series: {len(adoption):,}")
    print(f"technologies with desire data (2023+): {len(desire):,}\n")

    out = {}
    for tech, series in adoption.items():
        entry = fit_trend(series)
        entry["category"] = category.get(tech)
        entry["series"] = {y: round(v, 4) for y, v in sorted(series.items())}
        dk = canon_key(tech)
        if dk in desire:
            entry["desire"] = {y: round(v, 4) for y, v in sorted(desire[dk].items())}
            latest = sorted(desire[dk])[-1]
            # want minus used: positive means more people want it than use it
            if latest in series:
                entry["desire_gap"] = round(desire[dk][latest] - series[latest], 4)
        out[tech] = entry

    matched = 0
    if args.vocab.exists():
        vocab = json.loads(args.vocab.read_text())
        names = {e["canonical"] for e in vocab}
        for tech in out:
            out[tech]["in_graph"] = tech in names
        matched = sum(1 for t in out if out[t]["in_graph"])
        print(f"technologies also present as graph nodes: {matched:,} of {len(out):,}")
        print("  (the rest are survey options that job postings rarely mention)\n")

    args.out.write_text(json.dumps(out, indent=1))
    print(f"wrote {args.out}\n")

    solid = {t: e for t, e in out.items()
             if e["n_years"] >= MIN_YEARS and e["slope"] is not None
             and e["latest"] >= 0.01}

    print(f"--- rising fastest (>= {MIN_YEARS} years, >= 1% latest adoption) ---")
    for tech, e in sorted(solid.items(), key=lambda kv: -kv[1]["slope"])[:15]:
        print(f"  {e['slope']:>+8.4f}/yr  {e['latest']:>6.1%} now  "
              f"r2 {e['r2'] if e['r2'] is not None else float('nan'):>5.2f}  "
              f"{e['n_years']}y  {tech}")

    print(f"\n--- declining fastest ---")
    for tech, e in sorted(solid.items(), key=lambda kv: kv[1]["slope"])[:15]:
        print(f"  {e['slope']:>+8.4f}/yr  {e['latest']:>6.1%} now  "
              f"r2 {e['r2'] if e['r2'] is not None else float('nan'):>5.2f}  "
              f"{e['n_years']}y  {tech}")

    gaps = {t: e for t, e in out.items() if "desire_gap" in e and e["latest"] >= 0.01}
    print("\n--- most wanted relative to current use (desire minus adoption) ---")
    for tech, e in sorted(gaps.items(), key=lambda kv: -kv[1]["desire_gap"])[:12]:
        print(f"  {e['desire_gap']:>+7.1%}  used {e['latest']:>6.1%}  {tech}")

    # If most technologies move the same direction at once, a shift in who
    # answered the survey is likelier than a shift in what developers use --
    # respondent counts here run 83k, 38k, 88k, 60k, 32k.
    slopes = [e["slope"] for e in solid.values() if e["slope"] is not None]
    if slopes:
        arr = np.array(slopes)
        share_down = float((arr < 0).mean())
        print("\n--- composition check ---")
        print(f"  {len(arr):,} technologies with a usable series")
        print(f"  median slope {np.median(arr):+.5f}/yr, {share_down:.0%} declining")
        if share_down > 0.6 or share_down < 0.4:
            print("  WARNING: the direction is lopsided. Respondent counts vary from")
            print("  83k to 32k across these years, so a shared drift more likely")
            print("  reflects who answered than what changed. Prefer rank-based")
            print("  trends below over raw percentage change.")

    # Rank within year is robust to sample size/composition shifts, since it
    # only asks whether a technology moved relative to its peers.
    per_year = defaultdict(list)
    for tech, e in out.items():
        for y, v in e.get("series", {}).items():
            per_year[y].append((v, tech))
    ranks: dict[str, dict[str, float]] = defaultdict(dict)
    for y, rows in per_year.items():
        rows.sort(reverse=True)
        n = len(rows)
        for i, (_, tech) in enumerate(rows):
            ranks[tech][y] = 1.0 - i / max(n - 1, 1)   # 1.0 = most adopted

    rank_trend = {}
    for tech, series in ranks.items():
        if len(series) < MIN_YEARS:
            continue
        ys = sorted(series)
        x = np.array([int(y) for y in ys], dtype=float)
        v = np.array([series[y] for y in ys], dtype=float)
        rank_trend[tech] = float(np.polyfit(x, v, 1)[0])
        out[tech]["rank_series"] = {y: round(series[y], 4) for y in ys}
        out[tech]["rank_slope"] = round(rank_trend[tech], 6)

    print("\n--- rank-based trend (robust to composition shift) ---")
    print("  rising in relative standing:")
    for tech, s in sorted(rank_trend.items(), key=lambda kv: -kv[1])[:12]:
        print(f"    {s:>+8.4f}/yr  {out[tech].get('latest', 0):>6.1%} now  {tech}")
    print("  falling in relative standing:")
    for tech, s in sorted(rank_trend.items(), key=lambda kv: kv[1])[:12]:
        print(f"    {s:>+8.4f}/yr  {out[tech].get('latest', 0):>6.1%} now  {tech}")

    args.out.write_text(json.dumps(out, indent=1))

    print("\n--- shortest series (treat any trend here with suspicion) ---")
    short = [(t, e) for t, e in out.items() if e["n_years"] <= 2]
    print(f"  {len(short)} technologies observed in 2 years or fewer, e.g. "
          + ", ".join(t for t, _ in short[:10]))


if __name__ == "__main__":
    main()
