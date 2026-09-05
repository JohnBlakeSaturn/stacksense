"""
Build the skill co-occurrence graph.

Order: canonicalise -> dedup -> split -> count edges.

Dedup has to run after canonicalisation, since near-duplicate postings only
become detectable once spelling variation is removed (one agency in this
corpus posts the same role hundreds of times; raw, those look like distinct
skill sets). Split has to run before edge counting, and at the posting level:
two skills co-occurring in the same posting produce correlated edges, so
splitting edges randomly would leak correlated pairs across train/val/test.

Outputs (graph/):
    postings_clean.parquet   canonicalised, deduped postings with split labels
    graph.json               nodes, train edges, val/test edge lists
    stats.json               diagnostics

Usage:
    python build_graph.py --dedup-threshold 0.6 --min-edge-weight 3
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd

SEED = 42


def canonicalise(postings: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Map raw skill strings to canonical terms, dropping anything that didn't
    survive earlier steps (soft skills, credentials, noise, low-frequency tail)."""
    rows = []
    for link, raw in zip(postings["job_link"], postings["job_skills"]):
        skills = {
            mapping[part.strip()]
            for part in str(raw).split(",")
            if part.strip() in mapping
        }
        if len(skills) >= 2:
            rows.append({"job_link": link, "skills": sorted(skills)})
    out = pd.DataFrame(rows)
    out = out.merge(postings[["job_link", "job_title", "company"]], on="job_link", how="left")
    return out


def dedup(postings: pd.DataFrame, threshold: float) -> tuple[pd.DataFrame, int]:
    """Collapse near-identical postings within the same company. Compared only
    within a company: two employers listing the same stack is real signal, the
    same employer reposting one role isn't."""
    keep_idx: list[int] = []
    removed = 0

    for _, group in postings.groupby("company", dropna=False):
        seen: list[set] = []
        for idx, skills in zip(group.index, group["skills"]):
            s = set(skills)
            if any(len(s & t) / len(s | t) >= threshold for t in seen if s | t):
                removed += 1
                continue
            seen.append(s)
            keep_idx.append(idx)

    return postings.loc[sorted(keep_idx)].reset_index(drop=True), removed


def split_postings(postings: pd.DataFrame, val: float, test: float) -> pd.DataFrame:
    """Assign whole postings to train/val/test, so no edge can be reconstructed
    across the boundary."""
    rng = random.Random(SEED)
    labels = []
    for _ in range(len(postings)):
        r = rng.random()
        labels.append("test" if r < test else "val" if r < test + val else "train")
    postings = postings.copy()
    postings["split"] = labels
    return postings


def build_edges(postings: pd.DataFrame, min_weight: int) -> tuple[Counter, Counter]:
    edges: Counter = Counter()
    node_df: Counter = Counter()
    for skills in postings["skills"]:
        node_df.update(skills)
        for a, b in combinations(sorted(skills), 2):
            edges[(a, b)] += 1
    if min_weight > 1:
        edges = Counter({e: w for e, w in edges.items() if w >= min_weight})
    return edges, node_df


