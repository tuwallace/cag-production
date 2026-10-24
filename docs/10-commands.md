# 10. Command reference

Every command used so far, grouped by task. Run from `cag-production/` unless a `cd` is shown.
`PYTHONPATH=src` is needed because the project is not installed as a package (same convention as `../helpdesk-rag`).

## 1. Setup

| Command | What it does |
|---|---|
| `cp .env.example .env` | Create local settings (Ollama host, model, context size). No secrets are needed. |
| `uv sync --python 3.12` | Create `.venv` and install dependencies (ollama, fastmcp, rank-bm25, fastapi, datasets...). |
| `uv sync --python 3.12 --group helpdesk` | Also install what helpdesk-rag's retriever imports (qdrant-client, sentence-transformers, OpenTelemetry). Large download. |
| `PYTHONPATH=src uv run pytest -q` | Run the 95 offline tests (fake LLM; no Ollama needed). |

## 2. Ollama

| Command | What it does |
|---|---|
| `ollama list` | Show installed models. |
| `ollama show qwen3:8b` | Show a model's context length, quantization and default parameters. |
| `ollama ps` | Show loaded models, their context size, and whether they sit on the GPU. |
| `ollama stop qwen3:8b` | Unload a model. The next call is a cold start, so the KV cache is empty. Use before a measurement that should start cold. |
| `curl -s localhost:11434/api/version` | Check the desktop Ollama server is up and see its version. |
| `OLLAMA_HOST=127.0.0.1:11435 OLLAMA_NUM_PARALLEL=1 OLLAMA_FLASH_ATTENTION=1 ollama serve` | Start the **dedicated CAG instance** on port 11435: one KV slot, flash attention. Keeps the chat model from evicting the cached corpus. Restart it if it dies (it did overnight once). |
| `OLLAMA_HOST=127.0.0.1:11435 ollama ps` / `... ollama stop qwen3:8b` | Inspect or unload on the dedicated instance. |
| `curl -s 127.0.0.1:11435/api/version` | Check the dedicated instance is up. |

The CAG code reads `CAG_OLLAMA_HOST` (set in `.env`); embeddings for the hybrid retriever use `OLLAMA_HOST`.

## 3. Data

| Command | What it does |
|---|---|
| `curl -s https://api.github.com/repos/ollama/ollama/contents/docs` | List the Ollama docs folder to pick files. |
| `curl -sf -O https://raw.githubusercontent.com/ollama/ollama/main/docs/<file>.mdx` | Download one doc into `data/ollama-docs/` (run from that folder). 15 files were used (MIT license, commit in `COMMIT.txt`). |
| `curl -s localhost:6333/collections/tickets` | Check helpdesk-rag's Qdrant index exists (1,000 points). |
| `cd ../helpdesk-rag && docker compose up -d` | Start Qdrant and Phoenix for the helpdesk-rag baseline (already running here). |

The SQuAD data downloads itself from Hugging Face the first time `--dataset squad` runs.

## 4. Evaluation (`cag.evaluate`)

Always prefix: `PYTHONPATH=src uv run python -m cag.evaluate ...`. Reports land in `reports/` (`.md` table, `.json` summary, `.answers.jsonl` per-question outputs).

