"""
Build the heterogeneous skill/role graph.

Adds a second node type on top of the skill co-occurrence graph:

    skill --cooccurs_with--> skill     weighted by count and PMI
    skill --required_by----> role      weighted by the fraction of that role's
                                       postings listing the skill, plus one
                                       weight per seniority level

Roles are not split by seniority -- 21 roles x 6 levels would give 126 nodes,
and a role with 400 postings drops to under 70 per level, below where edge
weights are stable. Seniority instead rides on the skill-role edge as a
per-level vector.

The train/val/test split from build_graph.py is reused unchanged; role edges
are computed from training postings only.

Usage:
    python build_hetero.py
    python build_hetero.py --min-role-support 0.05
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

SENIORITY_LEVELS = ["junior", "mid", "senior", "staff", "lead", "principal"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", type=Path, default=Path("graph/graph.json"))
    ap.add_argument("--roles", type=Path, default=Path("insights/postings_roles.parquet"))
    ap.add_argument("--out-dir", type=Path, default=Path("insights"))
    ap.add_argument("--min-role-support", type=float, default=0.03,
                    help="drop skill-role edges below this share of the role's postings")
    ap.add_argument("--min-edge-weight", type=int, default=3)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    graph = json.loads(args.graph.read_text())
    skills = [n["name"] for n in graph["nodes"]]
    skill_index = {s: i for i, s in enumerate(skills)}
    print(f"skill nodes          {len(skills):>8,}")
    print(f"skill-skill edges    {len(graph['train_edges']):>8,}")

    postings = pd.read_parquet(args.roles)
    postings = postings[postings["role"].notna()]
    train = postings[postings["split"] == "train"]
    print(f"\npostings with a role {len(postings):>8,}  (train {len(train):,})")

    roles = sorted(train["role"].unique())
    role_index = {r: i for i, r in enumerate(roles)}
    print(f"role nodes           {len(roles):>8,}")

    role_total: Counter = Counter()
    role_level_total: dict[str, Counter] = defaultdict(Counter)
    skill_in_role: dict[str, Counter] = defaultdict(Counter)
    skill_in_role_level: dict[tuple[str, str], Counter] = defaultdict(Counter)

    for role, level, skill_list in zip(train["role"], train["seniority"], train["skills"]):
        role_total[role] += 1
        role_level_total[role][level] += 1
        seen = {s for s in skill_list if s in skill_index}
        for s in seen:
            skill_in_role[role][s] += 1
            skill_in_role_level[(role, level)][s] += 1

    # Edge weight is the share of the role's postings listing the skill --
    # directly interpretable (0.68 = 68% of Data Engineer postings ask for it)
    # and what makes gap analysis explainable without the model.
    role_edges = []
    for role in roles:
        total = role_total[role]
        for skill, n in skill_in_role[role].items():
            support = n / total
            if support < args.min_role_support or n < args.min_edge_weight:
                continue

            levels = {}
            for level in SENIORITY_LEVELS:
                denom = role_level_total[role].get(level, 0)
                if denom >= 20:
                    levels[level] = round(
                        skill_in_role_level[(role, level)].get(skill, 0) / denom, 4
                    )

            # concentration of this skill in this role vs the corpus, e.g.
            # "Airflow matters specifically to Data Engineers" vs "everyone
            # asks for Python"
            overall = sum(skill_in_role[r].get(skill, 0) for r in roles) / len(train)
            lift = math.log(support / overall) if overall > 0 else 0.0

            role_edges.append({
                "skill": skill,
                "role": role,
                "support": round(support, 4),
                "count": n,
                "lift": round(lift, 4),
                "by_level": levels,
            })

    print(f"skill-role edges     {len(role_edges):>8,}")
    per_role = Counter(e["role"] for e in role_edges)
    print(f"  per role: mean {sum(per_role.values()) / len(per_role):.0f}, "
          f"min {min(per_role.values())}, max {max(per_role.values())}")

    train_pairs = {(e["skill"], e["role"]) for e in role_edges}
    held = {}
    for split in ("val", "test"):
        part = postings[postings["split"] == split]
        counts: Counter = Counter()
        totals: Counter = Counter()
        for role, skill_list in zip(part["role"], part["skills"]):
            totals[role] += 1
            for s in {x for x in skill_list if x in skill_index}:
                counts[(s, role)] += 1
        kept = [
            {"skill": s, "role": r, "count": n}
            for (s, r), n in counts.items()
            if (s, r) not in train_pairs
            and n >= args.min_edge_weight
            and totals[r] and n / totals[r] >= args.min_role_support
        ]
        held[split] = kept
        print(f"  {split} role edges unseen in train: {len(kept):,}")

    out = {
        "skill_nodes": [
            {"name": n["name"], "category": n["category"], "doc_freq": n["doc_freq"]}
            for n in graph["nodes"]
        ],
        "role_nodes": [
            {
                "name": r,
                "postings": role_total[r],
                "by_level": {lv: role_level_total[r].get(lv, 0) for lv in SENIORITY_LEVELS},
            }
            for r in roles
        ],
        "skill_skill_edges": graph["train_edges"],
        "skill_role_edges": role_edges,
        "val_skill_edges": graph["val_edges"],
        "test_skill_edges": graph["test_edges"],
        "val_role_edges": held["val"],
        "test_role_edges": held["test"],
    }
    path = args.out_dir / "hetero_graph.json"
    path.write_text(json.dumps(out))
    print(f"\nwrote {path}")

    print("\n--- top skills by support, for four roles ---")
    for role in ["AI/ML Engineer", "Data Engineer", "Developer, Front-end",
                 "Security Professional"]:
        if role not in role_index:
            continue
        rows = sorted((e for e in role_edges if e["role"] == role),
                      key=lambda e: -e["support"])[:8]
        print(f"\n  {role}  ({role_total[role]:,} postings)")
        for e in rows:
            print(f"    {e['support']:>6.1%}  lift {e['lift']:>+5.2f}  {e['skill']}")

    print("\n--- most role-specific skills (highest lift, support >= 15%) ---")
    top = sorted((e for e in role_edges if e["support"] >= 0.15),
                 key=lambda e: -e["lift"])[:20]
    for e in top:
        print(f"  lift {e['lift']:>+5.2f}  {e['support']:>6.1%}  "
              f"{e['skill']:<32} -> {e['role']}")

    print("\n--- seniority effects: largest senior-minus-mid gaps ---")
    gaps = []
    for e in role_edges:
        lv = e["by_level"]
        if "mid" in lv and "senior" in lv:
            gaps.append((lv["senior"] - lv["mid"], e))
    gaps.sort(key=lambda x: -x[0])
    for delta, e in gaps[:12]:
        print(f"  +{delta:.1%}  {e['skill']:<30} {e['role']:<28} "
              f"mid {e['by_level']['mid']:.1%} -> senior {e['by_level']['senior']:.1%}")


if __name__ == "__main__":
    main()
