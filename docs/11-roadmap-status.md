# 11. Roadmap status

Progress against the phases in [05 Implementation steps](05-implementation-steps.md), as of 2026-10-23.
Legend: DONE = built and run; PARTIAL = built, not fully exercised or missing a piece; TODO = not started.

| Phase | Status | Evidence / what is missing |
|---|---|---|
| 0. Qualify the use case | PARTIAL | `check_budget` rejects oversized corpora (it caught the 103k-token helpdesk set and the 38k-token 3-article SQuAD set). Token counts are a chars/4 estimate; the exact count comes from Ollama after the first call. No tokenizer-exact pre-check. |
| 1. Data and corpus builder | DONE | Deterministic, order-independent corpus with doc ids and a content hash (`corpus.py`); three adapters (SQuAD, helpdesk, Ollama docs). Gap: `write_version` (immutable versioned corpus files + manifest) exists but no CLI uses it yet; `corpus/` is empty. |
| 2. Golden evaluation set | DONE (human review waived) | Docs-QA: 90 questions in two splits: 40 dev (18 single, 10 multi, 1 conflict, 11 unanswerable) and 50 held-out (10 answerable, 40 unanswerable, grep-verified absent). Helpdesk: reused golden set (17 usable on the subset). Metrics: correctness, refusal, citation hit, quote groundedness. Human review waived by the owner on 2026-10-24 (see "Golden question set: review status" below). Gaps: written by the assistant, keyword scoring, only 10 held-out answerable questions. |
| 3. Minimal working CAG | DONE | Cold prefill 66 s (15k tokens) vs warm 0.2-0.3 s; cache hit ratio 0.995-0.997; compared with BM25 and helpdesk-rag RAG on three datasets. Local Ollama instead of the Claude API, by choice. |
| 4. Service | PARTIAL | FastAPI app with `/ask`, `/healthz`, `/readyz`, `/corpus`; returns system-side `sources` and `support`; runs live against the 32B model on the docs corpus (491 s warm-up, 0 errors in a load sweep). Warm-up now runs in a background thread, so liveness stays up and readiness returns 503 (found and fixed in phase 7). Hardened in phase 7: API keys, per-client rate limit, FIFO bounded queue with timeouts (503/429/504), URL guard on outputs, JSON request log; verified live on the 32B (overload sheds in ~10 ms, served latency bounded, goodput stays at capacity). Also: PII redaction, backend-outage recovery. Gaps: applies no groundedness gate, no conversation history, limits are per process (single replica), no TLS. |
| 5. Cache operations | PARTIAL | Warm on startup (service and MCP server), readiness gate, dedicated Ollama instance to prevent eviction. New: the service detects a lost backend, reports not-ready, and re-prefills the corpus automatically when Ollama returns (147 s on 8B; ~8 min on 32B). TODO: scheduled keep-alive, blue/green corpus rollout with rollback, a second replica to cover cold starts. |
| 6. Observability and cost | PARTIAL | Every eval row records prefill time, tokens reused, hit ratio and latency; the service writes one JSON log line per request (client, status, latency, queue time, hit ratio, links removed). TODO: metrics export, dashboards/alerts, a cost model (local inference has no per-token price; GPU-hour and memory are the real cost). |
| 7. Security and hardening | DONE (with caveats) | Doc 12: prompt-injection test (commands ignored; one hidden exfil link on 32B; a false documentation fact adopted every time), API keys, per-client rate limit, bounded FIFO queue with timeouts, model timeout, URL allowlist guard, PII/secret redaction on corpus and output (live leak test: 5 of 5 planted values leaked without it, 0 with it), kill-Ollama tests (fast 502/503, automatic recovery), 20-minute soak (no errors, flat memory after warm-up, no latency drift). Caveats: names are not redacted; soak was 8B only, one client, 20 minutes; no TLS, shared limits across replicas, or key rotation; a hung-but-alive Ollama was not tested. |
| 8. Launch and iterate | PARTIAL | Doc 13. Done: a three-tier regression gate (fast / replay / model) with thresholds from the held-out baseline and a corpus + question + prompt lock; the full model tier ran end to end on the 32B and passed with answers byte-identical to the baseline; a shadow runner (bounded backlog, crash isolation, privacy modes) with promotion criteria; shadow verdicts: 32B CAG promote (matches RAG on correctness, 0 fabrications where RAG refuses, ~8x faster), 8B hold. The project is now a git repository and the fast job was rehearsed on a fresh clone (passes; fails with a non-zero exit when a corpus fact is edited). The repo is on GitHub (private, `tuwallace/cag-production`, pushed 2026-10-24) and its gitleaks workflow passes there. Not done: the gate workflow has never run on a hosted CI system (the example is not enabled), shadow mode is not wired into the service, no canary rollout or automatic rollback, no live 32B shadow (two 24 GB models do not fit on this machine), no real traffic. |

## Beyond the original plan (added because the results asked for it)

