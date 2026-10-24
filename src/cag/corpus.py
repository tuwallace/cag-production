"""Deterministic corpus assembly. The output text is the cached prefix, so it must be byte-stable."""
import hashlib, json
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    text: str

def render_doc(d: Doc) -> str:
    return f'<doc id="{d.id}" title="{d.title}">\n{d.text.strip()}\n</doc>'

def estimate_tokens(text: str) -> int:
    """Rough chars/4 estimate. Use LLM.count_tokens for the real number before launch."""
    return len(text) // 4

@dataclass(frozen=True)
class Corpus:
    text: str
    sha: str
    n_docs: int
    est_tokens: int
    ids: frozenset

    def manifest(self) -> dict:
        return {"sha": self.sha, "n_docs": self.n_docs, "est_tokens": self.est_tokens}

def build_corpus(docs: list[Doc]) -> Corpus:
    ordered = sorted(docs, key=lambda d: d.id)           # never shuffle: order is part of the cache key
    if len({d.id for d in ordered}) != len(ordered):
        raise ValueError("duplicate doc ids")
    text = "\n\n".join(render_doc(d) for d in ordered)
    sha = hashlib.sha256(text.encode()).hexdigest()[:16]
    return Corpus(text, sha, len(ordered), estimate_tokens(text), frozenset(d.id for d in ordered))

def check_budget(corpus: Corpus, context_window: int = 200_000, ratio: float = 0.5, reserve: int = 2_000) -> None:
    """Fail loudly if the corpus would crowd out the question, history and answer."""
    limit = int(context_window * ratio)
    if corpus.est_tokens + reserve > limit:
        raise ValueError(f"corpus ~{corpus.est_tokens} tokens exceeds budget {limit} "
                         f"({ratio:.0%} of {context_window}); trim it or use RAG/hybrid")

def write_version(corpus: Corpus, outdir) -> None:
    from pathlib import Path
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    (out / f"corpus-{corpus.sha}.txt").write_text(corpus.text)
    (out / f"corpus-{corpus.sha}.manifest.json").write_text(json.dumps(corpus.manifest(), indent=2))
