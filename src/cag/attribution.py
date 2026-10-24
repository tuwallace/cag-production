"""System-side citations. Instead of trusting chunk ids the model writes, find the chunks that support the ANSWER after generation:
score every chunk against the answer text (and any quoted text) with BM25 and keep the top chunks that score close to the best.
Also reports `support`: the share of the answer's content words found in the attributed chunks, a cheap groundedness signal."""
import re
from dataclasses import dataclass
from rank_bm25 import BM25Okapi
from .corpus import Doc
from .systems import parse_answer, parse_quotes, _terms

_tok = lambda s: re.findall(r"[a-z0-9_]+", s.lower())

@dataclass
class Attribution:
    ids: list          # best first
    scores: list
    support: float     # 0..1, answer content words present in the attributed chunks (lexical)
    sem: float = 0.0   # best cosine between the answer and an attributed chunk (semantic; hybrid/rerank modes only)

class Attributor:
    def __init__(self, docs: list[Doc], k: int = 3, rel: float = 0.6, use_question: bool = False):
        self.docs, self.k, self.rel, self.use_question = docs, k, rel, use_question
        self.text = {d.id: d.title + " " + d.text for d in docs}
        self.ids = [d.id for d in docs]
        self.bm25 = BM25Okapi([_tok(self.text[i]) for i in self.ids])
        self.terms = {i: _terms(self.text[i]) for i in self.ids}

    def _scores(self, final: str, quoted: str, question: str):
        return self.bm25.get_scores(_tok(final + " " + quoted + (" " + question if self.use_question else "")))

    def attribute(self, answer_text: str, question: str = "") -> Attribution:
        final = parse_answer(answer_text)
        if final.strip().lower().startswith("not in the knowledge base"):
            return Attribution([], [], 0.0)
        quoted = " ".join(q for q, _ in parse_quotes(answer_text, lenient=True))
        scores = self._scores(final, quoted, question)
        order = sorted(range(len(self.ids)), key=lambda j: -scores[j])[: self.k]
        best = scores[order[0]] if order else 0.0
        if best <= 0:
            return Attribution([], [], 0.0)
        keep = [j for j in order if scores[j] >= self.rel * best]
        aterms = _terms(final)
        covered = set().union(*(self.terms[self.ids[j]] for j in keep)) if keep else set()
        support = len(aterms & covered) / len(aterms) if aterms else 0.0
        return Attribution([self.ids[j] for j in keep], [float(scores[j]) for j in keep], support,
                           self._sem(final, keep))

    def _sem(self, final, keep):
        return 0.0

class SemanticAttributor(Attributor):
    """Dense + BM25 attribution so answers that reword the docs still find their source.
    mode "dense": cosine only. "hybrid": alpha * (BM25 / best BM25) + (1 - alpha) * min-max cosine. "rerank": hybrid shortlist of 8,
    then a cross-encoder (bge-reranker-base) scores (answer, chunk); kept chunks must reach rel * best sigmoid score.
    Embeddings are nomic-embed-text through Ollama (OLLAMA_HOST), cached on disk by HybridRetriever."""
    def __init__(self, docs: list[Doc], mode: str = "hybrid", k: int = 3, rel: float = 0.6, alpha: float = 0.5, use_question: bool = False):
        super().__init__(docs, k, rel, use_question)
        from .retrievers import HybridRetriever
        self.mode, self.alpha = mode, alpha
        self.hr = HybridRetriever(docs)                      # embeds + caches chunk vectors
        self._ce = None

    def _dense(self, final: str, quoted: str):
        import numpy as np
        q = np.array(self.hr.client.embed(model=self.hr.model, input=["search_query: " + (final + " " + quoted).strip()[:3000]])["embeddings"][0], dtype="float32")
        return self.hr.mat @ (q / np.linalg.norm(q))

    def _scores(self, final: str, quoted: str, question: str):
        import numpy as np
        self._last_cos = cos = self._dense(final, quoted)
        if self.mode == "dense":
            return cos - cos.min()                            # shift so relative thresholds mean something
        bm = super()._scores(final, quoted, question)
        b = bm / bm.max() if bm.max() > 0 else bm
        d = (cos - cos.min()) / (cos.max() - cos.min() + 1e-9)
        hyb = self.alpha * b + (1 - self.alpha) * d
        if self.mode == "hybrid":
            return hyb
        from sentence_transformers import CrossEncoder
        if self._ce is None:
            self._ce = CrossEncoder("BAAI/bge-reranker-base", local_files_only=True)
        short = list(np.argsort(-hyb)[:8])
        logits = self._ce.predict([(final, self.text[self.ids[j]][:1800]) for j in short])
        out = np.zeros(len(self.ids))
        for j, lg in zip(short, logits):
            out[j] = 1 / (1 + np.exp(-lg))
        return out

    def _sem(self, final, keep):
        return float(max((self._last_cos[j] for j in keep), default=0.0))
