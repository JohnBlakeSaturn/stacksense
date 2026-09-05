"""
Step 3: resume analyser.

Turns a resume into canonical skills so it becomes an input path into the
recommender rather than a separate feature. Output feeds the same hybrid scorer
and role gap analysis as a hand-entered skill list.

Three things drove the design, all visible in real resumes:

  Skills live in two places. An explicit skills block lists them directly, but
  project and experience bullets carry as many again, embedded in prose --
  "implemented a sliding window-based flow control algorithm with Go-Back-N ARQ"
  names a skill without any list to parse. Reading only the skills section
  misses roughly half of what a resume demonstrates.

  Where a skill appears is evidence about how well it is known. Named in a dated
  project with implementation detail is demonstrated; listed in a comma-separated
  skills dump is claimed; appearing under coursework is exposure. The weighting
  reflects that, but stays mild: a demonstrated skill counts 1.0 and a
  coursework mention 0.6, not 1.0 against 0.1. Someone who has taken a compilers
  course does know something about compilers.

  Fresher resumes carry their signal in projects rather than employment, so
  projects are treated as first-class evidence, not as an afterthought behind an
  experience section that may not exist.

Matching runs exact, then normalised, then embedding similarity, against the
canonical vocabulary built earlier. Terms the vocabulary does not contain are
reported rather than dropped: academic and systems vocabulary ("B+ tree
indexing", "predictive parser") rarely appears in job postings, and silently
discarding it would misrepresent the resume.

Usage:
    python resume_analyze.py --file cv.pdf
    python resume_analyze.py --file cv.pdf --json out.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

# Section weights. Deliberately compressed: the gap between demonstrating a
# skill and merely listing it is real but not enormous, and over-weighting
# projects would let a single hobby project outrank years of listed experience.
SECTION_WEIGHT = {
    "experience": 1.00,
    "projects": 1.00,
    "skills": 0.85,
    "achievements": 0.75,
    "coursework": 0.60,
    "education": 0.60,
    "other": 0.70,
}

# Header patterns, matched against short all-caps or title-case lines.
SECTION_PATTERNS: list[tuple[str, str]] = [
    ("experience", r"experience|employment|work history|internship|professional"),
    ("projects", r"projects?|portfolio|personal work"),
    ("skills", r"skills?|expertise|technical|technolog|competenc|proficien"),
    ("education", r"education|academic|qualification"),
    ("coursework", r"coursework|courses|curriculum|subjects"),
    ("achievements", r"achievement|award|honou?r|certification|competition|conference"),
]

# Words that are common English first and technology names second. Matching
# them from prose produces skills the candidate never claimed: "Engineering"
# from a college name, "Architecture" from "multi-tab shell architecture",
# "Stack Overflow" from the name of a dataset they analysed.
GENERIC = {
    # Bare organisational and structural words only. Domain terms like
    # "machine learning" or "object detection" were in this list initially and
    # that was wrong -- they are real skills, and blocking them outside the
    # skills section cost 17 legitimate matches from the projects section.
    "engineering", "computing", "architecture", "analytics", "graphics",
    "programming", "linear", "audio", "monitoring", "simulation", "design",
    "development", "software", "systems", "system", "data", "web",
    "accessibility", "performance", "documentation", "research", "analysis",
    "mathematics", "stack overflow", "programming languages",
    "web technologies", "backend services", "databases",
}


# Spellings a resume uses that the posting-derived vocabulary stores
# differently. These are naming differences, not missing technologies.
RESUME_ALIASES = {
    "express.js": "Express",
    "expressjs": "Express",
    "unity": "Unity 3D",
    "jupyter notebook": "Jupyter Nb/JupyterLab",
    "jupyter": "Jupyter Nb/JupyterLab",
    "google colab": "Jupyter Nb/JupyterLab",
    "node": "Node.js",
    "nodejs": "Node.js",
    "postgres": "PostgreSQL",
    "js": "JavaScript",
    "ts": "TypeScript",
    "k8s": "Kubernetes",
    "sklearn": "Scikit-Learn",
    "tf": "TensorFlow",
    "cv2": "Opencv",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
}


# A generic term is only credited when it appears in a section that lists
# skills or coursework outright, where the candidate is naming it deliberately
# rather than using it as ordinary prose.
GENERIC_OK_SECTIONS = {"skills", "coursework"}

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "using", "via", "by", "at", "as", "is", "was", "were", "be", "been",
    "from", "into", "over", "under", "this", "that", "these", "those", "it",
    "its", "prof", "dr", "project", "built", "designed", "developed",
    "implemented", "achieved", "performed", "conducted", "created", "used",
    "study", "based", "real", "time", "custom", "advanced", "multi", "core",
}


# Resumes often mark weaker skills with an asterisk and a footnote.
ELEMENTARY_MARK = re.compile(r"\*")


# ------------------------------------------------------------------ extraction
def read_pdf(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        raise SystemExit("pip install pdfplumber")
    out = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text() or "")
    return "\n".join(out)


def read_docx(path: Path) -> str:
    try:
        import docx
    except ImportError:
        raise SystemExit("pip install python-docx")
    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs]
    # tables are common in resume templates and paragraphs alone would miss them
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf(path)
    if suffix in {".docx", ".doc"}:
        return read_docx(path)
    return path.read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------- segmentation
def looks_like_header(line: str) -> bool:
    """Headers are short, mostly uppercase or title case, and carry no sentence
    punctuation. Checked before pattern matching so a bullet mentioning the word
    "projects" is not mistaken for a section break."""
    s = line.strip()
    if not (2 < len(s) < 60):
        return False
    if s.endswith((".", ",", ";", ":")) and len(s.split()) > 4:
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(c.isupper() for c in letters) / len(letters)
    return upper_ratio > 0.6 or s.istitle()


def segment(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = defaultdict(list)
    current = "other"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if looks_like_header(line):
            low = line.lower()
            matched = False
            for name, pattern in SECTION_PATTERNS:
                if re.search(pattern, low):
                    current = name
                    matched = True
                    break
            if matched:
                continue
            # An unrecognised header-shaped line is usually a company, employer
            # or project title rather than a section break -- "Government College
            # of Engineering and Ceramic Technology" reads exactly like a header.
            # Keeping the current section means its bullets stay attributed to
            # the right place instead of falling into "other".
        sections[current].append(line)
    return dict(sections)


# ------------------------------------------------------------------- matching
def normalize(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9+#./ ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ", "").rstrip(".")


def build_index(vocab: list[dict]) -> tuple[dict, list[str]]:
    """Index canonical names, and also index each half of a slash-compound.

    The survey asks about HTML and CSS jointly, so the vocabulary holds a single
    "HTML/CSS" node. A resume lists them separately, and neither half matches
    the compound key, so both would be missed without this."""
    by_norm = {}
    for spelling, canonical in RESUME_ALIASES.items():
        by_norm[normalize(spelling)] = canonical
    for entry in vocab:
        name = entry["canonical"]
        by_norm.setdefault(normalize(name), name)
        bare = re.sub(r"\(.*?\)", "", name).strip()
        if "/" in bare and not bare.startswith("."):
            for part in bare.split("/"):
                part = part.strip()
                if len(part) > 1:
                    by_norm.setdefault(normalize(part), name)
    return by_norm, [e["canonical"] for e in vocab]


def candidate_spans(line: str) -> list[str]:
    """Pull plausible skill mentions out of a line.

    Skills-section lines are delimited lists, so splitting on separators works.
    Prose bullets are not, so n-grams up to length four are also emitted and
    left for the matcher to accept or reject."""
    spans: list[str] = []
    line = re.sub(r"^[\u2022\-\*\u25cf\u25aa]\s*", "", line)

    for part in re.split(r"[,;|]|\s{2,}", line):
        part = part.strip(" .:")
        if 1 < len(part) < 40:
            spans.append(part)

    words = re.findall(r"[A-Za-z0-9+#.\-]+", line)
    for n in (1, 2, 3, 4):
        for i in range(len(words) - n + 1):
            chunk = words[i:i + n]
            # a span that starts or ends on a stopword is a fragment of a
            # sentence, not a name
            if chunk[0].lower() in STOPWORDS or chunk[-1].lower() in STOPWORDS:
                continue
            span = " ".join(chunk)
            if 1 < len(span) < 40:
                spans.append(span)
    return spans


def extract_skills(sections: dict[str, list[str]], by_norm: dict,
                   names: list[str], use_embeddings: bool,
                   threshold: float) -> tuple[dict, list]:
    found: dict[str, dict] = {}
    unmatched: dict[str, int] = defaultdict(int)

    for section, lines in sections.items():
        weight = SECTION_WEIGHT.get(section, SECTION_WEIGHT["other"])
        for line in lines:
            elementary = bool(ELEMENTARY_MARK.search(line))
            for span in candidate_spans(line):
                canonical = by_norm.get(normalize(span))
                if canonical and canonical.lower() in GENERIC and section not in GENERIC_OK_SECTIONS:
                    continue
                if canonical:
                    prior = found.get(canonical)
                    score = weight * (0.75 if elementary else 1.0)
                    if prior is None or score > prior["weight"]:
                        found[canonical] = {
                            "weight": round(score, 3),
                            "section": section,
                            "matched_text": span,
                            "elementary": elementary,
                        }
                elif (len(span.split()) <= 3 and any(c.isalpha() for c in span)
                      and span.lower() not in STOPWORDS and len(span) > 2):
                    unmatched[span.strip()] += 1

    # Embedding pass over the frequent unmatched spans only. Running it over
    # every n-gram would match arbitrary prose to the nearest technology name.
    if use_embeddings and unmatched:
        from sentence_transformers import SentenceTransformer, util

        candidates = [s for s, n in unmatched.items() if n >= 1 and len(s) > 2][:400]
        if candidates:
            model = SentenceTransformer("all-MiniLM-L6-v2")
            cv = model.encode(candidates, normalize_embeddings=True, batch_size=128)
            nv = model.encode(names, normalize_embeddings=True, batch_size=256)
            sims = util.cos_sim(cv, nv)
            best, idx = sims.max(dim=1)
            for span, score, j in zip(candidates, best.tolist(), idx.tolist()):
                if score >= threshold:
                    canonical = names[j]
                    if canonical not in found:
                        found[canonical] = {
                            "weight": round(SECTION_WEIGHT["other"] * 0.8, 3),
                            "section": "inferred",
                            "matched_text": span,
                            "elementary": False,
                            "similarity": round(score, 3),
                        }
                    unmatched.pop(span, None)

    ranked = sorted(unmatched.items(), key=lambda kv: -kv[1])
    return found, ranked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, required=True)
    ap.add_argument("--vocab", type=Path, default=Path("day1_out/final_vocab.json"))
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--embed", action="store_true",
                    help="second pass matching unmatched spans by similarity")
    ap.add_argument("--threshold", type=float, default=0.80,
                    help="cosine floor for the embedding pass; kept high because "
                         "loose matching turns prose into spurious skills")
    ap.add_argument("--show-unmatched", type=int, default=30)
    args = ap.parse_args()

    vocab = json.loads(args.vocab.read_text())
    by_norm, names = build_index(vocab)
    print(f"vocabulary {len(names):,} canonical skills")

    text = read_text(args.file)
    print(f"extracted {len(text):,} characters from {args.file.name}")

    sections = segment(text)
    print(f"\n--- sections ---")
    for name, lines in sorted(sections.items(), key=lambda kv: -len(kv[1])):
        print(f"  {name:<14} {len(lines):>3} lines   weight "
              f"{SECTION_WEIGHT.get(name, SECTION_WEIGHT['other']):.2f}")

    found, unmatched = extract_skills(sections, by_norm, names,
                                      args.embed, args.threshold)
    print(f"\nmatched {len(found)} canonical skills")

    by_section: dict[str, list] = defaultdict(list)
    for skill, meta in found.items():
        by_section[meta["section"]].append((skill, meta))

    print("\n--- skills by evidence ---")
    for section in sorted(by_section, key=lambda s: -SECTION_WEIGHT.get(s, 0.7)):
        items = sorted(by_section[section], key=lambda kv: -kv[1]["weight"])
        print(f"\n  {section}  (weight {SECTION_WEIGHT.get(section, 0.7):.2f})")
        for skill, meta in items:
            mark = " *elementary" if meta["elementary"] else ""
            sim = f"  ~{meta['similarity']}" if "similarity" in meta else ""
            print(f"    {meta['weight']:.2f}  {skill:<34} <- \"{meta['matched_text']}\"{mark}{sim}")

    if args.show_unmatched:
        print(f"\n--- top unmatched spans ---")
        print("  (terms the vocabulary does not cover; academic and systems")
        print("   vocabulary rarely appears in job postings)")
        for span, n in unmatched[:args.show_unmatched]:
            print(f"    {n:>2}x  {span}")

    if args.json:
        args.json.write_text(json.dumps({
            "file": str(args.file),
            "sections": {k: len(v) for k, v in sections.items()},
            "skills": found,
            "unmatched": [{"text": s, "count": n} for s, n in unmatched[:200]],
        }, indent=1))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()