| Command | What it does |
|---|---|
| `... --dataset squad --articles 1 --n 25` | CAG vs RAG (BM25) on a SQuAD subset. Use 1 article: 3 articles (~38k tokens) do not fit a 32k window. |
| `... --dataset helpdesk --baseline bm25 --max-docs 150 --n 8` | Helpdesk tickets, RAG = BM25. No Qdrant needed. `--max-docs` caps the cached tickets so they fit. |
| `... --dataset helpdesk --baseline helpdesk-rag --max-docs 150 --n 26` | Same, RAG = helpdesk-rag's hybrid + rerank retrieval (needs Qdrant, Ollama, the `helpdesk` group). |
| `python3 scripts/make_heldout.py` | Regenerate `eval/docs_qa_new.jsonl` (50 held-out questions): 10 answerable and 40 unanswerable ones, dropping any candidate whose key terms appear in the corpus. |
| `... --dataset docs --split new --n 50 --window 40960 --prompt quote --max-tokens 450 --systems cag,rag` | The same eval on the held-out split (`--split dev` = original 40, `new` = 50 held-out, `all` = 90). |
| `... --dataset docs --n 40 --window 40960 --k 5` | Ollama-docs QA (118 chunks, ~25k tokens, 40 golden questions) with the default "cite" prompt. |
| `... --dataset docs --n 40 --window 40960 --prompt quote --max-tokens 450 --systems cag,rag,closed_book` | Quote-then-answer prompt, plus the closed-book control (no documents). |
| `CAG_OLLAMA_HOST=http://127.0.0.1:11435 ... --dataset docs --n 40 --model qwen2.5:32b-instruct-q4_K_M --window 32768 --ratio 0.85 --prompt quote --max-tokens 450 --systems cag,rag,closed_book --verify` | The 32B run: native 32k window, so a higher `--ratio`. Start the dedicated instance with `OLLAMA_KV_CACHE_TYPE=q8_0` so it fits on the GPU. Cold prefill takes ~8.5 minutes; the whole run about 1.5 hours. |
| `... <above> --verify` | Also score verbatim-quote-gated copies of cag and rag (`cag+verify`, `rag+verify`). Needs `--prompt quote`. |

Flags: `--window` = Ollama `num_ctx` (must match `CAG_NUM_CTX`; changing it reloads the model and drops the cache), `--ratio` = share of the window the corpus may use (default 0.7), `--k` = chunks RAG retrieves, `--model` overrides `CAG_MODEL`.

## 5. Replay a gate over saved answers (no model calls)

| Command | What it does |
|---|---|
| `PYTHONPATH=src uv run python scripts/replay_verify.py reports/<run>.answers.jsonl [--lenient]` | Re-score saved answers under every gate policy: `strict`, `any_chunk`, `soft`, `soft_rel25`, `soft_rel50` (quote prompt) and `support50`, `support60` (system-side; work on any prompt). `--lenient` also accepts `> text [id]` quotes without quote marks (changes results; see doc 09 follow-up 4). Use a **quote-prompt** run; a cite-prompt run has no quotes and everything is rejected. |

| `PYTHONPATH=src uv run python scripts/replay_attribution.py reports/<run>.answers.jsonl [more...]` | Compare model-written citations with system-side attribution (and a question-only retrieval control) over saved answers. Also reports a `support` score. No model calls. |
| `PYTHONPATH=src uv run python scripts/make_paraphrases.py reports/<run>.answers.jsonl [...] > eval/paraphrases.jsonl` | Reword known-good answers at two levels with a local LLM (needs Ollama on `OLLAMA_HOST`) to stress-test attribution. |
| `PYTHONPATH=src uv run python scripts/replay_paraphrase.py eval/paraphrases.jsonl` | Score BM25, dense, hybrid and reranker attribution on original vs paraphrased answers, plus a question-only control. Needs Ollama (embeddings) and the cached `bge-reranker-base`. |
| `PYTHONPATH=src uv run python scripts/make_paraphrases.py --bad reports/<run>.answers.jsonl [...] > eval/paraphrases_bad.jsonl` | Reword the *fabricated* answers (non-refused answers to unanswerable questions): the negatives for a groundedness gate. |
| `PYTHONPATH=src uv run python scripts/replay_gate.py [reports/<run>.answers.jsonl ...]` | Compare lexical `support` and semantic `sem` as refusal signals: AUROC with bootstrap CI, thresholds fitted on originals and applied to rewordings, plus an in-sample end-to-end replay on the given runs. Needs Ollama (embeddings). |
| `PYTHONPATH=src uv run python scripts/replay_gate_heldout.py --pair 8B <dev>.answers.jsonl <new>.answers.jsonl [--pair 32B ... --fit-from 8B]` | Fit lexical and semantic gate thresholds on the dev questions' answers and test them, unchanged, on the held-out questions' answers (AUROC, kept/refused, end-to-end correctness). |
| `PYTHONPATH=src uv run python scripts/replay_verify.py <run>.answers.jsonl --lenient --split new` | Replay the quote/support gates on a held-out run (`--split` must match the split the answers came from). |
| `CAG_OLLAMA_HOST=http://127.0.0.1:11435 PYTHONPATH=src uv run python scripts/inject_test.py --model qwen3:8b --window 40960 --out reports/inject-8b.jsonl` | Prompt-injection test: the same 39 questions on a clean corpus and a corpus with five poisoned chunks (override, exfil link, false fact, prompt leak, no-refuse). Two cold prefills per run. For 32B use `--model qwen2.5:32b-instruct-q4_K_M --window 32768`. |
| `PYTHONPATH=src uv run python scripts/inject_report.py reports/inject-8b.jsonl [reports/inject-32b.jsonl]` | Attack success per payload, utility change, and four cheap output guards (URL allowlist, prompt-leak, lexical support, quote gate) with caught and false-positive counts. |
| `CAG_OLLAMA_HOST=http://127.0.0.1:11435 PYTHONPATH=src uv run python scripts/pii_test.py --model qwen3:8b --window 40960` | Live PII-leak test: plant fake PII and secrets in a chunk, ask for them, compare raw corpus, redacted corpus and output redaction. |

