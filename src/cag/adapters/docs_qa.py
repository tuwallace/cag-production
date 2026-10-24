"""Ollama documentation slice (MIT licensed, github.com/ollama/ollama/docs) with a hand-written golden set.
Docs are the section-level chunks (split at '## ', or '### ' for files without '## '); CAG caches all of them,
RAG retrieves top-k. Questions: eval/docs_qa.jsonl, gold given as 'file#heading prefix' and resolved to chunk ids."""
import json, re, pathlib
from ..corpus import Doc
from ..retrievers import HybridRetriever
from . import Dataset, Example

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOCS = ROOT / "data" / "ollama-docs"
QUESTIONS = ROOT / "eval" / "docs_qa.jsonl"          # the original 40 ("dev")
QUESTIONS_NEW = ROOT / "eval" / "docs_qa_new.jsonl"  # 50 held-out questions, written after the gate was tuned ("new")

def _clean(text: str) -> str:
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)          # frontmatter
    text = re.sub(r"<img[^>]*>|!\[[^\]]*\]\([^)]*\)", "", text)          # images
    text = re.sub(r"</?(Note|Info|Card|CodeGroup)[^>]*>", "", text)      # MDX wrappers, keep content
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def chunk_file(path: pathlib.Path) -> list[tuple[str, str]]:
    text = _clean(path.read_text())
    level = "## " if re.search(r"^## ", text, re.M) else "### "
    parts = re.split(rf"^(?={re.escape(level)})", text, flags=re.M)
    out = []
    for p in parts:
        p = p.strip()
        if len(p) < 40:
            continue
        head = p.splitlines()[0].lstrip("# ").strip() if p.startswith("#") else "(intro)"
        out.append((re.sub(r"\s*\{#.*?\}", "", head), p))
    return out

def load_docs() -> list[Doc]:
    docs = []
    for path in sorted(DOCS.glob("*.md*")):
        for i, (head, body) in enumerate(chunk_file(path)):
            docs.append(Doc(f"{path.stem}-{i:02d}", f"{path.stem}: {head}", body))
    return docs

def resolve(spec: str, docs: list[Doc]) -> set:
    f, _, head = spec.partition("#")
    hit = {d.id for d in docs if d.title.startswith(f"{f}: ") and d.title[len(f) + 2:].lower().startswith(head.lower())}
    if not hit:
        raise ValueError(f"gold spec matches no chunk: {spec}")
    return hit

def build(n_questions: int = 100, hybrid: bool = True, split: str = "dev") -> Dataset:
    docs = load_docs()
    examples = []
    files = {"dev": [QUESTIONS], "new": [QUESTIONS_NEW], "all": [QUESTIONS, QUESTIONS_NEW]}[split]
    for line in [l for f in files for l in f.read_text().splitlines()]:
        if not line.strip():
            continue
        q = json.loads(line)
        gold = set().union(*(resolve(g, docs) for g in q.get("gold", []))) if q.get("gold") else set()
        examples.append(Example(q["q"], gold, q.get("any", []), q.get("all", []), q["type"]))
    return Dataset(f"docs-qa-{len(docs)}c", docs, examples[:n_questions], HybridRetriever(docs) if hybrid else None)
