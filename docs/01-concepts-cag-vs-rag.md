# 01. Concepts: CAG vs RAG

## What CAG is

Proposed in "Don't Do RAG: When Cache-Augmented Generation is All You Need for Knowledge Tasks"
(arXiv 2412.15605). Three phases:

1. **Preload**: concatenate the knowledge base into one prompt prefix.
2. **Precompute**: run the model once over that prefix and keep the KV cache.
3. **Infer**: for each query, append only the question to the cached prefix and decode.
   Prefill cost for the corpus is paid once, not per query.

## Comparison

| Aspect | RAG | CAG |
|---|---|---|
| Per-query work | embed query, search, (rerank), build prompt | append question to cached prefix |
| Moving parts | chunker, embedder, vector DB, reranker | long-context LLM + cache layer |
| Retrieval errors | possible (missed or wrong chunks) | none: the model sees everything |
| Corpus size limit | effectively unbounded | must fit the context window |
| Freshness | incremental index updates | re-prefill (cache rebuild) on change |
| Latency | retrieval + prefill of retrieved chunks | low time-to-first-token on cache hit |
| Cost driver | retrieval infra + per-query tokens | GPU memory (self-host) or cached-read tokens (API) |
| Source filtering / ACLs per doc | natural | hard: everyone shares the cached prefix |
| Attribution | chunk-level | needs doc IDs in the prompt + citation prompting |

## Decision rule

Use CAG when **all** hold:
- Corpus fits comfortably in context (rule of thumb: <= 50% of the window, leaving room for question, answer and reasoning).
- Corpus changes rarely (daily or slower, or in versioned releases).
- Many queries hit the same corpus (cache amortization).
- All users may see all documents.

Use RAG when the corpus is large, volatile, or needs per-user access control.
Use a **hybrid** when part of it is stable (cache it) and part is large or fresh (retrieve it).

## Known limitations

- Quality can degrade on very long contexts ("lost in the middle"); test, don't assume.
- Cache is tied to the exact model and exact prefix bytes. Any change invalidates it.
- Managed APIs do not expose the raw KV cache; you rely on their prompt caching.