## 5b. Regression gate and shadow mode (phase 8)

| Command | What it does |
|---|---|
| `make gate-fast` (= `scripts/ci_gate.py fast --with-tests`) | Seconds, no model: unit tests, the corpus/question/prompt lock (`eval/corpus.lock.json`), token budget, gold specs. Run on every change. |
| `PYTHONPATH=src uv run python scripts/ci_gate.py replay --answers a.answers.jsonl b.answers.jsonl [--rag-answers ...]` | Check saved answers against `eval/gate.json` (exit 1 = fail). With `--rag-answers` also applies the CAG-minus-RAG checks. |
| `make gate-model` (= `CAG_OLLAMA_HOST=http://127.0.0.1:11435 scripts/ci_gate.py model --model qwen2.5:32b-instruct-q4_K_M --window 32768 --ratio 0.85 --prompt quote`) | Full docs eval (90 questions) on the production configuration, then the same checks. 30-60 min; start the dedicated Ollama with `OLLAMA_KV_CACHE_TYPE=q8_0` first. Saves `reports/gate-run-*.answers.jsonl` and `reports/gate-*.json`. |
| `PYTHONPATH=src uv run python scripts/ci_gate.py calibrate --answers ... --model ... --prompt quote` | Rewrite `eval/gate.json` from a baseline run (Wilson bounds, rounded outward to 0.05). Do this deliberately and record why. |
| `PYTHONPATH=src uv run python scripts/ci_gate.py update-lock` | Re-record the corpus/question/prompt hashes after a deliberate change and a passing model tier. |
| `PYTHONPATH=src uv run python scripts/shadow_run.py --model qwen3:8b --rag-host http://127.0.0.1:11434 --cag-host http://127.0.0.1:11435 --out reports/shadow-8b.jsonl [--interval 25]` | Live shadow run: RAG answers, CAG shadows in the background on a second Ollama server (one server has one cache slot). `--interval` paces requests so the candidate can keep up. |
| `PYTHONPATH=src uv run python scripts/shadow_report.py reports/shadow-8b.jsonl` | Agreement, disagreements, labelled correctness and the promotion criteria (exit 1 = hold). |
| `PYTHONPATH=src uv run python scripts/shadow_report.py --from-answers cag.answers.jsonl ... --rag rag.answers.jsonl ...` | The same analysis on two completed runs paired by question (no model needed). |

## 6. Service and MCP

