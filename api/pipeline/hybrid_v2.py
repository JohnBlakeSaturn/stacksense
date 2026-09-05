"""
Hybrid scorer: blends a structural index over the co-occurrence graph with the
GraphSAGE embeddings.

    resource-alloc  Hits@10 0.213   -- sharp ranking, blind on sparse pairs
    sage-L1         Hits@10 0.115   -- strong on sparse pairs, blurry ranking

Structural indices compute exact neighbourhood overlap, which stays
discriminative among a node's true neighbours. The GNN compresses each node
into a fixed vector, losing that precision, but carries signal into the
low-support region where overlap is uninformative. Since neither dominates:

    fixed      s = a * structural + (1 - a) * gnn
    adaptive   a varies with pair degree -- lean on overlap where there's
               enough of it to mean something, on the GNN otherwise

Scores are standardised before mixing (structural indices are bounded ratios,
the GNN decoder is an unbounded dot product).

Two optional post-hoc normalisations, off by default:

    --row-standardise     each query skill contributes its relative
                          preferences rather than its absolute magnitude
    --column-standardise  a candidate is scored against its own average
                          across queries, so a merely ubiquitous skill
                          stops winning by default

Both were added after the API returned AWS, SQL, Agile and Java for an ML
profile. They improve the served ranking and are expected to lower Hits@k,
since the metric rewards predicting whatever appears in most postings --
exactly what column standardisation suppresses.

Usage:
    python hybrid_v2.py --gnn embeddings/sage-L1.pt --sweep --structural all
    python hybrid_v2.py --gnn embeddings/sage-L1.pt --split test \\
        --alpha 0.1 --adaptive --structural resource-alloc
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import pandas as pd
import torch
import torch.nn.functional as F

SEED = 42
HITS_AT = (5, 10, 20)


def standardise(x: torch.Tensor) -> torch.Tensor:
    return (x - x.mean()) / x.std().clamp(min=1e-8)


def apply_normalisation(scores: torch.Tensor, row: bool, col: bool) -> torch.Tensor:
    """Row: each query skill contributes its relative preferences, so summing
    over [PyTorch, Machine Learning, Python] isn't decided by Python alone
    (it appears in a third of all postings, so its row is high against
    everything). Column: a candidate is scored against its own average across
    queries, so a skill that scores high for every query gets no credit."""
    if row:
        scores = ((scores - scores.mean(dim=1, keepdim=True))
                  / scores.std(dim=1, keepdim=True).clamp(min=1e-8))
    if col:
        scores = ((scores - scores.mean(dim=0, keepdim=True))
                  / scores.std(dim=0, keepdim=True).clamp(min=1e-8))
    return scores


class Hybrid:
    def __init__(self, graph_path: Path, gnn_path: Path):
        graph = json.loads(graph_path.read_text())
        self.names = [n["name"] for n in graph["nodes"]]
        self.index = {n: i for i, n in enumerate(self.names)}
        N = len(self.names)

        adj = torch.zeros(N, N)
        for e in graph["train_edges"]:
            a, b = self.index[e["source"]], self.index[e["target"]]
            adj[a, b] = adj[b, a] = 1.0
        self.adj = adj
        self.degree = adj.sum(dim=1)

        inter = adj @ adj.T
        union = self.degree[:, None] + self.degree[None, :] - inter
        self.jaccard = inter / union.clamp(min=1)

        # Adamic-Adar: shared neighbours discounted by 1/log(degree).
        w = 1.0 / torch.log(self.degree.clamp(min=2))
        self.adamic_adar = (adj * w[None, :]) @ adj.T

        # Resource Allocation (Zhou, Lu & Zhang 2009): 1/degree penalty rather
        # than 1/log(degree), so hubs are discounted much harder -- suits a
        # graph where Python appears in a third of all postings.
        wr = 1.0 / self.degree.clamp(min=1)
        self.resource_alloc = (adj * wr[None, :]) @ adj.T

        # Salton (cosine): normalises by geometric mean of degrees rather than
        # union, gentler on degree imbalance.
        d = self.degree.clamp(min=1)
        self.salton = inter / torch.sqrt(d[:, None] * d[None, :])

        # Hub-depressed: divides by the larger degree, so a pair scores highly
        # only if the busier node still shares most of its neighbourhood.
        self.hub_depressed = inter / torch.maximum(d[:, None].expand_as(inter),
                                                   d[None, :].expand_as(inter))

        z = torch.load(gnn_path, map_location="cpu")["embeddings"]
        z = F.normalize(z, dim=-1)
        self.gnn = z @ z.T

        self.g_rank = standardise(self.gnn)
        self._ranks = {
            "jaccard": standardise(self.jaccard),
            "adamic-adar": standardise(self.adamic_adar),
            "resource-alloc": standardise(self.resource_alloc),
            "salton": standardise(self.salton),
            "hub-depressed": standardise(self.hub_depressed),
        }
        self.set_structural("jaccard")

    def set_structural(self, name: str) -> None:
        self.structural_name = name
        self.j_rank = self._ranks[name]

    def scores(self, alpha: float, adaptive: bool = False,
               pivot: float = 60.0) -> torch.Tensor:
        if not adaptive:
            return alpha * self.j_rank + (1 - alpha) * self.g_rank

        d = self.degree.clamp(min=1)
        conf = (d / (d + pivot)).clamp(0, 1)
        w = torch.sqrt(conf[:, None] * conf[None, :]) * alpha
        return w * self.j_rank + (1 - w) * self.g_rank


def masked_skill(scores: torch.Tensor, postings: pd.DataFrame,
                 index: dict[str, int], n_postings: int, rng: random.Random) -> dict:
    usable = []
    for skills in postings["skills"]:
        known = [index[s] for s in skills if s in index]
        if len(known) >= 4:
            usable.append(known)
    rng.shuffle(usable)
    usable = usable[:n_postings]

    hits = {k: 0 for k in HITS_AT}
    rr, total = 0.0, 0
    for skills in usable:
        masked = set(rng.sample(skills, max(1, len(skills) // 3)))
        known = [s for s in skills if s not in masked]
        if not known:
            continue
        s = scores[known].sum(dim=0)
        s[known] = -1e9
        order = torch.argsort(s, descending=True)
        rank = torch.empty_like(order)
        rank[order] = torch.arange(len(order))
        for t in masked:
            r = int(rank[t]) + 1
            total += 1
            rr += 1.0 / r
            for k in HITS_AT:
                if r <= k:
                    hits[k] += 1
    if not total:
        return {}
    out = {f"hits@{k}": round(hits[k] / total, 4) for k in HITS_AT}
    out["mrr"] = round(rr / total, 4)
    out["n_targets"] = total
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", type=Path, default=Path("graph/graph.json"))
    ap.add_argument("--postings", type=Path, default=Path("graph/postings_clean.parquet"))
    ap.add_argument("--gnn", type=Path, default=Path("embeddings/sage-L1.pt"))
    ap.add_argument("--split", choices=["val", "test"], default="val")
    ap.add_argument("--alpha", type=float, default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--adaptive", action="store_true")
    ap.add_argument("--structural",
                    choices=["jaccard", "adamic-adar", "resource-alloc",
                             "salton", "hub-depressed", "both", "all"],
                    default="jaccard")
    ap.add_argument("--row-standardise", action="store_true",
                    help="z-score each skill's row before summing")
    ap.add_argument("--column-standardise", action="store_true",
                    help="subtract each candidate's mean across queries")
    ap.add_argument("--mask-postings", type=int, default=400)
    ap.add_argument("--out", type=Path, default=Path("hybrid_out/hybrid.json"))
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    h = Hybrid(args.graph, args.gnn)
    postings = pd.read_parquet(args.postings)
    postings = postings[postings["split"] == args.split]

    norm = ("row+col" if args.row_standardise and args.column_standardise
            else "row" if args.row_standardise
            else "col" if args.column_standardise
            else "none")
    print(f"{len(h.names):,} nodes | {args.split} postings {len(postings):,} "
          f"| normalisation: {norm}\n")

    if args.structural == "both":
        structurals = ["jaccard", "adamic-adar"]
    elif args.structural == "all":
        structurals = ["jaccard", "adamic-adar", "resource-alloc",
                       "salton", "hub-depressed"]
    else:
        structurals = [args.structural]

    results = {}
    for structural in structurals:
        h.set_structural(structural)
        print(f"### structural component: {structural}")
        run(h, postings, args, results, structural, norm)

    args.out.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {args.out}")


def run(h, postings, args, results, structural: str, norm: str) -> None:
    tag = "" if norm == "none" else f"_{norm}"

    if args.sweep:
        print(f"{'alpha':>7}{'Hits@5':>9}{'Hits@10':>9}{'Hits@20':>9}{'MRR':>9}   mode")
        print("-" * 56)
        for alpha in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
            for adaptive in (False, True):
                if adaptive and alpha == 0.0:
                    continue
                s = apply_normalisation(h.scores(alpha, adaptive),
                                        args.row_standardise,
                                        args.column_standardise)
                m = masked_skill(s, postings, h.index, args.mask_postings,
                                 random.Random(SEED))
                mode = "adaptive" if adaptive else "fixed"
                results[f"{structural}_{mode}_{alpha}{tag}"] = m
                print(f"{alpha:>7.1f}{m['hits@5']:>9.4f}{m['hits@10']:>9.4f}"
                      f"{m['hits@20']:>9.4f}{m['mrr']:>9.4f}   {mode}")
        here = {k: v for k, v in results.items() if k.startswith(structural)}
        best = max(here.items(), key=lambda kv: kv[1]["hits@10"])
        print(f"\nbest: {best[0]}  Hits@10 {best[1]['hits@10']:.4f}")
        print(f"alpha 0.0 is the GNN alone, 1.0 is {structural} alone\n")
    else:
        alpha = args.alpha if args.alpha is not None else 0.5
        s = apply_normalisation(h.scores(alpha, args.adaptive),
                                args.row_standardise, args.column_standardise)
        m = masked_skill(s, postings, h.index, args.mask_postings, random.Random(SEED))
        mode = "adaptive" if args.adaptive else "fixed"
        results[f"{structural}_{mode}_{alpha}{tag}"] = m
        print(f"alpha {alpha} ({mode}), split {args.split}, normalisation {norm}")
        print(" ", m)


if __name__ == "__main__":
    main()
