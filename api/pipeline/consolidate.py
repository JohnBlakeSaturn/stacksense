"""
Consolidate the canonical vocabulary.

The LLM pass normalised spelling but not concepts, so it proposed ~13k
canonical terms including duplicates (".NET", ".NET/C#", ".NET 6"; "Agile",
"Agile Development"). This step:

  1. keeps survey terms unconditionally
  2. keeps LLM-proposed terms at or above a mention threshold (or employer
     spread, for terms too rare in volume but used by many distinct companies)
  3. embeds the surviving names and agglomeratively clusters them
  4. merges each cluster into its highest-frequency member

Output: final_vocab.json, final_mapping.json, merges.txt.

Review merges.txt by hand -- clustering will occasionally merge two genuinely
distinct technologies.

Usage:
    python consolidate.py --min-mentions 20 --threshold 0.86
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

EMBED_MODEL = "all-MiniLM-L6-v2"

# Pairs that embed close on string similarity but must never merge.
NEVER_MERGE = [
    {"java", "javascript"}, {"c", "c#"}, {"c", "c++"}, {"c#", "c++"},
    {"r", "ruby"}, {"go", "golang", "django"}, {"react", "react native"},
    {"angular", "angularjs"}, {"mysql", "postgresql"},
    {"aws", "azure", "google cloud"},
    {"sas", "sass"}, {"swift", "swiftui"}, {"nix", "nixos"},
    {"ada", "adas"}, {"jax", "jaxb"}, {"nat", "nats"},
    {"couchbase", "couch db", "couchdb"},

    {"frontend frameworks", "backend frameworks"},
    {"frontend development", "backend development"},
    {"front-end development", "back-end development"},
    {"high-level design", "low-level design"},

    {"analytics", "google analytics"},
    {"cloud storage", "google cloud storage"},
    {"command line", "linux command line"},
    {"github", "git/github"}, {"gitlab", "gitlab ci"},
    {"rollout", "rollup"},

    {"iec 61850", "iec 61131"},
    {"nist sp 800-53", "nist sp 800-171", "nist sp 800-37"},
    {"arp4754", "arp4754a", "arp4761"},
    {"ethernet", "ethernet/ip"}, {"tcp", "tcp/ip"}, {"tacacs", "tacacs+"},
    {"software-defined networking", "software-defined wide area networking"},
    {"ros", "ros 2"},

    {"schema design", "schematic design"},
    {"threat modeling", "threat analysis"},
    {"computer architecture", "hardware architecture"},

    {"unit testing", "integration testing", "system testing"},

    {"mvc", "asp.net mvc"},
    {"database administration", "database management system",
     "database management systems", "dbms"},
    {"application security", "security applications"},
]

DISPLAY_OVERRIDE = {
    "Linux (non-WSL)": "Linux",
    "Amazon Web Services (AWS)": "AWS",
    "Bash/Shell (all shells)": "Bash/Shell",
    "Slack (public)": "Slack",
    ".NET (5+)": ".NET",
    ".NET Framework (1.0 - 4.8)": ".NET Framework",
    "APIs": "API",
}


def blocked(a: str, b: str) -> bool:
    la, lb = a.lower(), b.lower()
    return any(la in group and lb in group and la != lb for group in NEVER_MERGE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", type=Path, default=Path("vocab"))
    ap.add_argument("--survey-vocab", type=Path, default=Path("canonical_vocab.json"))
    ap.add_argument("--min-mentions", type=int, default=20)
    ap.add_argument("--min-companies", type=int, default=8,
                    help="alternative admission route for terms below the "
                         "mention floor but used by this many distinct employers")
    ap.add_argument("--postings", type=Path, default=Path("vocab/tech_postings.parquet"))
    ap.add_argument("--threshold", type=float, default=0.86,
                    help="cosine similarity above which two names merge")
    args = ap.parse_args()

    survey = json.loads(args.survey_vocab.read_text())
    survey_names = {e["canonical"] for e in survey}
    survey_cat = {e["canonical"]: e["category"] for e in survey}

    classified = json.loads((args.in_dir / "llm_classified.json").read_text())
    base_mapping = json.loads((args.in_dir / "skill_mapping.json").read_text())

    raw_to_canon: dict[str, str] = {}
    mentions: Counter = Counter()
    cat_of: dict[str, str] = {}

    for row in classified:
        if not row["category"].startswith("tech") or not row["canonical"]:
            continue
        canon = row["canonical"].strip()
        raw_to_canon[row["raw"]] = canon
        mentions[canon] += row["count"]
        cat_of.setdefault(canon, row["category"])

    for raw, m in base_mapping.items():
        raw_to_canon[raw] = m["canonical"]
        mentions[m["canonical"]] += m["count"]
        cat_of.setdefault(m["canonical"], "tech-product")

    print(f"proposed canonical terms      : {len(mentions):>8,}")

    # Distinct employers using a term separates a real technology from one
    # company's internal vocabulary better than raw volume: "Gate Automation"
    # and "Employee Center Pro" appear 11-15 times each from a single employer,
    # while spaCy and WebSocket sit at the same volume spread across many.
    company_spread: Counter = Counter()
    if args.postings.exists():
        import pandas as pd

        postings = pd.read_parquet(args.postings)
        seen: dict[str, set] = defaultdict(set)
        for company, skills in zip(postings["company"], postings["job_skills"]):
            for part in str(skills).split(","):
                canon = raw_to_canon.get(part.strip())
                if canon:
                    seen[canon].add(company)
        company_spread = Counter({k: len(v) for k, v in seen.items()})
        print(f"company spread computed for {len(company_spread):,} terms")
    else:
        print(f"note: {args.postings} not found, falling back to the mention floor alone")

    keep = {
        name for name, n in mentions.items()
        if name in survey_names
        or n >= args.min_mentions
        or (company_spread.get(name, 0) >= args.min_companies
            and cat_of.get(name) == "tech-product")
    }
    via_spread = {
        name for name in keep
        if name not in survey_names
        and mentions[name] < args.min_mentions
        and company_spread.get(name, 0) >= args.min_companies
    }
    if via_spread:
        print(f"{len(via_spread):,} terms admitted on employer spread alone, e.g. "
              + ", ".join(sorted(via_spread, key=lambda n: -company_spread[n])[:12]))
    dropped_mentions = sum(n for name, n in mentions.items() if name not in keep)
    print(f"kept (survey or >={args.min_mentions} mentions) : {len(keep):>8,}")
    print(f"dropped                       : {len(mentions) - len(keep):>8,} terms "
          f"({dropped_mentions:,} mentions)\n")

    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import AgglomerativeClustering

    names = sorted(keep)
    print(f"embedding {len(names):,} names...")
    model = SentenceTransformer(EMBED_MODEL)
    vecs = model.encode(names, normalize_embeddings=True, batch_size=256,
                        show_progress_bar=True)

    print("clustering...")
    labels = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=1.0 - args.threshold,
        metric="cosine",
        linkage="average",
    ).fit_predict(vecs)

    clusters: dict[int, list[str]] = defaultdict(list)
    for name, label in zip(names, labels):
        clusters[label].append(name)

    merge_to: dict[str, str] = {}
    merge_log: list[str] = []

    for members in clusters.values():
        if len(members) == 1:
            merge_to[members[0]] = members[0]
            continue

        protected = {m for m in members if any(blocked(m, o) for o in members if o != m)}
        mergeable = [m for m in members if m not in protected]
        for m in protected:
            merge_to[m] = m

        if not mergeable:
            continue

        head = sorted(
            mergeable,
            key=lambda n: (n in survey_names, mentions[n], -len(n)),
            reverse=True,
        )[0]
        for m in mergeable:
            merge_to[m] = head
        if len(mergeable) > 1:
            others = [m for m in mergeable if m != head]
            merge_log.append(
                f"{mentions[head]:>7,}  {head}\n" +
                "".join(f"         <- {m}  ({mentions[m]:,})\n" for m in others)
            )

    final_terms = sorted(set(merge_to.values()))
    print(f"\nafter merging                 : {len(final_terms):>8,} terms")
    print(f"merge groups                  : {len(merge_log):>8,}")

    def display(name: str) -> str:
        return DISPLAY_OVERRIDE.get(name, name)

    final_mentions: Counter = Counter()
    final_mapping: dict[str, str] = {}
    for raw, canon in raw_to_canon.items():
        head = merge_to.get(canon)
        if head:
            final_mapping[raw] = display(head)
            final_mentions[display(head)] += 1

    variant_counts = Counter(final_mapping.values())
    vocab = [
        {
            "canonical": display(t),
            "category": survey_cat.get(t, cat_of.get(t, "tech-product")),
            "in_survey": t in survey_names,
            "mentions": mentions[t],
            "raw_variants": variant_counts.get(display(t), 0),
        }
        for t in final_terms
    ]
    vocab.sort(key=lambda e: -e["mentions"])

    (args.in_dir / "final_vocab.json").write_text(json.dumps(vocab, indent=1))
    (args.in_dir / "final_mapping.json").write_text(json.dumps(final_mapping, indent=1))
    (args.in_dir / "merges.txt").write_text("\n".join(merge_log))

    covered = sum(mentions[t] for t in final_terms)
    print(f"\nraw strings mapped            : {len(final_mapping):>8,}")
    print(f"mentions covered              : {covered:>8,}")
    print(f"\nwrote {args.in_dir}/final_vocab.json")
    print(f"wrote {args.in_dir}/final_mapping.json")
    print(f"wrote {args.in_dir}/merges.txt   <- review this by hand")

    print("\n--- top 30 final terms ---")
    for e in vocab[:30]:
        flag = "S" if e["in_survey"] else " "
        print(f"  {flag} {e['mentions']:>7,}  {e['canonical']}")

    print("\n--- 15 sample merges (full list in merges.txt) ---")
    for block in merge_log[:15]:
        print(block, end="")


if __name__ == "__main__":
    main()
