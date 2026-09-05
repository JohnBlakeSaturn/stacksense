"""
StackSense API.

Serves the pipeline built in the preceding steps. Everything is loaded once at
startup and held in memory: the graph is 2.8k nodes and ~155k edges, so the
similarity matrices are a few hundred megabytes and there is no reason to
recompute them per request.

Endpoint groups and what backs each:

    /skills/*      canonical vocabulary lookup and normalisation
    /recommend/*   hybrid scorer (Resource Allocation + GraphSAGE)
    /roles/*       skill-role edges, weighted by support and lift
    /trends/*      Stack Overflow rank slope, seven survey years
    /resume/*      extraction into canonical skills, then the above

Two deliberate choices worth knowing about:

The recommender and the gap analysis are different mechanisms. Recommendations
come from the learned hybrid; gap analysis is aggregation over role edges and
involves no model at all. That means gap results are exactly explainable -- "68%
of Data Engineer postings list this and you do not have it" -- and the responses
say which is which rather than presenting both as "AI recommendations".

Trends are attached as context, not folded into the ranking. The trend signal
comes from a differently-biased source (developer sentiment rather than employer
demand) and covers only about 8% of the vocabulary, so letting it reweight a
carefully evaluated ranking would trade a measured signal for an unvalidated
one. It is returned alongside each recommendation for the caller to display.

Data layout (baked into the Docker image, see Dockerfile):

    data/vocab/       final_vocab.json, final_mapping.json
    data/graph/        graph.json
    data/embeddings/   sage-L1.pt
    data/insights/      hetero_graph.json, trends.json

Run:
    uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Literal

import numpy as np
import torch
import torch.nn.functional as F
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATA = Path("data")
VOCAB = DATA / "vocab"
GRAPH_DIR = DATA / "graph"
EMBEDDINGS = DATA / "embeddings"
INSIGHTS = DATA / "insights"

# Blend weight, selected on validation under row+column normalisation. Under raw
# scoring the optimum sat at 0.1 with degree-adaptive weighting; once column
# standardisation removes the hub advantage directly, the structural component
# can carry most of the score and the adaptive weighting becomes redundant.
# Performance is flat from roughly 0.2 to 0.9 on both splits, so this is not a
# knife-edge choice.
ALPHA = 0.9
ADAPTIVE = False
DEGREE_PIVOT = 60.0  # unused while ADAPTIVE is False; kept for the ablation
TOP_K_DEFAULT = 10


# ============================================================== state
class Engine:
    """Everything loaded once at startup."""

    def __init__(self) -> None:
        self.ready = False
        self.errors: list[str] = []

    def load(self) -> None:
        try:
            self._load_vocab()
            self._load_graph()
            self.median_degree = float(self.degree.median())
            self._load_embeddings()
            self._load_roles()
            self._load_trends()
            self.ready = True
        except Exception as exc:                      # noqa: BLE001
            self.errors.append(f"{type(exc).__name__}: {exc}")
            raise

    # ---------------------------------------------------------- vocabulary
    def _load_vocab(self) -> None:
        self.vocab = json.loads((VOCAB / "final_vocab.json").read_text())
        self.mapping = json.loads((VOCAB / "final_mapping.json").read_text())
        self.meta = {}
        for entry in self.vocab:
            entry = dict(entry)
            if not isinstance(entry.get("category"), str):
                entry["category"] = "/".join(entry.get("category") or [])
            self.meta[entry["canonical"]] = entry

        # raw posting string -> canonical, plus a normalised index so callers
        # can send "javascript" or "Node JS" rather than exact canonical names
        from resume_analyze import RESUME_ALIASES, normalize

        self.norm_index: dict[str, str] = {}
        for spelling, canonical in RESUME_ALIASES.items():
            self.norm_index[normalize(spelling)] = canonical
        for entry in self.vocab:
            name = entry["canonical"]
            self.norm_index.setdefault(normalize(name), name)
            bare = name.split("(")[0].strip()
            if "/" in bare and not bare.startswith("."):
                for part in bare.split("/"):
                    if len(part.strip()) > 1:
                        self.norm_index.setdefault(normalize(part.strip()), name)
        for raw, canonical in self.mapping.items():
            self.norm_index.setdefault(normalize(raw), canonical)

        self._normalize = normalize

    # --------------------------------------------------------------- graph
    def _load_graph(self) -> None:
        graph = json.loads((GRAPH_DIR / "graph.json").read_text())
        self.skills = [n["name"] for n in graph["nodes"]]
        self.index = {s: i for i, s in enumerate(self.skills)}
        # A term that appeared in more than one survey block carries a list of
        # categories rather than a string (Pip is both Platform and Tool), so
        # flatten here and let every consumer assume a plain string.
        self.categories = {
            n["name"]: (n["category"] if isinstance(n["category"], str)
                        else "/".join(n["category"]))
            for n in graph["nodes"]
        }
        n = len(self.skills)

        adj = torch.zeros(n, n)
        self.neighbours: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for e in graph["train_edges"]:
            a, b = self.index[e["source"]], self.index[e["target"]]
            adj[a, b] = adj[b, a] = 1.0
            self.neighbours[e["source"]].append((e["target"], e["pmi"], e["count"]))
            self.neighbours[e["target"]].append((e["source"], e["pmi"], e["count"]))
        # sorted by PMI, which surfaces distinctive pairings rather than merely
        # frequent ones: Docker's top PMI neighbours are Docker Compose and
        # Podman, not Kubernetes, even though Kubernetes co-occurs far more
        # often. Both figures are returned so a caller can re-sort.
        for k in self.neighbours:
            self.neighbours[k].sort(key=lambda p: -p[1])

        # P(B|A): of postings mentioning A, what share also mention B. The
        # asymmetry between P(B|A) and P(A|B) is the only directional signal
        # available here -- it says which skill is the broader context, not
        # which is learned first.
        self.conditional: dict[tuple[str, str], float] = {}
        for e in graph["train_edges"]:
            a, b, n = e["source"], e["target"], e["count"]
            fa = self.meta.get(a, {}).get("mentions") or 0
            fb = self.meta.get(b, {}).get("mentions") or 0
            if fa:
                self.conditional[(a, b)] = round(n / fa, 4)
            if fb:
                self.conditional[(b, a)] = round(n / fb, 4)

        self.degree = adj.sum(dim=1).clamp(min=1)
        # Resource Allocation (Zhou, Lu & Zhang 2009): shared neighbours weighted
        # by 1/k, which penalises hubs far harder than Adamic-Adar's 1/log(k).
        # That matters on a graph where Python appears in a third of postings.
        self.ra = (adj * (1.0 / self.degree)[None, :]) @ adj.T
        self.ra_std = self._standardise(self.ra)

    @staticmethod
    def _standardise(x: torch.Tensor) -> torch.Tensor:
        return (x - x.mean()) / x.std().clamp(min=1e-8)

    @staticmethod
    def _row_standardise(x: torch.Tensor) -> torch.Tensor:
        """Z-score each row independently, so summing over several skills gives
        each one equal say regardless of how well-connected it is."""
        return (x - x.mean(dim=1, keepdim=True)) / x.std(dim=1, keepdim=True).clamp(min=1e-8)

    @staticmethod
    def _column_standardise(x: torch.Tensor) -> torch.Tensor:
        """Z-score each column, so a candidate scoring high against every query
        gains nothing from doing so."""
        return (x - x.mean(dim=0, keepdim=True)) / x.std(dim=0, keepdim=True).clamp(min=1e-8)

    # ---------------------------------------------------------- embeddings
    def _load_embeddings(self) -> None:
        checkpoint = torch.load(EMBEDDINGS / "sage-L1.pt", map_location="cpu")
        z = F.normalize(checkpoint["embeddings"], dim=-1)
        self.gnn_std = self._standardise(z @ z.T)

        # Per-row standardisation, applied before any summing over a user's
        # skills. Without it a hub dominates the aggregate: Python appears in a
        # third of all postings, so its row is high against everything, and
        # summing raw rows for [PyTorch, Machine Learning, Python] returns AWS,
        # SQL, C++ and Agile rather than TensorFlow and Deep Learning. Dropping
        # Python from the same query fixes it, which is what identified the
        # cause. Standardising each row first means every known skill
        # contributes what it is *unusually* associated with rather than what it
        # co-occurs with in absolute terms -- the same base-rate correction that
        # PMI applies to edges and Resource Allocation applies to shared
        # neighbours.
        if ADAPTIVE:
            # Weight the structural term by how much neighbourhood evidence each
            # endpoint actually has. Resource Allocation counts shared
            # neighbours, so it says little about a pair whose endpoints have
            # few; the GNN carries text features and degrades more gracefully
            # there. This is the blend validation selected.
            conf = (self.degree / (self.degree + DEGREE_PIVOT)).clamp(0, 1)
            w = torch.sqrt(conf[:, None] * conf[None, :]) * ALPHA
            self.scores = w * self.ra_std + (1 - w) * self.gnn_std
        else:
            self.scores = ALPHA * self.ra_std + (1 - ALPHA) * self.gnn_std

        # Row then column standardisation. Row: each query skill contributes
        # its relative preferences rather than its absolute magnitude. Column: a
        # candidate is scored against its own average across all queries, so a
        # merely ubiquitous skill stops winning by default. Together these lifted
        # test Hits@10 from 0.257 to 0.296 and fixed the case where an ML profile
        # returned AWS, SQL, Agile and Java.
        self.scores_norm = self._column_standardise(
            self._row_standardise(self.scores))
        self.ra_norm = self._column_standardise(
            self._row_standardise(self.ra_std))

    # --------------------------------------------------------------- roles
    def _load_roles(self) -> None:
        path = INSIGHTS / "hetero_graph.json"
        if not path.exists():
            self.roles, self.role_edges = [], {}
            return
        hetero = json.loads(path.read_text())
        self.roles = [r["name"] for r in hetero["role_nodes"]]
        self.role_info = {r["name"]: r for r in hetero["role_nodes"]}
        self.role_edges: dict[str, list[dict]] = defaultdict(list)
        for e in hetero["skill_role_edges"]:
            self.role_edges[e["role"]].append(e)
        for role in self.role_edges:
            self.role_edges[role].sort(key=lambda e: -e["support"])

    # -------------------------------------------------------------- trends
    def _load_trends(self) -> None:
        path = INSIGHTS / "trends.json"
        self.trends = json.loads(path.read_text()) if path.exists() else {}

    # ------------------------------------------------------------ resolving
    def resolve(self, raw: str) -> str | None:
        return self.norm_index.get(self._normalize(raw))

    def trend_of(self, skill: str) -> dict | None:
        entry = self.trends.get(skill)
        if not entry or "rank_slope" not in entry:
            return None
        slope = entry["rank_slope"]
        return {
            # rank slope rather than raw percentage change: respondent counts
            # swing from 83k to 32k across years, so absolute shares are not
            # comparable, while relative standing is
            "rank_slope": slope,
            "direction": "rising" if slope > 0.01 else "falling" if slope < -0.01 else "flat",
            "years_observed": entry.get("n_years"),
            "latest_adoption": entry.get("latest"),
            "desire_gap": entry.get("desire_gap"),
        }


engine = Engine()

app = FastAPI(
    title="StackSense API",
    description="Skill and career recommendations from job-posting co-occurrence.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    try:
        engine.load()
    except Exception as exc:                          # noqa: BLE001
        print(f"startup failed: {exc}")


def require_ready() -> None:
    if not engine.ready:
        raise HTTPException(503, f"engine not loaded: {engine.errors}")


# ============================================================== schemas
class SkillsIn(BaseModel):
    skills: list[str] = Field(..., description="Skill names in any spelling.")


class RecommendIn(SkillsIn):
    top_k: int = Field(TOP_K_DEFAULT, ge=1, le=100)
    target_role: str | None = Field(
        None, description="Restrict and re-rank toward this role."
    )
    method: Literal["hybrid", "heuristic"] = Field(
        "hybrid",
        description="'heuristic' runs the original TF-IDF-era scorer, kept as a "
                    "labelled baseline so the two can be compared directly.",
    )
    exclude_categories: list[str] = Field(
        default_factory=lambda: ["tech-practice"],
        description="Categories to omit. Practices (Agile, CI/CD, Scrum) "
                    "co-occur with everything and crowd out actionable skills.",
    )


class GapIn(SkillsIn):
    role: str
    seniority: str | None = Field(None, description="junior, mid, senior, staff, lead, principal")
    top_k: int = Field(15, ge=1, le=100)


class ResolvedSkill(BaseModel):
    input: str
    canonical: str | None
    category: str | None = None


# ============================================================== endpoints
@app.get("/health")
def health() -> dict:
    return {
        "ready": engine.ready,
        "errors": engine.errors,
        "skills": len(getattr(engine, "skills", [])),
        "roles": len(getattr(engine, "roles", [])),
        "trends": len(getattr(engine, "trends", {})),
    }


@app.post("/skills/normalize", response_model=list[ResolvedSkill])
def normalize_skills(body: SkillsIn) -> list[ResolvedSkill]:
    """Map free-text skill names onto the canonical vocabulary.

    Unrecognised names return canonical=null rather than being dropped: a caller
    showing "we did not recognise 3 of your 20 skills" is more honest than one
    silently working with 17.
    """
    require_ready()
    return [
        ResolvedSkill(
            input=s,
            canonical=(c := engine.resolve(s)),
            category=engine.categories.get(c) if c else None,
        )
        for s in body.skills
    ]


@app.get("/skills")
def list_skills() -> dict:
    """Full canonical vocabulary, for client-side autocomplete.

    Returned once and cached by the caller rather than hit per keystroke --
    3,250 short strings is a few hundred KB, trivial next to the embedding
    matrices already held in memory.
    """
    require_ready()
    return {
        "skills": [
            {
                "canonical": s,
                "category": engine.categories.get(s),
                "postings_mentioning": engine.meta.get(s, {}).get("mentions"),
            }
            for s in engine.skills
        ]
    }


@app.get("/skills/{name}")
def skill_detail(name: str, neighbours: int = 15) -> dict:
    require_ready()
    canonical = engine.resolve(name)
    if not canonical or canonical not in engine.index:
        raise HTTPException(404, f"unknown skill: {name}")
    meta = engine.meta.get(canonical, {})
    return {
        "canonical": canonical,
        "category": engine.categories.get(canonical),
        "in_survey": meta.get("in_survey"),
        "postings_mentioning": meta.get("mentions"),
        "degree": int(engine.degree[engine.index[canonical]]),
        "trend": engine.trend_of(canonical),
        "co_occurring_distinctive": [
            {"skill": s, "pmi": p, "postings": c}
            for s, p, c in engine.neighbours[canonical][:neighbours]
        ],
        "co_occurring_frequent": [
            {"skill": s, "pmi": p, "postings": c}
            for s, p, c in sorted(engine.neighbours[canonical],
                                  key=lambda t: -t[2])[:neighbours]
        ],
        "roles_requiring": sorted(
            (
                {"role": role, "support": e["support"], "lift": e["lift"]}
                for role, edges in engine.role_edges.items()
                for e in edges
                if e["skill"] == canonical
            ),
            key=lambda r: -r["lift"],
        )[:8],
    }


@app.post("/recommend/skills")
def recommend(body: RecommendIn) -> dict:
    """Rank skills the caller does not have by affinity to the ones they do.

    Scores come from the hybrid: Resource Allocation over the co-occurrence
    graph blended with GraphSAGE embeddings at alpha=0.1, chosen on the
    validation split. The two components are kept because they are only weakly
    correlated (0.226) and the ensemble gain tracks that decorrelation: across
    five structural indices, hybrid performance follows correlation with the GNN
    almost monotonically. The GNN scores 0.083 alone against Resource
    Allocation's 0.278, yet every blend of the two beats either -- a component
    three times weaker standalone still adds 6% when mixed in.
    """
    require_ready()
    resolved, unknown = [], []
    for s in body.skills:
        c = engine.resolve(s)
        (resolved if c and c in engine.index else unknown).append(c or s)
    if not resolved:
        raise HTTPException(400, {"error": "no recognisable skills", "unknown": unknown})

    known = [engine.index[c] for c in resolved]
    matrix = engine.ra_norm if body.method == "heuristic" else engine.scores_norm
    score = matrix[known].sum(dim=0)
    score[known] = -1e9
    if body.exclude_categories:
        drop = [i for i, s in enumerate(engine.skills)
                if engine.categories.get(s) in body.exclude_categories]
        score[drop] = -1e9

    role_support: dict[str, float] = {}
    if body.target_role:
        if body.target_role not in engine.role_edges:
            raise HTTPException(404, f"unknown role: {body.target_role}")
        # Lift rather than support: support alone puts Python at the top of every
        # role, since it is ubiquitous. Lift asks whether a skill is more common
        # in this role than in the corpus, which is what "characteristic of the
        # role" means. /roles/gap already ranks this way; this makes the two
        # endpoints consistent.
        role_lift = {e["skill"]: e["lift"] for e in engine.role_edges[body.target_role]}
        role_support = {e["skill"]: e["support"] for e in engine.role_edges[body.target_role]}
        mask = torch.tensor(
            [1.0 + max(role_lift.get(s, -1.0), -0.9) for s in engine.skills],
            dtype=torch.float,
        )
        score = score * mask.clamp(min=0.1)

    order = torch.argsort(score, descending=True)[: body.top_k]
    results = []
    for rank, i in enumerate(order.tolist(), start=1):
        skill = engine.skills[i]
        results.append({
            "rank": rank,
            "skill": skill,
            "score": round(float(score[i]), 4),
            "category": engine.categories.get(skill),
            "postings_mentioning": engine.meta.get(skill, {}).get("mentions"),
            "role_support": round(role_support[skill], 4) if skill in role_support else None,
            "trend": engine.trend_of(skill),
            "given_your_skills": max(
                (engine.conditional.get((k, skill), 0.0) for k in resolved),
                default=0.0,
            ),
        })
    warning = None
    if len(known) == 1:
        skill = resolved[0]
        deg = float(engine.degree[known[0]])
        if deg > 2 * engine.median_degree:
            warning = (
                f"{skill} appears in "
                f"{engine.meta.get(skill, {}).get('mentions', 0):,} postings across "
                f"every domain. Add a second skill for a more specific answer."
            )

    return {
        "method": body.method,
        "recognised": resolved,
        "unrecognised": unknown,
        "target_role": body.target_role,
        "recommendations": results,
        "warning": warning,
        "note": "Scores are relative rankings, not probabilities. Trend data "
                "comes from the Stack Overflow survey and reflects developer "
                "sentiment, not employer demand.",
    }


@app.get("/roles")
def list_roles() -> dict:
    require_ready()
    return {
        "roles": [
            {
                "name": r,
                "postings": engine.role_info[r]["postings"],
                "by_seniority": engine.role_info[r]["by_level"],
                "distinct_skills": len(engine.role_edges.get(r, [])),
            }
            for r in engine.roles
        ]
    }


@app.post("/roles/gap")
def role_gap(body: GapIn) -> dict:
    """What a role asks for that the caller does not have.

    This is aggregation over job postings, not a model prediction: every number
    is a share of that role's postings. Skills are ranked by lift rather than
    raw support, because support alone puts Python at the top of every role --
    it is ubiquitous, so its presence says nothing about the role.
    """
    require_ready()
    if body.role not in engine.role_edges:
        raise HTTPException(404, f"unknown role: {body.role}")

    have = {c for s in body.skills if (c := engine.resolve(s))}
    edges = engine.role_edges[body.role]

    missing, covered = [], []
    for e in edges:
        support = e["support"]
        if body.seniority and body.seniority in e.get("by_level", {}):
            support = e["by_level"][body.seniority]
            if support == 0:
                continue
        row = {
            "skill": e["skill"],
            "support": round(support, 4),
            "lift": e["lift"],
            "by_seniority": e.get("by_level"),
            "trend": engine.trend_of(e["skill"]),
        }
        (covered if e["skill"] in have else missing).append(row)

    missing.sort(key=lambda r: -(r["support"] * max(r["lift"], 0.1)))
    total = len(edges)
    return {
        "role": body.role,
        "seniority": body.seniority,
        "postings_analysed": engine.role_info[body.role]["postings"],
        "coverage": round(len(covered) / total, 4) if total else 0.0,
        "you_have": sorted(covered, key=lambda r: -r["support"])[:30],
        "gaps": missing[: body.top_k],
        "note": "Support is the share of this role's postings listing the skill. "
                "Lift compares that against how often the skill appears corpus-wide, "
                "so a high-support low-lift skill is common everywhere rather than "
                "characteristic of this role.",
    }


@app.post("/roles/match")
def role_match(body: SkillsIn) -> dict:
    """Rank roles by how much of their requirement profile the caller covers.

    Coverage is weighted by support, so matching a skill 70% of postings ask for
    counts more than one only 5% mention.
    """
    require_ready()
    have = {c for s in body.skills if (c := engine.resolve(s))}
    if not have:
        raise HTTPException(400, "no recognisable skills")

    rows = []
    for role, edges in engine.role_edges.items():
        total = sum(e["support"] for e in edges)
        matched = sum(e["support"] for e in edges if e["skill"] in have)
        top_missing = [
            e["skill"] for e in sorted(edges, key=lambda e: -e["support"])
            if e["skill"] not in have
        ][:5]
        rows.append({
            "role": role,
            "coverage": round(matched / total, 4) if total else 0.0,
            "matched_skills": sorted(e["skill"] for e in edges if e["skill"] in have)[:15],
            "top_missing": top_missing,
            "postings": engine.role_info[role]["postings"],
        })
    rows.sort(key=lambda r: -r["coverage"])
    return {"recognised": sorted(have), "roles": rows}


@app.get("/trends/{name}")
def trend(name: str) -> dict:
    require_ready()
    canonical = engine.resolve(name) or name
    entry = engine.trends.get(canonical)
    if not entry:
        raise HTTPException(404, f"no trend data for {name}")
    return {
        "skill": canonical,
        "series": entry.get("series"),
        "rank_series": entry.get("rank_series"),
        "rank_slope": entry.get("rank_slope"),
        "desire_gap": entry.get("desire_gap"),
        "years_observed": entry.get("n_years"),
        "source": "Stack Overflow Developer Survey 2019-2025",
        "caveat": "Developer sentiment among survey respondents, not employer "
                  "demand. Respondent counts vary from 83k to 32k across years, "
                  "so relative standing is more reliable than absolute share.",
    }


@app.get("/trends")
def trends_overview(direction: Literal["rising", "falling"] = "rising",
                    limit: int = 20) -> dict:
    require_ready()
    rows = [
        {"skill": k, "rank_slope": v["rank_slope"],
         "latest_adoption": v.get("latest"), "years_observed": v.get("n_years")}
        for k, v in engine.trends.items()
        if "rank_slope" in v and v.get("n_years", 0) >= 4
    ]
    rows.sort(key=lambda r: -r["rank_slope"] if direction == "rising" else r["rank_slope"])
    return {
        "direction": direction,
        "skills": rows[:limit],
        "note": "Restricted to technologies observed in at least four survey "
                "years; shorter series produce unreliable slopes.",
    }


@app.post("/resume/analyze")
async def analyze_resume(file: UploadFile = File(...),
                         target_role: str | None = None,
                         top_k: int = TOP_K_DEFAULT) -> dict:
    """Extract skills from a resume, then run recommendations against them.

    The resume is an input path into the same recommender rather than a separate
    feature. Extraction weights by section -- a skill demonstrated in a project
    counts more than one listed in a skills block, which counts more than one
    from coursework -- but the weights are hand-set and mild, and they are
    returned so a caller can see where each skill came from.

    target_role and top_k are query parameters (not form fields): once an
    endpoint accepts a File/UploadFile, FastAPI treats other plain-typed
    parameters as query params rather than multipart body fields, since the
    request body itself is multipart-encoded for the file. Call this as
    POST /resume/analyze?target_role=...&top_k=... with the file in the body.
    """
    require_ready()
    import tempfile

    from resume_analyze import (SECTION_WEIGHT, build_index, extract_skills,
                                read_text, segment)

    suffix = Path(file.filename or "resume.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        text = read_text(tmp_path)
        sections = segment(text)
        by_norm, names = build_index(engine.vocab)
        found, unmatched = extract_skills(sections, by_norm, names, False, 0.80)
    finally:
        tmp_path.unlink(missing_ok=True)

    skills = [s for s in found if s in engine.index]
    payload = {
        "sections_found": {k: len(v) for k, v in sections.items()},
        "skills": [
            {"skill": s, **found[s], "trend": engine.trend_of(s)}
            for s in sorted(found, key=lambda s: -found[s]["weight"])
        ],
        "unmatched_terms": [t for t, _ in unmatched[:40]],
        "note": "Terms absent from the vocabulary are listed rather than dropped. "
                "The vocabulary is derived from job postings, so academic and "
                "niche tooling vocabulary is often not represented.",
    }

    if skills:
        payload["recommendations"] = recommend(
            RecommendIn(skills=skills, top_k=top_k, target_role=target_role)
        )["recommendations"]
        payload["role_match"] = role_match(SkillsIn(skills=skills))["roles"][:5]
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
