"""
LLM pass over the frequent unmatched skill strings.

The survey vocabulary covers products but not practices (Agile, CI/CD), tools
it never asked about (Jenkins, Tableau), or domain concepts (Machine Learning,
Microservices), and doesn't separate soft skills/credentials from tech -- all
of those come out of the NER as "skills". This classifies each frequent
unmatched string and, for technical ones, assigns a canonical name.

Spot-check the review file before trusting it -- this is model output, not
ground truth.

Usage:
    export API_KEY=...
    python llm_classify.py --top 2000
    python llm_classify.py --top 2000 --resume
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BATCH_SIZE = 40

CATEGORIES = """
tech-product   a named technology: language, framework, library, database, tool,
               platform, service, IDE  (Jenkins, Tableau, Redis, Terraform)
tech-practice  an engineering practice or methodology
               (Agile, CI/CD, Scrum, Unit Testing, Code Review, TDD)
tech-domain    a technical field or specialisation
               (Machine Learning, Microservices, Cybersecurity, Distributed Systems)
soft-skill     a non-technical human skill
               (Communication, Teamwork, Leadership, Mentoring, Attention to Detail)
credential     a degree, certification, clearance, or experience requirement
               (Bachelor's Degree, AWS Certified, Security Clearance, 5+ years)
noise          not a skill at all: salary text, benefits, boilerplate, extraction
               artefacts, job-ad filler
""".strip()

PROMPT = """You are normalising skill labels extracted from software job postings.

For each input string, decide its category and, if it is technical, its canonical name.

Categories:
{categories}

Canonical naming rules:
- If the string is a spelling variant, abbreviation, or casing difference of a term
  in the KNOWN VOCABULARY below, set "canonical" to that exact known term.
- Otherwise, if it is technical, set "canonical" to the most standard, conventional
  spelling of the concept (e.g. "ci/cd" -> "CI/CD", "objectoriented programming" ->
  "Object-Oriented Programming", "problemsolving" -> null since it is a soft skill).
- For soft-skill, credential, and noise, set "canonical" to null.
- Do not invent technologies. If a string is ambiguous or you cannot identify it,
  use category "noise" and canonical null.

KNOWN VOCABULARY (use these exact spellings when a string matches one):
{vocab}

Return ONLY a JSON object of this exact shape, with one entry per input string,
in the same order as the input:
{{"results": [{{"raw": "<input string>", "category": "<category>", "canonical": "<name or null>"}}]}}

Input strings:
{items}"""


def call_gemini(prompt: str, api_key: str, model: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = httpx.post(
        url,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
        },
        timeout=120.0,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code}: {r.text[:400]}")
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def call_groq(prompt: str, api_key: str, model: str) -> str:
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        },
        timeout=120.0,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code}: {r.text[:400]}")
    return r.json()["choices"][0]["message"]["content"]


def call_openai_compatible(prompt: str, api_key: str, model: str, base_url: str) -> str:
    """Works for OpenAI and Together AI, which share the chat/completions schema."""
    r = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        },
        timeout=120.0,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code}: {r.text[:400]}")
    return r.json()["choices"][0]["message"]["content"]


def parse_response(text: str) -> list[dict]:
    """Models sometimes wrap the array in fences or an object; handle both."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
        return []
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", type=Path, default=Path("vocab"))
    ap.add_argument("--vocab", type=Path, default=Path("canonical_vocab.json"))
    ap.add_argument("--top", type=int, default=2000)
    ap.add_argument("--provider", choices=["gemini", "groq", "openai", "together"],
                    default="gemini")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel batches; raise to 4-8 on a paid tier")
    ap.add_argument("--model", default=None)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    PROVIDERS = {
        "gemini":   ("GEMINI_API_KEY",   "gemini-2.5-flash",                None),
        "groq":     ("GROQ_API_KEY",     "llama-3.3-70b-versatile",         "https://api.groq.com/openai/v1"),
        "openai":   ("OPENAI_API_KEY",   "gpt-5.6-luna",                    "https://api.openai.com/v1"),
        "together": ("TOGETHER_API_KEY", "meta-llama/Llama-3.3-70B-Instruct-Turbo",
                     "https://api.together.xyz/v1"),
    }
    env_var, default_model, base_url = PROVIDERS[args.provider]
    model = args.model or default_model
    key = os.getenv(env_var)
    if not key:
        raise SystemExit(f"set {env_var}")

    vocab = json.loads(args.vocab.read_text())
    known = sorted({e["canonical"] for e in vocab})
    unmatched = json.loads((args.in_dir / "unmatched.json").read_text())[: args.top]

    out_path = args.in_dir / "llm_classified.json"
    results: dict[str, dict] = {}
    if args.resume and out_path.exists():
        results = {r["raw"]: r for r in json.loads(out_path.read_text())}
        print(f"resuming: {len(results):,} already classified")

    todo = [u for u in unmatched if u["raw"] not in results]
    print(f"classifying {len(todo):,} strings in batches of {BATCH_SIZE} "
          f"via {args.provider}/{model}\n")

    if args.provider == "gemini":
        def caller(prompt: str, k: str, m: str) -> str:
            return call_gemini(prompt, k, m)
    else:
        def caller(prompt: str, k: str, m: str) -> str:
            return call_openai_compatible(prompt, k, m, base_url)
    counts = {u["raw"]: u["count"] for u in unmatched}

    batches = [todo[i : i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]

    def run_batch(batch: list[dict]) -> list[dict]:
        prompt = PROMPT.format(
            categories=CATEGORIES,
            vocab=", ".join(known),
            items=json.dumps([b["raw"] for b in batch], indent=0),
        )
        for attempt in range(3):
            try:
                return parse_response(caller(prompt, key, model))
            except Exception as exc:
                if attempt == 2:
                    print(f"  batch failed after 3 tries ({type(exc).__name__}: {exc})")
                    return []
                time.sleep(2 * (attempt + 1))
        return []

    def absorb(rows: list[dict]) -> None:
        if not rows:
            print("    warning: batch returned no usable rows")
        for row in rows:
            raw = row.get("raw")
            if raw in counts:
                results[raw] = {
                    "raw": raw,
                    "count": counts[raw],
                    "category": row.get("category", "noise"),
                    "canonical": row.get("canonical") or None,
                }

    if args.workers > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_batch, b): b for b in batches}
            for n, fut in enumerate(as_completed(futures), start=1):
                absorb(fut.result())
                print(f"  batch {n:>4}/{len(batches)}  ({len(results):,} classified)")
                if n % 5 == 0:
                    out_path.write_text(json.dumps(list(results.values()), indent=1))
    else:
        for n, batch in enumerate(batches, start=1):
            absorb(run_batch(batch))
            print(f"  batch {n:>4}/{len(batches)}  ({len(results):,} classified)")
            out_path.write_text(json.dumps(list(results.values()), indent=1))
            time.sleep(0.4)

    rows = list(results.values())
    out_path.write_text(json.dumps(rows, indent=1))

    by_cat: dict[str, list] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)

    print(f"\nwrote {out_path}\n")
    print("category          strings     mentions")
    for cat, items in sorted(by_cat.items(), key=lambda kv: -sum(i["count"] for i in kv[1])):
        print(f"  {cat:<14} {len(items):>7,}  {sum(i['count'] for i in items):>10,}")

    tech = [r for r in rows if r["category"].startswith("tech")]
    new_terms = sorted({r["canonical"] for r in tech if r["canonical"] and r["canonical"] not in known})
    print(f"\n{len(new_terms)} canonical terms proposed beyond the survey vocabulary:")
    print("  " + ", ".join(new_terms[:60]))
    if len(new_terms) > 60:
        print(f"  ... and {len(new_terms) - 60} more")


if __name__ == "__main__":
    main()
