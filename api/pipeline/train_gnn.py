"""
GraphSAGE link prediction over the skill graph.

Baselines to beat (val split, degree-matched negatives):

    jaccard      AUC 0.578   Hits@10 0.195   MRR 0.095   w3-5 0.534
    st-base      AUC 0.536   Hits@10 0.058   MRR 0.028   w3-5 0.518
    st-lora      AUC 0.570   Hits@10 0.075   MRR 0.032   w3-5 0.571

Structure dominates ranking; text features win on low-support pairs where
structural signal is at chance. The GNN holds both -- text as node inputs,
structure through message passing.

Node features come from a sentence-transformer, so running with
--features st-base vs the fine-tuned checkpoint isolates what LoRA
contributes once message passing is present.

Training uses only train_edges; val edges never reach the encoder.

Usage:
    python train_gnn.py --features all-MiniLM-L6-v2 --tag st-base
    python train_gnn.py --features sweep/lr2e-4_bs64_ep4 --tag st-lora
    python train_gnn.py --features all-MiniLM-L6-v2 --conv gat --tag gat-base
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

SEED = 42
HITS_AT = (5, 10, 20)
SUPPORT_BANDS = [(3, 5), (6, 10), (11, 10**9)]


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class Encoder(nn.Module):
    def __init__(self, in_dim: int, hidden: int, out: int, conv: str,
                 layers: int, dropout: float, edge_dim: int = 0, heads: int = 4):
        super().__init__()
        from torch_geometric.nn import GATConv, GCNConv, SAGEConv

        self.conv_type = conv
        self.dropout = dropout
        self.convs = nn.ModuleList()
        dims = [in_dim] + [hidden] * (layers - 1) + [out]

        for i in range(layers):
            a, b = dims[i], dims[i + 1]
            if conv == "sage":
                self.convs.append(SAGEConv(a, b))
            elif conv == "gcn":
                self.convs.append(GCNConv(a, b))
            elif conv == "gat":
                # heads concat on all but the final layer, so divide width to
                # keep parameter count comparable to SAGE
                last = i == layers - 1
                self.convs.append(
                    GATConv(a, b if last else b // heads,
                            heads=1 if last else heads,
                            edge_dim=edge_dim or None,
                            dropout=dropout)
                )
            else:
                raise ValueError(conv)

    def forward(self, x, edge_index, edge_attr=None):
        for i, conv in enumerate(self.convs):
            if self.conv_type == "gat" and edge_attr is not None:
                x = conv(x, edge_index, edge_attr=edge_attr)
            else:
                x = conv(x, edge_index)
            if i < len(self.convs) - 1:
                x = F.relu(x)
                x = F.dropout(x, p=self.dropout, training=self.training)
        return x


def decode(z: torch.Tensor, pairs: torch.Tensor) -> torch.Tensor:
    return (z[pairs[0]] * z[pairs[1]]).sum(dim=-1)


def degree_matched_negatives(num_nodes, adj, degrees, n, rng, tries=40):
    """Negatives with endpoint degrees similar to positives, so the model can't
    score well by ranking hubs highly."""
    buckets = defaultdict(list)
    for i in range(num_nodes):
        buckets[int(math.log1p(degrees[i]) * 2)].append(i)
    keys = list(buckets)

    src, dst = [], []
    for _ in range(n):
        for _ in range(tries):
            ka, kb = rng.choice(keys), rng.choice(keys)
            a, b = rng.choice(buckets[ka]), rng.choice(buckets[kb])
            if a != b and b not in adj[a]:
                src.append(a)
                dst.append(b)
                break
        else:
            a, b = rng.randrange(num_nodes), rng.randrange(num_nodes)
            src.append(a)
            dst.append(b)
    return torch.tensor([src, dst], dtype=torch.long)


def masked_skill_eval(z, postings, index, n_postings, rng):
    """Hide part of a posting's skills, rank all candidates by summed
    similarity to the known ones, report where the hidden ones land."""
    z = F.normalize(z, dim=-1)
    sims = z @ z.T

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
        n_mask = max(1, len(skills) // 3)
        masked = set(rng.sample(skills, n_mask))
        known = [s for s in skills if s not in masked]
        if not known:
            continue

        score = sims[known].sum(dim=0)
        score[known] = -1e9
        order = torch.argsort(score, descending=True)
        rank_of = torch.empty_like(order)
        rank_of[order] = torch.arange(len(order), device=order.device)

        for target in masked:
            r = int(rank_of[target]) + 1
            total += 1
            rr += 1.0 / r
            for k in HITS_AT:
                if r <= k:
                    hits[k] += 1

    if not total:
        return {}
    out = {f"hits@{k}": hits[k] / total for k in HITS_AT}
    out["mrr"] = rr / total
    out["n_targets"] = total
    return out


def link_metrics(pos_scores, neg_scores, supports):
    from sklearn.metrics import average_precision_score, roc_auc_score

    p = pos_scores.detach().cpu().numpy()
    n = neg_scores.detach().cpu().numpy()
    y = np.concatenate([np.ones_like(p), np.zeros_like(n)])
    s = np.concatenate([p, n])
    out = {"auc": float(roc_auc_score(y, s)), "ap": float(average_precision_score(y, s))}

    for lo, hi in SUPPORT_BANDS:
        idx = [i for i, c in enumerate(supports) if lo <= c <= hi]
        if len(idx) < 50:
            continue
        sub_n = n[: len(idx)]
        yy = np.concatenate([np.ones(len(idx)), np.zeros(len(sub_n))])
        ss = np.concatenate([p[idx], sub_n])
        out[f"auc_w{lo}-{hi if hi < 10**9 else '+'}"] = float(roc_auc_score(yy, ss))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", type=Path, default=Path("graph/graph.json"))
    ap.add_argument("--postings", type=Path, default=Path("graph/postings_clean.parquet"))
    ap.add_argument("--features", default="all-MiniLM-L6-v2",
                    help="sentence-transformer name or path for node features")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--conv", choices=["sage", "gcn", "gat"], default="sage")
    ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--hidden", type=int, default=256)
    ap.add_argument("--out-dim", type=int, default=128)
    ap.add_argument("--dropout", type=float, default=0.3)
    ap.add_argument("--lr", type=float, default=5e-3)
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--patience", type=int, default=40)
    ap.add_argument("--loss", choices=["bce", "weighted-bce", "regress"], default="weighted-bce",
                    help="bce treats every edge as equally strong, which teaches "
                         "edge-vs-nonedge but nothing about ranking within edges")
    ap.add_argument("--select-on", choices=["auc", "hits@10", "mrr"], default="hits@10",
                    help="metric for early stopping and checkpoint selection")
    ap.add_argument("--eval-every", type=int, default=10)
    ap.add_argument("--edge-features", action="store_true",
                    help="pass [log(count), pmi] to GAT attention")
    ap.add_argument("--split", choices=["val", "test"], default="val")
    ap.add_argument("--mask-postings", type=int, default=400)
    ap.add_argument("--out-dir", type=Path, default=Path("embeddings"))
    args = ap.parse_args()

    set_seed(SEED)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device {device} | conv {args.conv} | features {args.features}")

    import pandas as pd

    graph = json.loads(args.graph.read_text())
    names = [n["name"] for n in graph["nodes"]]
    index = {n: i for i, n in enumerate(names)}
    N = len(names)

    src, dst, counts, pmis = [], [], [], []
    adj = defaultdict(set)
    for e in graph["train_edges"]:
        a, b = index[e["source"]], index[e["target"]]
        src += [a, b]
        dst += [b, a]
        counts += [e["count"]] * 2
        pmis += [e["pmi"]] * 2
        adj[a].add(b)
        adj[b].add(a)

    edge_index = torch.tensor([src, dst], dtype=torch.long, device=device)
    edge_attr = None
    if args.edge_features:
        edge_attr = torch.tensor(
            np.stack([np.log1p(counts), pmis], axis=1), dtype=torch.float, device=device
        )
    # Edge strength for the weighted losses. Under plain BCE every edge gets
    # target 1 regardless of count, so the model separates edges from
    # non-edges but has no signal for ordering edges among themselves -- which
    # is what Hits@k measures.
    edge_w = torch.tensor(np.log1p(counts), dtype=torch.float, device=device)
    edge_w = edge_w / edge_w.mean()

    degrees = [len(adj[i]) for i in range(N)]
    print(f"nodes {N:,} | directed edges {edge_index.shape[1]:,}")

    held_key = "val_edges" if args.split == "val" else "test_edges"
    held = [(index[e["source"]], index[e["target"]], e.get("count", 0))
            for e in graph[held_key]
            if e["source"] in index and e["target"] in index]
    pos_eval = torch.tensor([[a for a, _, _ in held], [b for _, b, _ in held]],
                            dtype=torch.long, device=device)
    supports = [c for _, _, c in held]
    print(f"{args.split} edges {len(held):,}")

    rng = random.Random(SEED)
    neg_eval = degree_matched_negatives(N, adj, degrees, len(held), rng).to(device)

    from sentence_transformers import SentenceTransformer

    st = SentenceTransformer(args.features, device=device)
    x = torch.tensor(
        st.encode(names, normalize_embeddings=True, batch_size=256, show_progress_bar=True),
        dtype=torch.float, device=device,
    )
    print(f"node features {tuple(x.shape)}")

    model = Encoder(x.shape[1], args.hidden, args.out_dim, args.conv,
                    args.layers, args.dropout,
                    edge_dim=2 if args.edge_features else 0).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-5)
    print(f"parameters {sum(p.numel() for p in model.parameters()):,}\n")

    import pandas as _pd
    postings_eval = _pd.read_parquet(args.postings)
    postings_eval = postings_eval[postings_eval["split"] == args.split]

    train_pos = torch.tensor([src, dst], dtype=torch.long, device=device)
    best = {"auc": 0.0, "epoch": -1}
    best_state = None
    stale = 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        opt.zero_grad()
        z = model(x, edge_index, edge_attr)

        neg = degree_matched_negatives(N, adj, degrees, train_pos.shape[1],
                                       random.Random(epoch)).to(device)
        pos_s, neg_s = decode(z, train_pos), decode(z, neg)

        if args.loss == "bce":
            loss = F.binary_cross_entropy_with_logits(
                torch.cat([pos_s, neg_s]),
                torch.cat([torch.ones_like(pos_s), torch.zeros_like(neg_s)]),
            )
        elif args.loss == "weighted-bce":
            pos_loss = F.binary_cross_entropy_with_logits(
                pos_s, torch.ones_like(pos_s), weight=edge_w
            )
            neg_loss = F.binary_cross_entropy_with_logits(neg_s, torch.zeros_like(neg_s))
            loss = pos_loss + neg_loss
        else:  # regress: predict log-count directly, non-edges regress to zero
            loss = (F.mse_loss(pos_s, edge_w) + F.mse_loss(neg_s, torch.zeros_like(neg_s)))
        loss.backward()
        opt.step()

        if epoch % args.eval_every == 0 or epoch == 1:
            model.eval()
            with torch.no_grad():
                z = model(x, edge_index, edge_attr)
                m = link_metrics(decode(z, pos_eval), decode(z, neg_eval), supports)
                # ranking quality needs a direct check: AUC saturates on a
                # graph this dense and stops discriminating between checkpoints
                mm = masked_skill_eval(z, postings_eval, index, 200, random.Random(SEED))
            m.update({k: v for k, v in mm.items() if k != "n_targets"})

            score = m.get(args.select_on, 0.0)
            if score > best.get(args.select_on, -1):
                best = {**m, "epoch": epoch}
                best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
                stale = 0
            else:
                stale += args.eval_every
            print(f"  epoch {epoch:>4}  loss {loss.item():.4f}  "
                  f"auc {m['auc']:.4f}  hits@10 {m.get('hits@10', 0):.4f}  "
                  f"mrr {m.get('mrr', 0):.4f}  best[{args.select_on}] "
                  f"{best.get(args.select_on, 0):.4f}")
            if stale >= args.patience:
                print(f"  early stop at {epoch} (no gain for {stale} epochs)")
                break

    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        z = model(x, edge_index, edge_attr)
        lp = link_metrics(decode(z, pos_eval), decode(z, neg_eval), supports)

    postings = pd.read_parquet(args.postings)
    postings = postings[postings["split"] == args.split]
    ms = masked_skill_eval(z, postings, index, args.mask_postings, random.Random(SEED))

    print(f"\n--- {args.tag} ({args.conv}) best epoch {best['epoch']} ---")
    print("  link prediction:", {k: round(v, 4) for k, v in lp.items()})
    print("  masked skill   :", {k: round(v, 4) for k, v in ms.items()})

    result = {
        "tag": args.tag,
        "conv": args.conv,
        "features": str(args.features),
        "split": args.split,
        "best_epoch": best["epoch"],
        "link_prediction": lp,
        "masked_skill": ms,
    }
    (args.out_dir / f"{args.tag}.json").write_text(json.dumps(result, indent=1))
    torch.save({"state_dict": best_state, "embeddings": z.cpu()},
               args.out_dir / f"{args.tag}.pt")
    print(f"\nwrote {args.out_dir}/{args.tag}.json")

    print("\n" + "=" * 66)
    print(f"{'model':<22}{'AUC':>8}{'w3-5':>8}{'Hits@10':>10}{'MRR':>8}")
    print("=" * 66)
    print(f"{'jaccard (baseline)':<22}{0.5779:>8.4f}{0.5344:>8.4f}{0.1947:>10.4f}{0.0947:>8.4f}")
    print(f"{'st-base (baseline)':<22}{0.5358:>8.4f}{0.5179:>8.4f}{0.0583:>10.4f}{0.0278:>8.4f}")
    print(f"{'st-lora (baseline)':<22}{0.5699:>8.4f}{0.5709:>8.4f}{0.0746:>10.4f}{0.0316:>8.4f}")
    print(f"{args.tag:<22}{lp['auc']:>8.4f}{lp.get('auc_w3-5', float('nan')):>8.4f}"
          f"{ms.get('hits@10', float('nan')):>10.4f}{ms.get('mrr', float('nan')):>8.4f}")


if __name__ == "__main__":
    main()