def pmi_weights(edges: Counter, node_df: Counter, n_docs: int) -> dict:
    """Positive PMI: scores a pair by how much more often it co-occurs than
    independence predicts. Raw counts rank every pair with a ubiquitous skill
    (Python, SQL) at the top regardless of specificity."""
    import math

    out = {}
    for (a, b), w in edges.items():
        p_ab = w / n_docs
        p_a = node_df[a] / n_docs
        p_b = node_df[b] / n_docs
        if p_a and p_b:
            pmi = math.log(p_ab / (p_a * p_b))
            if pmi > 0:
                out[(a, b)] = {"count": w, "pmi": round(pmi, 4)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", type=Path, default=Path("vocab"))
    ap.add_argument("--out-dir", type=Path, default=Path("graph"))
    ap.add_argument("--dedup-threshold", type=float, default=0.6)
    ap.add_argument("--min-edge-weight", type=int, default=3)
    ap.add_argument("--val", type=float, default=0.1)
    ap.add_argument("--test", type=float, default=0.1)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    mapping = json.loads((args.in_dir / "final_mapping.json").read_text())
    vocab = json.loads((args.in_dir / "final_vocab.json").read_text())
    postings = pd.read_parquet(args.in_dir / "tech_postings.parquet")
    print(f"postings in                 {len(postings):>9,}")
    print(f"vocabulary                  {len(vocab):>9,}")

    clean = canonicalise(postings, mapping)
    print(f"after canonicalisation      {len(clean):>9,}  "
          f"(dropped postings with <2 mapped skills)")
    sizes = clean["skills"].str.len()
    print(f"  skills per posting        mean {sizes.mean():.1f}  median {int(sizes.median())}  max {sizes.max()}")

    clean, removed = dedup(clean, args.dedup_threshold)
    print(f"after dedup (J>={args.dedup_threshold})       {len(clean):>9,}  "
          f"({removed:,} near-duplicates removed)")

    clean = split_postings(clean, args.val, args.test)
    counts = clean["split"].value_counts()
    print(f"  train {counts.get('train', 0):,}  "
          f"val {counts.get('val', 0):,}  test {counts.get('test', 0):,}")

    train = clean[clean["split"] == "train"]

    edges, node_df = build_edges(train, args.min_edge_weight)
    weighted = pmi_weights(edges, node_df, len(train))
    nodes = sorted({n for e in weighted for n in e})

    print(f"\ngraph")
    print(f"  nodes                     {len(nodes):>9,}")
    print(f"  edges (w>={args.min_edge_weight}, pmi>0)      {len(weighted):>9,}")
    if nodes:
        deg: Counter = Counter()
        for a, b in weighted:
            deg[a] += 1
            deg[b] += 1
        print(f"  mean degree               {sum(deg.values()) / len(nodes):>9.1f}")
        print(f"  density                   "
              f"{2 * len(weighted) / (len(nodes) * (len(nodes) - 1)):>9.4f}")

    # Held-out edges restricted to nodes the training graph knows, with the
    # same support floor as training -- without it, most eval pairs occur
    # once or twice and are coincidences rather than affinities.
    node_set = set(nodes)
    held = {}
    held_support = {}
    for name in ("val", "test"):
        part = clean[clean["split"] == name]
        pair_counts: Counter = Counter()
        for skills in part["skills"]:
            known = [s for s in skills if s in node_set]
            pair_counts.update(combinations(sorted(known), 2))
        unseen = {p: c for p, c in pair_counts.items() if p not in weighted}
        kept = {p: c for p, c in unseen.items() if c >= args.min_edge_weight}
        held[name] = sorted(kept)
        held_support[name] = kept
        print(f"  {name} edges unseen in train  {len(unseen):>9,} "
              f"-> {len(kept):,} at w>={args.min_edge_weight}")

    cat = {e["canonical"]: e["category"] for e in vocab}
    in_survey = {e["canonical"]: e["in_survey"] for e in vocab}

    graph = {
        "nodes": [
            {
                "name": n,
                "category": cat.get(n, "tech-product"),
                "in_survey": in_survey.get(n, False),
                "doc_freq": node_df[n],
            }
            for n in nodes
        ],
        "train_edges": [
            {"source": a, "target": b, "count": v["count"], "pmi": v["pmi"]}
            for (a, b), v in weighted.items()
        ],
        "val_edges": [
            {"source": a, "target": b, "count": held_support["val"][(a, b)]}
            for a, b in held["val"]
        ],
        "test_edges": [
            {"source": a, "target": b, "count": held_support["test"][(a, b)]}
            for a, b in held["test"]
        ],
    }
    (args.out_dir / "graph.json").write_text(json.dumps(graph))
    clean.to_parquet(args.out_dir / "postings_clean.parquet", index=False)
    (args.out_dir / "stats.json").write_text(json.dumps({
        "postings_in": len(postings),
        "postings_clean": len(clean),
        "duplicates_removed": removed,
        "nodes": len(nodes),
        "train_edges": len(weighted),
        "val_edges": len(held["val"]),
        "test_edges": len(held["test"]),
        "dedup_threshold": args.dedup_threshold,
        "min_edge_weight": args.min_edge_weight,
    }, indent=1))

    print(f"\nwrote {args.out_dir}/graph.json")
    print(f"wrote {args.out_dir}/postings_clean.parquet")

    top = sorted(weighted.items(), key=lambda kv: -kv[1]["pmi"])[:20]
    print("\n--- 20 highest-PMI edges (should look like genuine affinities) ---")
    for (a, b), v in top:
        print(f"  pmi {v['pmi']:>5.2f}  n={v['count']:>4}  {a}  <->  {b}")

    common = sorted(weighted.items(), key=lambda kv: -kv[1]["count"])[:15]
    print("\n--- 15 most frequent edges (should look generic) ---")
    for (a, b), v in common:
        print(f"  n={v['count']:>5}  pmi {v['pmi']:>5.2f}  {a}  <->  {b}")


if __name__ == "__main__":
    main()
