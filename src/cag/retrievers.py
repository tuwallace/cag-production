import re, sys, pathlib
from rank_bm25 import BM25Okapi
from .corpus import Doc

def _tok(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())

class BM25Retriever:
    """Self-contained lexical baseline (no services needed)."""
    def __init__(self, docs: list[Doc]):
        self.docs = docs
        self.bm25 = BM25Okapi([_tok(d.title + " " + d.text) for d in docs])

    def retrieve(self, question: str, k: int) -> list[Doc]:
        scores = self.bm25.get_scores(_tok(question))
        top = sorted(range(len(self.docs)), key=lambda i: -scores[i])[:k]
        return [self.docs[i] for i in top]

HELPDESK_ROOT = pathlib.Path(__file__).resolve().parents[3] / "helpdesk-rag"

class HelpdeskRagRetriever:
    """Calls the sibling helpdesk-rag project's own retrieval stack (hybrid + rerank).
    Needs Qdrant + Ollama running and the index built (`python -m rag.ingest` in helpdesk-rag).
    Retrieval only: generation is done by the same local model as CAG so only context differs."""
    def __init__(self, docs: list[Doc], use_rewrite: bool = False, use_rerank: bool = True):
        sys.path.insert(0, str(HELPDESK_ROOT / "src"))
        from rag.pipeline import retrieve_docs      # noqa: import deferred, heavy deps
        self._retrieve = retrieve_docs
        self._by_summary: dict[str, Doc] = {}
        for d in docs:
            self._by_summary.setdefault(d.title, d)
        self.opts = {"use_rewrite": use_rewrite, "use_rerank": use_rerank}

    def retrieve(self, question: str, k: int) -> list[Doc]:
        """helpdesk-rag returns ONE representative ticket per distinct problem (summary), from its full 1,000-ticket index.
        The cached subset holds different tickets of the same problems, so map each hit to a subset ticket with the same
        summary; relevance in this dataset is defined per problem, so that is the like-for-like comparison."""
        hits = self._retrieve(question, top_n=k * 5, **self.opts)
        out = [self._by_summary[h["summary"]] for h in hits if h["summary"] in self._by_summary]
        return out[:k]

class HybridRetriever:
    """BM25 + dense (nomic-embed-text via Ollama) fused with reciprocal rank fusion. The stronger RAG baseline.
    Document embeddings are cached on disk by content hash. Embeddings use OLLAMA_HOST (not CAG_OLLAMA_HOST)."""
    CACHE = pathlib.Path(__file__).resolve().parents[2] / "data" / ".embed_cache.json"

    def __init__(self, docs: list[Doc], model: str = "nomic-embed-text"):
        import json, hashlib, os, ollama
        self.docs, self.model, self.bm25 = docs, model, BM25Retriever(docs)
        self.client = ollama.Client(host=os.getenv("OLLAMA_HOST"))
        cache = json.loads(self.CACHE.read_text()) if self.CACHE.exists() else {}
        keys = [hashlib.sha256((model + d.title + d.text).encode()).hexdigest() for d in docs]
        todo = [i for i, k in enumerate(keys) if k not in cache]
        for j in range(0, len(todo), 16):
            batch = todo[j:j + 16]
            out = self.client.embed(model=model, input=["search_document: " + docs[i].title + "\n" + docs[i].text[:6000] for i in batch])
            for i, v in zip(batch, out["embeddings"]):
                cache[keys[i]] = v
        if todo:
            self.CACHE.write_text(json.dumps(cache))
        import numpy as np
        m = np.array([cache[k] for k in keys], dtype="float32")
        self.mat = m / np.linalg.norm(m, axis=1, keepdims=True)

    def retrieve(self, question: str, k: int) -> list[Doc]:
        import numpy as np
        q = np.array(self.client.embed(model=self.model, input=["search_query: " + question])["embeddings"][0], dtype="float32")
        dense = list(np.argsort(-(self.mat @ (q / np.linalg.norm(q)))))[:30]
        scores = self.bm25.bm25.get_scores(_tok(question))
        sparse = sorted(range(len(self.docs)), key=lambda i: -scores[i])[:30]
        fused: dict[int, float] = {}
        for ranking in (dense, sparse):
            for r, i in enumerate(ranking):
                fused[int(i)] = fused.get(int(i), 0.0) + 1 / (60 + r)
        return [self.docs[i] for i in sorted(fused, key=lambda i: -fused[i])[:k]]
