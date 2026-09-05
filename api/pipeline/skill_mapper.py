"""
Map raw job-posting skill strings onto the canonical SO vocabulary.

1. Filter postings to tech roles by job title.
2. Collect skill strings appearing >= MIN_COUNT times.
3. Match each string in three passes: exact norm_key, known alias, then
   (optional, --embed) cosine similarity against canonical terms.
4. Write the mapping plus unmatched-but-frequent strings for the LLM pass.

Usage:
    python skill_mapper.py --data data --vocab canonical_vocab.json
    python skill_mapper.py --data data --vocab canonical_vocab.json --embed
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

MIN_COUNT = 3
EMBED_THRESHOLD = 0.62
EMBED_MODEL = "all-MiniLM-L6-v2"

INCLUDE = (
    r"(software|data|backend|back-end|frontend|front-end|full ?stack|cloud|devops|platform|"
    r"security|network|systems?|qa|test|automation|machine learning|ml|ai|embedded|mobile|ios|android|web)"
    r"\s+(?:engineer|developer|architect)"
    r"|software developer|programmer|data scientist|data analyst|sre|site reliability"
    r"|database administrator|\bdba\b|web developer|application developer"
    r"|\b(?:php|java|python|javascript|typescript|golang|ruby|scala|kotlin|swift|dotnet|\.net|"
    r"c\+\+|c#|rust|node|react|angular|kubernetes|sailpoint|salesforce|servicenow|sap)\s+"
    r"(?:developer|engineer|architect)"
    r"|software development engineer|development engineer"
    r"|(?:senior|sr\.?|lead|principal|staff|distinguished)\s+(?:developer|programmer)"
    r"|(?:solutions?|technical|principal|enterprise|cloud|application)\s+architect"
    r"|devsecops|mlops|machine learning operations"
    r"|engineering manager|tech lead|technical lead|product engineer"
    r"|(?:research|applied|principal|staff|senior|distinguished)?\s*"
    r"(?:scientist|researcher)\b(?=.*(?:machine learning|\bml\b|\bai\b|nlp|deep learning|"
    r"computer vision|data|software|algorithm))"
    r"|(?:machine learning|\bml\b|\bai\b|nlp|deep learning|computer vision|research)\s+"
    r"(?:scientist|researcher|engineer)"
    r"|applied scientist|research engineer"
    r"|game (developer|engineer|programmer)|graphics (developer|engineer|programmer)"
    r"|unity developer|unreal engine|gameplay (engineer|programmer)"
    r"|system(s)? administrator|sysadmin|linux administrator|windows administrator"
)

EXCLUDE = (
    r"electrical|mechanical|civil|structural|manufactur|geotech|chemical|industrial|"
    r"landscape|hvac|aerospace|automotive|petroleum|mining|marine|nuclear|biomedical|"
    r"field engineer|sales engineer|process engineer|controls engineer|quality engineer|"
    r"project engineer|design engineer|hardware engineer|packaging|"
    r"account executive|account manager|bioinformatician|safety architect|ai training|"
    r"clinical|biolog|chemi|pharma|laboratory|environmental scientist|food scientist|"
    r"soil|materials scientist"
)


def normalize(name: str) -> str:
    """Must match build_vocab.normalize() exactly, or keys won't line up."""
    s = name.strip().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9+#./ ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace(" ", "")
    return s.rstrip(".")


def load_tech_postings(data_dir: Path) -> pd.DataFrame:
    postings = pd.read_csv(data_dir / "linkedin_job_postings.csv")
    skills = pd.read_csv(data_dir / "job_skills.csv")

    title = postings["job_title"].fillna("").str.lower()
    keep = title.str.contains(INCLUDE, regex=True) & ~title.str.contains(EXCLUDE, regex=True)
    tech = postings.loc[keep, ["job_link", "job_title", "company"]]
    merged = tech.merge(skills, on="job_link", how="inner")
    merged = merged[merged["job_skills"].notna()]
    print(f"tech postings with skills : {len(merged):>8,}")
    return merged


def count_skill_strings(postings: pd.DataFrame) -> Counter:
    counts: Counter = Counter()
    for value in postings["job_skills"]:
        counts.update(part.strip() for part in str(value).split(",") if part.strip())
    print(f"unique raw skill strings  : {len(counts):>8,}")
    return counts