| Item | Status | Finding |
|---|---|---|
| Dedicated Ollama instance | DONE | Loading a chat model evicted the CAG model and lost the cache (65 s cold prefill again). |
| Quote-then-answer prompt | DONE | Citations 0.05 -> 0.65, but abstention fell 0.82 -> 0.27 (fabricated quotes). |
| Closed-book control | DONE | 0.30 correct with no documents, so CAG and RAG scores come from reading the docs. |
| Verbatim-quote gate (strict, any_chunk) | DONE | Restores refusals, costs 21-31% false refusals; accuracy flat. |
| Soft gate and relevance check | DONE (replay) | Doc 09, follow-up 3. Revised by the lenient-parser correction in follow-up 4. |
| System-side citation attribution | DONE (replay + service) | Hit 0.93-1.00 vs 0.07-0.96 model-written on CAG; `support` score gives an exploratory refusal gate (doc 09, follow-up 5). |
| Semantic attribution (dense / hybrid / reranker) | DONE (replay) | Hybrid keeps top-1 at 0.83-0.90 on paraphrased answers vs BM25 falling to 0.76; no gain on real model answers; reranker worse (doc 09, follow-up 6). |
| Semantic vs lexical groundedness gate | DONE (replay) | Dev favoured semantic (AUROC 0.87 vs 0.69) but held-out reversed it (0.66 vs 0.90 lexical). A lexical support gate lifts 8B CAG 0.28 -> 0.72 and RAG 0.84 -> 0.96; no gate helps 32B (doc 09, follow-ups 7-8). |
| Held-out evaluation (50 new questions) | DONE | 8B CAG refuses only 4 of 40 unanswerable questions (dev said 27%); 32B CAG refuses 40/40 and scores 0.98 at 3.0 s median. Model size beat every gate. |
| qwen2.5:32b comparison | DONE | Fixes abstention (11/11 refused) and widens CAG's latency edge, but attribution stays poor and the quote format is ignored. |
| Output guard: URL allowlist | DONE | Caught the only successful exfil link with 0 false positives; now in the service (`CAG_URL_ALLOWLIST`). |
| Interactive ollmcp session | TODO | Headless tool-use check passed; the terminal UI was not driven by hand. |

## Learning path

1. Concepts and when to use CAG (doc 01) - done.
2. Pick a dataset that fits (doc 02) - done; the proposed game-replay set was rejected, three others were tried.
3. Stack and architecture (docs 03, 04) - done.
4. Build and measure a prototype (docs 05, 08) - done.
5. Evaluate honestly against RAG (doc 09) - done once; repeat with a larger model (an independent review of the questions was waived).
6. Harden for production (docs 06, phases 4-8 above) - mostly ahead of us.

## Golden question set: review status (decision of 2026-10-24)

The planned second human review of the 90 questions was **waived by the owner**. What exists instead, and what it means:

| Check | Result |
|---|---|
| Authorship | Questions, gold chunks and keyword references were written by the AI assistant that built the project (Claude). No human has independently checked them. |
| Mechanical review (`scripts/review_mechanical.py`) | Every `any` / `all` reference was found in its gold chunks except one; all gold specs resolve; no duplicate questions; 6 of the 51 unanswerable questions use only words that occur somewhere in the corpus (topic-adjacent). |
| LLM review (`scripts/review_llm.py`, Llama 3.1 8B) | Not usable as a judge: it called 48 of the 51 unanswerable questions answerable (25 with invented evidence, 23 with a real sentence that does not answer the question) and agreed with the label on only 3. It did confirm that all 39 answerable questions can be answered from their gold chunks (its own answers matched the reference on 29). |
| Review sheet (`scripts/make_review_sheet.py`) | Generates `reports/review-sheet.md` for anyone who wants to review later. |

Known defects left in place. Changing a question changes the lock (`eval/corpus.lock.json`), which requires the 30-60 minute model tier and `ci_gate.py update-lock`, so they were not fixed:
- the q8_0 K/V cache question accepts "half" or "50%", but the docs say "approximately 1/2", so a faithful quote of the docs would be scored wrong;
- five references are very short and could match by accident ("3", "14", "0.8", "4k", "50%");
- six unanswerable questions are topic-adjacent (for example the Apple Neural Engine and "maximum number of GPUs"), so a refusal there is debatable.

Consequence: read every score as the assistant's own benchmark. It is useful for comparing configurations on the same questions, not as an independent measure of accuracy.

## Suggested next steps, in order

1. Copy the fast job from `ci/workflow.example.yml` into `.github/workflows/` (pin the actions to full SHAs; `actions/checkout` is already pinned in the gitleaks workflow) and watch `make gate-fast` + `make gate-baseline` run on the private repo. Keep the model tier a manual, pre-release step on your own hardware.
2. Grow the answerable side of the question set (only 39 answerable questions bound the weakest check) and fix the known reference defects below; then refit the gate. (The independent human review is waived.)
3. Wire a canary: route a small share of real traffic to CAG, keep RAG as fallback, and use the shadow criteria plus an automatic rollback.
4. Wire the winning gate policy into the service (the 32B passes without one; the 8B needs the lexical support gate), add `write_version` to a build CLI, and put shadow comparison behind a service flag.
5. Longer 32B soak, a TLS proxy, and a second replica to cover the 8-minute cold start.
