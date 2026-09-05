"""
API tests.

Most of these check semantics rather than status codes. An endpoint returning 200
with nonsense is worse than one returning 500, because nothing downstream will
notice. So the assertions ask whether the answers are actually right: does a
frontend profile get frontend recommendations, does Kubernetes rank Docker
highly, does the gap analysis for Data Engineer surface Spark rather than Python.

Start the server first:
    uvicorn api:app --port 8000

Then:
    python test_api.py
    python test_api.py --resume test.pdf     # also exercise the upload path
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

# 127.0.0.1 rather than localhost: on Windows, resolving "localhost" tries
# IPv6 first and falls back to IPv4, which costs about two seconds per request
# and made the API look 500x slower than it is. A shared client on top of that
# keeps the connection open -- fresh connections add another 180ms each.
BASE = "http://127.0.0.1:8000"
CLIENT = httpx.Client(base_url=BASE, timeout=180.0)
passed, failed = 0, 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def get(path: str, **params):
    return CLIENT.get(f"{path}", params=params, timeout=60)


def post(path: str, body: dict):
    return CLIENT.post(f"{path}", json=body, timeout=60)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", type=Path, default=None)
    args = ap.parse_args()

    # ------------------------------------------------------------ health
    section("health")
    r = get("/health")
    check("health responds", r.status_code == 200)
    health = r.json()
    check("engine ready", health.get("ready"), str(health.get("errors")))
    check("skills loaded", health.get("skills", 0) > 3000, f"got {health.get('skills')}")
    check("roles loaded", health.get("roles", 0) == 21, f"got {health.get('roles')}")
    check("trends loaded", health.get("trends", 0) > 400, f"got {health.get('trends')}")
    if not health.get("ready"):
        print("\nengine not ready, stopping")
        sys.exit(1)

    # ------------------------------------------------------- normalisation
    section("skill normalisation")
    r = post("/skills/normalize", {"skills": [
        "python", "PYTHON", "  Python  ",          # casing and whitespace
        "js", "JavaScript",                        # alias
        "k8s", "Kubernetes",                       # alias
        "postgres",                                # alias
        "Zzzzz Not A Real Skill",                  # should not resolve
    ]})
    check("normalize responds", r.status_code == 200)
    out = {x["input"]: x["canonical"] for x in r.json()}
    check("case-insensitive", out["python"] == out["PYTHON"] == out["  Python  "] == "Python",
          str({k: out[k] for k in ("python", "PYTHON", "  Python  ")}))
    check("js resolves to JavaScript", out["js"] == "JavaScript", f"got {out['js']}")
    check("k8s resolves to Kubernetes", out["k8s"] == "Kubernetes", f"got {out['k8s']}")
    check("postgres resolves to PostgreSQL", out["postgres"] == "PostgreSQL", f"got {out['postgres']}")
    check("nonsense stays unresolved", out["Zzzzz Not A Real Skill"] is None,
          "unknown input should return null rather than a nearest guess")

    # ------------------------------------------------------- skill detail
    section("skill detail")
    r = get("/skills/Docker")
    check("docker found", r.status_code == 200)
    if r.status_code == 200:
        d = r.json()
        distinctive = [n["skill"] for n in d["co_occurring_distinctive"]]
        frequent = [n["skill"] for n in d["co_occurring_frequent"]]
        # PMI surfaces distinctive pairings, count surfaces obvious ones; the
        # original version of this test asserted the wrong one
        check("kubernetes is a frequent docker neighbour", "Kubernetes" in frequent[:5],
              f"top 5 by count: {frequent[:5]}")
        check("distinctive neighbours are container-related",
              len({"Docker Compose", "Podman", "Containerization", "Kubernetes",
                   "Container Orchestration"} & set(distinctive[:8])) >= 2,
              f"top 8 by pmi: {distinctive[:8]}")
        check("docker has a category", d.get("category") is not None)
        check("docker appears in roles", len(d.get("roles_requiring", [])) > 0)

    r = get("/skills/definitely-not-a-skill-xyz")
    check("unknown skill returns 404", r.status_code == 404, f"got {r.status_code}")

    # ------------------------------------------------------ recommendations
    section("recommendations: are they semantically right?")

    r = post("/recommend/skills", {"skills": ["React", "JavaScript", "HTML/CSS"], "top_k": 15})
    check("frontend profile responds", r.status_code == 200)
    recs = [x["skill"] for x in r.json()["recommendations"]]
    frontend = {"TypeScript", "Angular", "Node.js", "Vue.js", "Redux", "Webpack",
                "Frontend Development", "Web Development", "Responsive Design",
                "jQuery", "Bootstrap", "UI/UX Design", "Next.js"}
    check("frontend profile gets frontend suggestions",
          len(frontend & set(recs)) >= 3, f"got {recs[:10]}")
    check("does not recommend skills already held",
          not ({"React", "JavaScript", "HTML/CSS"} & set(recs)), f"got {recs[:10]}")

    r = post("/recommend/skills", {"skills": ["Kubernetes", "Docker", "Terraform"], "top_k": 15})
    recs = [x["skill"] for x in r.json()["recommendations"]]
    devops = {"AWS", "Ansible", "Jenkins", "CI/CD", "Helm", "Prometheus", "Grafana",
              "Linux", "DevOps", "Microsoft Azure", "Google Cloud", "Infrastructure as Code",
              "Cloud Computing", "Containerization"}
    check("devops profile gets devops suggestions",
          len(devops & set(recs)) >= 3, f"got {recs[:10]}")

    r = post("/recommend/skills", {"skills": ["PyTorch", "Machine Learning", "Python"], "top_k": 15})
    recs = [x["skill"] for x in r.json()["recommendations"]]
    ml = {"TensorFlow", "Deep Learning", "NumPy", "Pandas", "Scikit-Learn",
          "Natural Language Processing", "Computer Vision", "Neural Networks",
          "Torch/PyTorch", "Data Science", "Keras", "MLOps"}
    check("ml profile gets ml suggestions", len(ml & set(recs)) >= 3, f"got {recs[:10]}")

    # the three profiles should not collapse to the same generic answer
    fe = set(x["skill"] for x in post("/recommend/skills",
             {"skills": ["React", "JavaScript"], "top_k": 10}).json()["recommendations"])
    ml2 = set(x["skill"] for x in post("/recommend/skills",
              {"skills": ["PyTorch", "Machine Learning"], "top_k": 10}).json()["recommendations"])
    check("different profiles give different answers", len(fe & ml2) < 6,
          f"overlap {sorted(fe & ml2)}")

    r = post("/recommend/skills", {"skills": ["Zzzz", "Qqqq"], "top_k": 5})
    check("all-unknown input returns 400", r.status_code == 400, f"got {r.status_code}")

    r = post("/recommend/skills", {"skills": ["Python", "Zzzz"], "top_k": 5})
    check("partial-unknown input still works", r.status_code == 200)
    if r.status_code == 200:
        check("unrecognised terms are reported back",
              "Zzzz" in r.json()["unrecognised"],
              "callers need to know what was ignored")

    # ---------------------------------------------------------- role gaps
    section("role gap analysis")
    r = get("/roles")
    check("roles listed", r.status_code == 200 and len(r.json()["roles"]) == 21)

    r = post("/roles/gap", {"skills": ["Python", "SQL"], "role": "Data Engineer", "top_k": 15})
    check("gap responds", r.status_code == 200)
    if r.status_code == 200:
        g = r.json()
        gaps = [x["skill"] for x in g["gaps"]]
        have = [x["skill"] for x in g["you_have"]]
        check("python and sql counted as held",
              "Python" in have and "SQL" in have, f"you_have: {have[:8]}")
        check("held skills are not listed as gaps",
              not ({"Python", "SQL"} & set(gaps)), f"gaps: {gaps[:8]}")
        expected = {"Apache Spark", "Data Warehousing", "Data Modeling", "ETL",
                    "Data Engineering", "Airflow", "Snowflake", "Databricks",
                    "Data Pipelines", "AWS", "Scala", "Apache Kafka"}
        check("data engineer gaps look like data engineering",
              len(expected & set(gaps)) >= 3, f"got {gaps[:10]}")
        check("gaps carry support figures",
              all(0 <= x["support"] <= 1 for x in g["gaps"]))
        check("coverage is a fraction", 0 <= g["coverage"] <= 1)

    r = post("/roles/gap", {"skills": ["Python"], "role": "Not A Role"})
    check("unknown role returns 404", r.status_code == 404, f"got {r.status_code}")

    r = post("/roles/gap", {"skills": ["Python"], "role": "Developer, Back-end",
                            "seniority": "senior", "top_k": 10})
    check("seniority filter accepted", r.status_code == 200)

    # --------------------------------------------------------- role match
    section("role matching")
    r = post("/roles/match", {"skills": ["React", "JavaScript", "TypeScript", "HTML/CSS", "Angular"]})
    check("match responds", r.status_code == 200)
    if r.status_code == 200:
        ranked = [x["role"] for x in r.json()["roles"]]
        check("frontend skills rank a frontend role first",
              ranked[0] in {"Developer, Front-end", "Developer, Full-stack"},
              f"top 3: {ranked[:3]}")
        coverages = [x["coverage"] for x in r.json()["roles"]]
        check("coverage sorted descending", coverages == sorted(coverages, reverse=True))

    r = post("/roles/match", {"skills": ["Kubernetes", "Docker", "Terraform", "Ansible", "Jenkins"]})
    if r.status_code == 200:
        ranked = [x["role"] for x in r.json()["roles"]]
        check("devops skills rank an infra role first",
              ranked[0] in {"DevOps Engineer", "Site Reliability Engineer",
                            "Cloud Infrastructure Engineer"},
              f"top 3: {ranked[:3]}")

    # ------------------------------------------------------------- trends
    section("trends")
    r = get("/trends", direction="rising", limit=10)
    check("rising trends respond", r.status_code == 200)
    if r.status_code == 200:
        rising = [x["skill"] for x in r.json()["skills"]]
        check("rising list is plausible",
              len({"Rust", "Torch/PyTorch", "Kubernetes", "Terraform", "FastAPI",
                   "Flutter", "Bun", "Go", "TypeScript"} & set(rising)) >= 2,
              f"got {rising}")
        check("all rising slopes are positive",
              all(x["rank_slope"] > 0 for x in r.json()["skills"]))

    r = get("/trends", direction="falling", limit=10)
    if r.status_code == 200:
        check("all falling slopes are negative",
              all(x["rank_slope"] < 0 for x in r.json()["skills"]))

    r = get("/trends/Python")
    check("python trend found", r.status_code == 200)
    if r.status_code == 200:
        t = r.json()
        check("series has multiple years", len(t.get("series", {})) >= 4,
              f"got {list(t.get('series', {}))}")
        check("caveat is present", "caveat" in t,
              "trend responses must state that this is sentiment, not demand")

    r = get("/trends/Zzzz")
    check("unknown trend returns 404", r.status_code == 404, f"got {r.status_code}")

    # ------------------------------------------------------------- resume
    if args.resume and args.resume.exists():
        section("resume upload")
        with open(args.resume, "rb") as fh:
            r = CLIENT.post(f"/resume/analyze",
                           files={"file": (args.resume.name, fh, "application/pdf")},
                           timeout=180)
        check("resume accepted", r.status_code == 200, r.text[:200])
        if r.status_code == 200:
            body = r.json()
            check("skills extracted", len(body.get("skills", [])) > 10,
                  f"got {len(body.get('skills', []))}")
            check("sections identified", len(body.get("sections_found", {})) >= 3)
            check("recommendations returned", len(body.get("recommendations", [])) > 0)
            check("role match returned", len(body.get("role_match", [])) > 0)
            check("unmatched terms surfaced", "unmatched_terms" in body,
                  "terms outside the vocabulary should be listed, not dropped")

    # ------------------------------------------------------------ summary
    print("\n" + "=" * 50)
    print(f"passed {passed}   failed {failed}")
    print("=" * 50)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()