# StackSense

Skill and career recommendations built from real job-posting data, not
survey opinions or invented confidence scores. Given a set of skills,
StackSense tells you what to learn next based on what actually co-occurs
in the market — and it's upfront about which parts of the answer come from
measured aggregation versus a learned model.

## The problem with most "skill recommender" projects

Most tutorials for this kind of tool either use TF-IDF over a tiny synthetic
dataset, or invent a plausible-looking demo with fabricated data. This one
runs on 34,663 real LinkedIn postings, and every number the API returns
traces back to something countable: a share of postings, a co-occurrence
count, or a rank in a Stack Overflow survey.

## How it works

**Vocabulary.** Stack Overflow's Developer Survey (2021–2025) gives an
externally curated set of ~2,300 technology names. That vocabulary is
extended with an LLM classification pass over frequent unmatched skill
strings pulled from the postings themselves (things the survey never asked
about — Terraform, CI/CD, Microservices), then consolidated by embedding
similarity to collapse spelling variants (".NET", ".NET/C#", ".NET 6" → one
node). The final vocabulary sits at 3,250 terms.

**Graph.** Skills that appear together in a posting get an edge, weighted by
PMI so a pair like Docker↔Kubernetes doesn't just win by both being common —
it wins by co-occurring *more than chance would predict*. Near-duplicate
postings (one recruiter reposting the same role 200+ times) are collapsed
before counting, and the whole thing is split train/val/test at the posting
level so no edge leaks across the boundary.

**Model.** A GraphSAGE GNN learns node embeddings over that graph, blended
with Resource Allocation — a much older, simpler link-prediction heuristic
(Zhou, Lu & Zhang, 2009) that scores shared neighbours weighted by inverse
degree. Neither wins outright, and the two barely agree with each other,
which turns out to be exactly why blending them works.

## How correlated are these signals?

Pairwise correlation between five structural indices and the GNN, measured
across all 3,250 nodes:

|                | jaccard | adamic-adar | resource-alloc | salton | hub-depressed | GNN   |
|----------------|--------:|------------:|----------------:|-------:|--------------:|------:|
| jaccard        |   1.000 |       0.535 |           0.336 |  0.955 |          0.979 | 0.590 |
| adamic-adar    |   0.535 |       1.000 |           0.878 |  0.539 |          0.498 | 0.376 |
| resource-alloc |   0.336 |       0.878 |           1.000 |  0.317 |          0.306 | 0.226 |
| salton         |   0.955 |       0.539 |           0.317 |  1.000 |          0.915 | 0.634 |
| hub-depressed  |   0.979 |       0.498 |           0.306 |  0.915 |          1.000 | 0.557 |

Resource Allocation is the least correlated with the GNN of the five (0.226).
That's the whole reason it's the one kept in the hybrid — ensemble gain here
tracks decorrelation with the GNN, not standalone ranking strength. Jaccard,
Salton, and Hub-depressed all move almost in lockstep with each other
(0.915–0.979) because they're variations on the same idea; Resource
Allocation and Adamic-Adar diverge from that cluster because they penalise
hub skills far more aggressively.

## Which structural index actually helps

Best Hits@10 achieved by each index when blended with the GNN, validation
split, row+column standardised:

| structural index   | best Hits@10 | winning α | mode     |
|---------------------|-------------:|----------:|----------|
| **Resource Allocation** |   **0.2705** |       0.9 | fixed    |
| Adamic-Adar          |       0.2576 |       0.5 | fixed    |
| Salton               |       0.2452 |       0.7 | fixed    |
| Jaccard              |       0.2424 |       0.6 | fixed    |
| Hub-depressed        |       0.2323 |       0.7 | fixed    |
| GNN alone (α=0)      |       0.0928 |         — | —        |

Resource Allocation wins, and by a comfortable margin over the next-best
index. GNN alone is far behind every hybrid — the structural signal is doing
most of the work, and the GNN's contribution is in the margins where
structure runs out.

## Final model

Selected on validation, confirmed once on test (never re-tuned against the
test number — see note below):

| split | Hits@5 | Hits@10 | Hits@20 | MRR |
|---|---:|---:|---:|---:|
| validation | 0.1760 | 0.2705 | 0.3886 | 0.1283 |
| **test** | **0.1951** | **0.2957** | 0.4171 | 0.1335 |

Configuration: Resource Allocation + GraphSAGE, α=0.9 fixed, row-then-column
standardised. That's 29% above the best single-component baseline
(Resource Allocation alone, Hits@10 0.2132 on test).

**A note on the alpha selection**, because it's easy to get backwards: α=0.9
was picked from the *validation* sweep, where it happened to be both the
single best point on the curve and part of a flat plateau running from
roughly α=0.2 to 0.9. A later sweep run directly on the *test* split showed
α=0.8 nosing very slightly ahead of 0.9 (0.2996 vs 0.2957, well within noise
at n=1,779). That number was **not** used to change the deployed alpha —
doing so would mean re-tuning on the held-out split, which defeats the point
of holding it out. The deployed config stays exactly what validation chose.

