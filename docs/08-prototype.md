# 08. Prototype: CAG vs RAG on a local LLM (Ollama + ollmcp)

Everything runs locally: **no Claude API calls**. Code is in `src/cag/`; Python 3.12 via `uv`, same convention as `../helpdesk-rag`.

## Design

One local model (`qwen3:8b`), one instruction prompt, one citation format. **Only the context differs**:

| System | Context | KV cache |
|---|---|---|
| `cag` | entire corpus in the system message (byte-identical every call) | Ollama reuses the cached prefix; only the question is prefilled |
| `rag` | top-k retrieved docs in the system message | new prefix every call, so full prefill each time |

| Dataset | Corpus | Gold | RAG retriever | Metrics |
|---|---|---|---|---|
| `helpdesk` | first `--max-docs` tickets from helpdesk-rag, built as its `ingest.py` does (public comments only) | `eval/golden.jsonl` ids intersected with the subset; questions left with no gold are dropped | `bm25` (no services) or **helpdesk-rag's hybrid + rerank** | citation hit/precision, retrieval hit@k |
| `squad` | first K SQuAD-train articles, one doc per paragraph | paragraph holding the answer | BM25 | contains-answer, F1, citation hit |

### Optional dependency: helpdesk-rag

The `helpdesk` dataset adapter and `--baseline helpdesk-rag` use the sibling project [helpdesk-rag](https://github.com/tuwallace/helpdesk-rag) (MIT, a separate repository).
It is **not included here**. To use that part: clone it next to this repository as `../helpdesk-rag`, follow its README to download the data and build its Qdrant index, and run
`uv sync --python 3.12 --group helpdesk` here. Even `--baseline bm25` reads the ticket CSVs from `../helpdesk-rag/data/raw`.
The ticket dataset it uses (`mindweave/help-desk-tickets`) is CC-BY-NC-4.0 (non-commercial) and is not redistributed in this repository.
Everything else runs without it: the docs-QA evaluation (the main results), the SQuAD adapter, the unit tests, the regression gate and the service.

## Setup

```bash
cd cag-production
cp .env.example .env
uv sync --python 3.12
PYTHONPATH=src uv run pytest          # 8 offline tests, fake LLM
ollama pull qwen3:8b                  # already present on this machine
```

Recommended Ollama server settings (set where `ollama serve` is launched; restart it):
`OLLAMA_NUM_PARALLEL=1` (one KV slot, so every request hits the warm cache), `OLLAMA_FLASH_ATTENTION=1`,
`OLLAMA_KV_CACHE_TYPE=q8_0` (about half the KV memory; check quality), `OLLAMA_KEEP_ALIVE=60m`.

## Run the eval

```bash
# helpdesk subset, BM25 baseline (no Qdrant needed)
PYTHONPATH=src uv run python -m cag.evaluate --dataset helpdesk --baseline bm25 --max-docs 150 --n 20

# helpdesk vs helpdesk-rag's real retrieval (needs `docker compose up -d`, index built, and `uv sync --group helpdesk`)
PYTHONPATH=src uv run python -m cag.evaluate --dataset helpdesk --baseline helpdesk-rag --max-docs 150 --n 20

# SQuAD (downloads rajpurkar/squad from Hugging Face on first run)
PYTHONPATH=src uv run python -m cag.evaluate --dataset squad --articles 3 --n 50
```

Reports go to `reports/` (JSON + markdown). Stop the model first (`ollama stop qwen3:8b`) if you want a truly cold first call.

## ollmcp

`mcp.json` registers a `cag` MCP server (tools `ask_knowledge_base`, `knowledge_base_info`). Start from the project root:

```bash
ollmcp --servers-json mcp.json --model qwen3:8b-16k
```

Use a **different model name** for ollmcp than `CAG_MODEL`. Same name with a different `num_ctx` makes Ollama reload the
model on every hop and discards the KV cache. The server prefills the corpus in a background thread at startup;
the first question may wait for it.

## Measured on this machine (M2 Pro, 32 GB, qwen3:8b Q4_K_M, num_ctx 32768)

| Observation | Value |
|---|---|
| Corpus (150 tickets) | ~16k tokens (prompt_eval_count 14,864) |
| Cold prefill | **65.7 s** |
| Warm prefill (same prefix, new question) | **0.22-0.30 s** |
| Model memory at num_ctx 32768 | ~9.9 GB (all in GPU/unified) |
| Mean prefill, RAG (~600 tokens, no reuse) | ~1.7 s |
| p50 total latency, CAG vs RAG (8 questions) | 4.3-7.5 s vs 2.1 s: CAG decodes slower with a 15k-token context and writes longer answers |

Takeaway: the cache removes prefill cost but not decode cost. On this hardware CAG is **not** faster end to end than a small-context RAG;
it wins on prefill and removes retrieval errors, not on total latency.
Quality at n=8 is noise (cite_hit 0.25-0.38 for both); run n >= 25 before concluding anything.

### SQuAD result (1 article, 55 paragraphs, ~13.6k tokens, n=25, qwen3:8b, BM25 top-5)

| system | contains | F1 | cite hit | p50 s | mean prefill s | cache hit |
|---|---|---|---|---|---|---|
| cag | 0.84 | 0.27 | 0.80 | 1.5 | 0.22 | 0.996 |
| rag | 0.84 | 0.26 | 0.84 | 4.8 | 3.7 | 0 |

Three articles (~38k tokens) did not fit the 32k window, so the paper's k=3 setup was cut to one article. Accuracy is a tie at n=25
(a difference of 1 question is 4 points). Here CAG is faster end to end because answers are short, so prefill dominates; on the
helpdesk run, longer answers made decode dominate. One article is an easy case for BM25; RAG's gap should widen with more documents.

## Gotchas found while building this

- **`prompt_eval_count` includes cached tokens.** Cache hits show up only as a tiny `prompt_eval_duration`.
  `OllamaLLM` infers reuse from prefill speed against a calibrated cold rate (persisted in `reports/.prefill_rate.json`), so reuse numbers are inferred, not reported by Ollama.
- **Ollama truncates silently** when the prompt exceeds `num_ctx`. `OllamaLLM` raises `ContextOverflow` at 95% fill; `check_budget` rejects corpora over 70% of `num_ctx`.
- **Corpus size is the binding constraint.** All 1,000 tickets are ~103k tokens, beyond qwen3:8b's 32-40k window, so the helpdesk adapter caches the first `--max-docs` tickets (150 fits; 200 does not at the default budget).
  Using all 1,000 needs a long-context local model plus the memory for its KV cache.
- **Changing `num_ctx`, the model, or any byte of the prefix is a cold start (about a minute here).**
- The citation-format example in the prompt is taken from a real doc id; a hard-coded example id was copied verbatim by the model.
- Questions run sequentially; one Ollama slot means concurrent requests would queue or evict the cache.

## Helpdesk vs helpdesk-rag's real retriever (150 tickets, 17 questions, qwen3:8b)

| system | cite hit | no-answer | p50 s | mean prefill s |
|---|---|---|---|---|
| cag | 0.41 | 0.35 | 4.7 | 0.27 |
| rag (helpdesk-rag hybrid + rerank, one ticket per problem) | **0.88** | 0.12 | 3.2 | 0.87 |

helpdesk-rag returns one representative ticket per distinct problem, from its full index. Those tickets are not in the cached
150, so hits are mapped to a cached ticket with the same summary (relevance in this dataset is per problem). Without that mapping RAG scored 0.12, an artifact, not a result.
The 8B model gets lost in 150 near-duplicate tickets and often answers "not in the knowledge base"; the retriever's dedupe does that work for RAG.

## Headless ollmcp-style check (`scripts/mcp_check.py`)

Chat model `qwen3:8b-16k` sees the tool schema and decides whether to call `ask_knowledge_base`. 3/3 IT questions called the tool;
3/3 non-IT questions (greeting, arithmetic, thanks) did not. This is a stand-in for an interactive ollmcp session (same method as helpdesk-rag's `23_mcp_test.py`); the interactive TUI itself was not driven.

**Eviction finding:** with a single Ollama server, loading the chat model evicted the CAG model, and the next two tool calls paid a 65 s cold prefill (cache lost).
Fix: run CAG on a **dedicated Ollama instance** on its own port:

```bash
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_NUM_PARALLEL=1 OLLAMA_FLASH_ATTENTION=1 ollama serve
```
and set `CAG_OLLAMA_HOST=http://127.0.0.1:11435` in `.env`. After that, all three tool calls reused ~14.8k cached tokens (0.24 s prefill).
Note the `ollama` CLI on PATH (0.35.1) is an older version than the desktop app's server (0.40.6); both worked.

## Status

- Verified: offline tests; live CAG vs RAG evals (helpdesk with BM25 and with helpdesk-rag retrieval, SQuAD 1 article); MCP server through fastmcp and a headless tool-calling loop; cache survives when CAG has a dedicated Ollama instance.
- Added later: docs-QA eval with saved per-question outputs, a quote-style prompt, and a closed-book control (doc 09).
- Not verified: an interactive ollmcp TUI session; corpora larger than the 32k window; n > 25 questions.