def match(counts: Counter, vocab: list[dict], use_embeddings: bool) -> tuple[dict, list]:
    by_norm = {entry["norm_key"]: entry for entry in vocab}
    by_alias = {}
    for entry in vocab:
        for alias in entry["aliases"]:
            by_alias.setdefault(normalize(alias), entry)

    candidates = [(s, n) for s, n in counts.items() if n >= MIN_COUNT]
    print(f"strings with count >= {MIN_COUNT}   : {len(candidates):>8,}\n")

    mapping: dict[str, dict] = {}
    unmatched: list[tuple[str, int]] = []
    stats = Counter()

    for raw, n in candidates:
        key = normalize(raw)
        entry = by_norm.get(key) or by_alias.get(key)
        if entry:
            how = "exact" if key in by_norm else "alias"
            mapping[raw] = {
                "canonical": entry["canonical"],
                "category": entry["category"],
                "method": how,
                "count": n,
            }
            stats[how] += 1
        else:
            unmatched.append((raw, n))

    if use_embeddings and unmatched:
        from sentence_transformers import SentenceTransformer, util

        print(f"embedding {len(unmatched):,} unmatched strings against "
              f"{len(vocab)} canonical terms...")
        model = SentenceTransformer(EMBED_MODEL)
        canon_names = [e["canonical"] for e in vocab]
        canon_vecs = model.encode(canon_names, convert_to_tensor=True,
                                  normalize_embeddings=True, batch_size=128,
                                  show_progress_bar=True)
        raw_names = [r for r, _ in unmatched]
        raw_vecs = model.encode(raw_names, convert_to_tensor=True,
                                normalize_embeddings=True, batch_size=128,
                                show_progress_bar=True)

        sims = util.cos_sim(raw_vecs, canon_vecs)
        best_scores, best_idx = sims.max(dim=1)

        still_unmatched = []
        for (raw, n), score, idx in zip(unmatched, best_scores.tolist(), best_idx.tolist()):
            if score >= EMBED_THRESHOLD:
                entry = vocab[idx]
                mapping[raw] = {
                    "canonical": entry["canonical"],
                    "category": entry["category"],
                    "method": "embedding",
                    "score": round(score, 3),
                    "count": n,
                }
                stats["embedding"] += 1
            else:
                still_unmatched.append((raw, n))
        unmatched = still_unmatched

    print("\nmatches by method:")
    for method, n in stats.most_common():
        print(f"  {method:<10} {n:>7,}")
    print(f"  {'unmatched':<10} {len(unmatched):>7,}")

    coverage = sum(m["count"] for m in mapping.values())
    total = sum(n for _, n in candidates)
    print(f"\ntoken coverage: {coverage:,}/{total:,} ({coverage / total:.1%}) "
          "of skill mentions map to a canonical term")

    return mapping, sorted(unmatched, key=lambda x: -x[1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--vocab", type=Path, default=Path("canonical_vocab.json"))
    ap.add_argument("--out-dir", type=Path, default=Path("vocab"))
    ap.add_argument("--embed", action="store_true", help="run the embedding match pass")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    vocab = json.loads(args.vocab.read_text())
    print(f"canonical vocabulary      : {len(vocab):>8,} terms\n")

    postings = load_tech_postings(args.data)
    counts = count_skill_strings(postings)
    mapping, unmatched = match(counts, vocab, args.embed)

    (args.out_dir / "skill_mapping.json").write_text(json.dumps(mapping, indent=1))
    (args.out_dir / "unmatched.json").write_text(
        json.dumps([{"raw": r, "count": n} for r, n in unmatched], indent=1)
    )
    postings.to_parquet(args.out_dir / "tech_postings.parquet", index=False)

    print(f"\nwrote {args.out_dir}/skill_mapping.json")
    print(f"wrote {args.out_dir}/unmatched.json")
    print(f"wrote {args.out_dir}/tech_postings.parquet")

    print("\n--- top 40 unmatched by frequency (candidates for the LLM pass) ---")
    for raw, n in unmatched[:40]:
        print(f"  {n:>6,}  {raw}")


if __name__ == "__main__":
    main()