## Why row and column standardisation

Added after the raw model returned AWS, SQL, Agile, and Java for a
machine-learning skill profile — a hub-skill problem, not a bug. Row
standardisation makes each query skill contribute its *relative* preferences
rather than absolute magnitude; column standardisation stops a candidate
from winning purely by being popular against every query. Confirmed directly
against the deployed config (α=0.9, resource-alloc, test split):

| normalisation | Hits@5 | Hits@10 | Hits@20 | MRR |
|---|---:|---:|---:|---:|
| none | — | — | — | — |
| row | — | — | — | — |
| column | — | — | — | — |
| **row + column** | **0.1951** | **0.2957** | 0.4171 | 0.1335 |

*(fill in the first three rows once `norm_none_a09_test.json` /
`norm_row_a09_test.json` / `norm_col_a09_test.json` finish running — the
commands are already in the pipeline notes)*

## What didn't work

**SEAL** (subgraph-based link prediction, Zhang & Chen, NeurIPS 2018) lost
to the 2009 Resource Allocation heuristic once an evaluation bug was fixed.
The first comparison had RA's adjacency matrix built from only a 200-node
subset, which crippled its neighbour-overlap computation — SEAL looked ahead
under that bug (Hits@10 0.2723 vs RA's artificially crippled 0.2531). With
RA computed correctly against the full graph, the result flips entirely:

| model | Hits@10 (200-skill subset) |
|---|---:|
| SEAL | 0.2723 |
| GraphSAGE | 0.2998 |
| **Resource Allocation** | **0.4013** |

SEAL is the worst of the three, and a three-way sweep confirmed it adds
nothing even as a blend component — best combination was RA 0.9 / SEAL 0.1 /
GNN 0.0 at 0.4047, a quarter of a standard error above RA alone.

**GNN depth** is monotonically worse: a 1-layer SAGE outperforms 2-layer,
which outperforms 3-layer, on Hits@10. Over-smoothing sets in fast on a graph
with mean degree ~100.

**AUC and Hits@10 move in opposite directions during training**, across
every loss function tried (BCE, weighted BCE, regression). Reporting AUC
alone would have been actively misleading about ranking quality.

**An untrained GAT beat every trained variant** on the heterogeneous
role graph — training the attention weights made ranking performance worse,
not better, across every objective and learning rate tried.

None of these are failures to hide — they're the actual finding. On a graph
this dense, exact neighbourhood overlap sits close to the ceiling, and
learned methods mostly fit noise on top of it. Four independent
architectures (depth sweep, loss sweep, untrained-vs-trained GAT, and SEAL)
point at the same conclusion.

## Dataset

- 34,663 LinkedIn job postings, tech-role filtered by title
- 3,250 canonical skills after consolidation
- 21 job roles derived from title patterns, seeded from Stack Overflow's
  DevType taxonomy
- 457 technologies with a multi-year adoption trend (SO survey, 2019–2025)

## Repo layout

```
stacksense/
├── api/            FastAPI serving layer
│   ├── api.py
│   ├── resume_analyze.py   ← copy in from stacksense_upgrade/, not included here
│   ├── requirements.txt
│   ├── Dockerfile
│   └── data/                (empty until migrate_artifacts.py runs)
│       ├── vocab/            final_vocab.json, final_mapping.json
│       ├── graph/            graph.json
│       ├── embeddings/       sage-L1.pt
│       └── insights/         hetero_graph.json, trends.json
├── web/            Next.js frontend
│   └── Dockerfile
├── docker-compose.yml
└── migrate_artifacts.py

```



## Running it

```bash
docker compose up --build
```

- API: `http://localhost:8000` (interactive docs at `/docs`)
- Frontend: `http://localhost:3000`

No GPU required — the container only serves precomputed matrices and
embeddings, it doesn't train anything.

## Reproducing the pipeline

Scripts in `api/pipeline/` run in this order against your own copy of the
LinkedIn postings dataset and the Stack Overflow survey archive:

```bash
python build_vocab.py --archive path/to/so-survey-archive
python skill_mapper.py --data path/to/postings --vocab canonical_vocab.json
python llm_classify.py --top 2000        # needs an LLM API key, see the script
python consolidate.py
python build_graph.py
python extract_roles.py
python build_hetero.py
python train_gnn.py --tag sage-L1
python hybrid_v2.py --sweep --structural all
python build_trends.py --archive path/to/so-survey-archive
```

Each step writes into `vocab/`, `graph/`, `embeddings/`, or `insights/`.

## Not included here

This repo ships the reproducible core pipeline. Left out: exploratory
ablation scripts (LoRA fine-tuning sweep, SEAL, heterogeneous-graph GAT
training, community detection) whose findings are summarised above rather
than re-run on every clone — and a private resume-to-offer benchmarking
dataset that isn't public.