| Command | What it does |
|---|---|
| `PYTHONPATH=src uv run uvicorn cag.service:app_factory --factory` | Start the FastAPI service (`/ask`, `/healthz`, `/readyz`, `/corpus`). Ready only after the cache is warm. Set `CAG_DATASET`, `CAG_MAX_DOCS`, `CAG_NUM_CTX` first. |
| `PYTHONPATH=src CAG_API_KEYS=alice:key1,bob:key2 CAG_URL_ALLOWLIST=ollama.com CAG_DATASET=docs CAG_MODEL=qwen2.5:32b-instruct-q4_K_M CAG_NUM_CTX=32768 CAG_BUDGET_RATIO=0.85 CAG_PROMPT=cite uv run uvicorn cag.service:app_factory --factory --port 8000` | Run the hardened service on the docs corpus with the 32B model (~8 minutes to become ready on a cold cache; `/healthz` answers meanwhile). Use `CAG_AUTH_DISABLED=1` instead of keys for local experiments. Call it with `curl -H 'X-API-Key: key1' -d '{"question":"..."}' -H 'Content-Type: application/json' localhost:8000/ask`. |
| `PYTHONPATH=src uv run python scripts/load_test.py --base http://127.0.0.1:8000 --levels 1,4,8,16 --keys key1,key2 [--retries 4] --out reports/load.json` | Wait for readiness, check 401s and hostile inputs, then a concurrency sweep; reports served, shed (429/503), timeouts, latency percentiles of served requests, goodput and cache hit ratio. `--retries` makes clients honour `Retry-After`. |
| `PYTHONPATH=src uv run python scripts/soak_test.py --pid <service pid> --key KEY --minutes 20 --interval 8 --out reports/soak.json` | Steady traffic for N minutes (a tenth of requests deliberately bad) while sampling the service's memory, threads and open files; reports latency by window, errors, hit ratio and growth. |
| `PYTHONPATH=src uv run python scripts/chaos_test.py --service-pid <pid> --key KEY --out reports/chaos.json` | Kill Ollama mid-request, with requests queued, and while idle; times detection and recovery. Restarts Ollama itself on :11435, so run it only against the dedicated instance. |
| `PYTHONPATH=src uv run python scripts/mcp_check.py` | Headless stand-in for an ollmcp session: a chat model sees the CAG tool, decides whether to call it, and answers. Checks tool selection and cache reuse. |
| `ollmcp --servers-json mcp.json --model qwen3:8b-16k` | Interactive ollmcp session with the `cag` MCP server. Use a chat model **different** from `CAG_MODEL`. Not yet driven by hand. |
| `PYTHONPATH=src uv run python -m cag.mcp_server` | Run the MCP server directly over stdio (normally ollmcp launches it). |

## 7. Useful one-off checks

| Command | What it does |
|---|---|
| `PYTHONPATH=src uv run python -c "from cag.adapters.docs_qa import load_docs; ..."` | List the 118 doc chunks and their sizes. |
| `ls reports/*.answers.jsonl` | Find saved per-question outputs. |

## Environment variables (`.env`)

| Variable | Meaning |
|---|---|
| `CAG_OLLAMA_HOST` | Ollama server for the CAG model (dedicated instance, `http://127.0.0.1:11435`). |
| `CAG_MODEL` | Model for CAG and RAG generation (`qwen3:8b`). |
| `CAG_NUM_CTX` | Context window sent to Ollama (`32768`; use `40960` for the docs corpus). |
| `CAG_KEEP_ALIVE` | How long the model stays loaded (`60m`). |
| `CAG_DATASET`, `CAG_MAX_DOCS` | Corpus for the MCP server and service. |
| `CAG_API_KEYS`, `CAG_AUTH_DISABLED` | Service auth: `name:key` pairs (comma-separated), or `1` to run open locally. The service refuses to start with neither. |
| `CAG_RATE_PER_MIN`, `CAG_RATE_BURST` | Per-client rate limit (default 12/min, burst 4). |
| `CAG_MAX_INFLIGHT`, `CAG_MAX_QUEUE`, `CAG_QUEUE_TIMEOUT_S`, `CAG_REQUEST_TIMEOUT_S` | Concurrency and queue limits (defaults 1, 2, 180 s, 120 s). Keep `CAG_QUEUE_TIMEOUT_S >= (CAG_MAX_QUEUE + 1) x worst-case answer time`. |
| `CAG_PII_CORPUS`, `CAG_PII_OUTPUT` | PII redaction: `redact` (default) or `off` for the corpus; `1` (default) or `0` for answers. |
| `CAG_HEALTH_INTERVAL_S`, `CAG_RECOVER_INTERVAL_S` | How often the service pings Ollama while ready (10 s) and while recovering (3 s). |
| `CAG_URL_ALLOWLIST` | Hosts allowed in answers (comma-separated, or `none`). Unset = hosts found in the corpus (weaker). |
| `CAG_PROMPT`, `CAG_MAX_TOKENS`, `CAG_BUDGET_RATIO` | Service: prompt style (`cite`/`quote`), answer length cap, and the share of `CAG_NUM_CTX` the corpus may use. `CAG_DATASET` also accepts `docs`. |
| `CAG_ATTRIBUTION` | `bm25` (default) or `hybrid`: which attributor the service uses for `sources`. |
