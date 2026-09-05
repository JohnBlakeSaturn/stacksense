"""
Build a canonical technology vocabulary from Stack Overflow Developer Survey
archives (packages/archive/<year>/json/technology.json, 2021-2025).

Usage:
    python build_vocab.py --archive path/to/packages/archive --out canonical_vocab.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

YEARS = ["2021", "2022", "2023", "2024", "2025"]

# Blocks that enumerate technologies. Excludes sentiment blocks (e.g. 2022's
# "Blockchain", whose responses are Favorable/Unfavorable, not tech names).
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
    "CommPlatform": "Collaboration",
    "SOTags": "Topic",
}

JUNK = re.compile(
    r"^(other|none|i don'?t use|not sure|unsure|indifferent|favorable|unfavorable|"
    r"very favorable|very unfavorable|n/?a)\b",
    re.I,
)

# Cross-year renames normalization can't catch (SO relabelled the option).
MANUAL_MERGE = {
    "amazonwebservices": "aws",
    "googlecloudplatform": "googlecloud",
    "linodenowakamai": "linode",
    "ibmcloudorwatson": "ibmcloud",
    "jupyternb/jupyterlab": "jupyternotebook/jupyterlab",
    "ipython/jupyter": "jupyternotebook/jupyterlab",
    "windowssubsystemforlinux": "wsl",
    "linuxnonwsl": "linux",
    "linuxbased": "linux",
    "otherlinuxbased": "linux",
    "visualstudiocode": "vscode",
}

STRIP_PREFIXES = (
    "apache ", "microsoft ", "google ", "amazon ", "ibm ", "oracle ",
    "gnu ", "the ", "adobe ", "atlassian ",
)

EXTRA_ALIASES = {
    "googlecloud": ["GCP", "Google Cloud Platform"],
    "amazonwebservices": ["AWS", "Amazon AWS"],
    "microsoftazure": ["Azure", "MS Azure"],
    "kubernetes": ["K8s"],
    "postgresql": ["Postgres"],
    "javascript": ["JS"],
    "typescript": ["TS"],
    "microsoftsqlserver": ["SQL Server", "MSSQL", "T-SQL"],
    "visualstudiocode": ["VS Code", "VSCode"],
    "jupyternb/jupyterlab": ["Jupyter", "Jupyter Notebook", "JupyterLab"],
    "html/css": ["HTML", "CSS"],
    "bash/shell": ["Bash", "Shell", "Shell Scripting", "Shell scripting"],
    "node.js": ["Node", "NodeJS"],
    "c#": ["CSharp", "C Sharp"],
    ".net": ["dotnet", ".NET Core"],
    "reactjs": ["React", "React.js"],
    "angular": ["AngularJS", "Angular.js"],
    "vue.js": ["Vue", "VueJS"],
    "linuxnonwsl": ["Linux"],
    "macos": ["Mac OS", "Mac OS X", "OSX"],
    "objectivec": ["Objective C"],
    "ruby": ["Ruby on Rails"],
}

# Generic-word aliases to drop: stripping "Google " from "Google Meet" yields
# "Meet", which would match every posting mentioning meetings.
ALIAS_STOPLIST = {
    "meet", "teams", "chat", "office", "word", "excel", "access", "one", "now",
    "cloud", "code", "test", "build", "make", "go", "r", "c", "spaces", "drive",
    "docs", "notes", "mail", "calendar", "search", "assistant", "studio", "core",
    "framework", "server", "web services", "services", "platform", "engine",
}


def generate_aliases(canonical: str, norm_key: str) -> set[str]:
    out: set[str] = set()
    low = canonical.lower()

    bare = re.sub(r"\(.*?\)", "", canonical).strip()
    if bare and bare != canonical:
        out.add(bare)

    for prefix in STRIP_PREFIXES:
        if low.startswith(prefix):
            out.add(canonical[len(prefix):].strip())

    if "/" in bare and not bare.startswith("."):
        for part in bare.split("/"):
            part = part.strip()
            if len(part) > 1:
                out.add(part)

    out = {a for a in out if a and a.lower() not in ALIAS_STOPLIST and len(a) > 1}
    out.update(EXTRA_ALIASES.get(norm_key, []))
    out.discard(canonical)
    return {a for a in out if a}


def normalize(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9+#./ ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace(" ", "")
    return s.rstrip(".")


def pick_canonical(variants: list[tuple[str, int, str]]) -> str:
    """Prefer the most recent survey year's spelling, then frequency, then
    length, then alphabetical for determinism."""
    return sorted(variants, key=lambda v: (v[2], v[1], len(v[0]), v[0]), reverse=True)[0][0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("canonical_vocab.json"))
    args = ap.parse_args()

    buckets: dict[str, dict] = defaultdict(
        lambda: {"variants": [], "categories": set(), "years": set()}
    )

    for year in YEARS:
        path = args.archive / year / "json" / "technology.json"
        if not path.exists():
            print(f"  skip {year} (no technology.json)")
            continue
        data = json.loads(path.read_text())

        for block, category in TECH_BLOCKS.items():
            if block not in data:
                continue
            datasets = data[block].get("datasets", {})
            if block not in datasets:
                continue
            for row in datasets[block].get("data", []):
                if not isinstance(row, dict):
                    continue
                raw = (row.get("response") or "").strip()
                if not raw or JUNK.match(raw):
                    continue
                key = normalize(raw)
                if not key:
                    continue
                key = MANUAL_MERGE.get(key, key)
                b = buckets[key]
                b["variants"].append((raw, row.get("frequency", 0) or 0, year))
                b["categories"].add(category)
                b["years"].add(year)

    vocab = []
    for key, b in buckets.items():
        canonical = pick_canonical(b["variants"])
        aliases = {v[0] for v in b["variants"]}
        aliases |= generate_aliases(canonical, key)
        aliases = sorted(aliases)
        vocab.append(
            {
                "canonical": canonical,
                "norm_key": key,
                "aliases": aliases,
                "category": sorted(b["categories"])[0]
                if len(b["categories"]) == 1
                else sorted(b["categories"]),
                "years": sorted(b["years"]),
                "max_frequency": max(v[1] for v in b["variants"]),
            }
        )

    vocab.sort(key=lambda e: -e["max_frequency"])
    args.out.write_text(json.dumps(vocab, indent=1))

    raw_total = sum(len(e["aliases"]) for e in vocab)
    print(f"\n{raw_total} raw response strings -> {len(vocab)} canonical terms")
    merged = [e for e in vocab if len(e["aliases"]) > 1]
    print(f"{len(merged)} terms merged from multiple spellings, e.g.:")
    for e in merged[:12]:
        print(f"   {e['canonical']:<28} <- {e['aliases']}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
