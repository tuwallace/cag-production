# 05. Implementation Steps

## Phase 0: Qualify the use case
1. Count corpus tokens with the target model's tokenizer.
2. Confirm the budget in doc 02 (<= 50% of the context window).
3. Confirm update frequency, query volume, and that all users may see all documents.
4. If any check fails, stop and consider RAG or hybrid.

## Phase 1: Data and corpus builder
1. Choose the dataset (doc 02). Start with a SQuAD subset; later the helpdesk corpus.
2. Clean: strip boilerplate, normalize whitespace and encoding, dedupe.
3. Assign stable doc IDs and wrap each doc, e.g. `<doc id="kb-0042" title="...">...</doc>`.
4. Order deterministically (by ID). Never shuffle.
5. Emit `corpus-<hash>.txt` plus `manifest.json` (version, token count, doc list, build date, source commit).

## Phase 2: Golden evaluation set
1. Write or collect 50-200 question/answer pairs with the supporting doc IDs, including unanswerable questions.
2. Define metrics: exact match/F1 or BERTScore (as in the paper), citation accuracy, refusal correctness.
3. Run the existing RAG baseline on the same set to get comparison numbers.

## Phase 3: Minimal working CAG
1. Path A: call the API with the corpus in `system`, `cache_control` on the last corpus block, question in `messages`. Confirm `cache_read_input_tokens > 0` on the second call.
   Path B: start vLLM with prefix caching, send the same long prefix twice, compare time-to-first-token.
2. Run the golden set; record accuracy, latency (p50/p95), cost per query.
3. Compare to RAG. Proceed only if CAG meets the quality bar.

## Phase 4: Service
1. FastAPI endpoints: `POST /ask` (streaming), `GET /healthz`, `GET /readyz` (ready only after cache warm), `GET /corpus` (version info).
2. Prompt builder that enforces the layout in doc 04 and fails a test if anything dynamic appears above the breakpoint.
3. Citation prompting: require answers to cite doc IDs; validate that cited IDs exist.
4. Conversation handling: append history after the breakpoint; cap its length.

## Phase 5: Cache operations
1. Warmer: prime on deploy; keepalive on a schedule shorter than the TTL (or use the 1-hour TTL).
2. Blue/green corpus rollout with rollback to the previous version.
3. Self-host only: sticky routing, readiness gating, evaluate LMCache for cross-replica reuse.

## Phase 6: Observability and cost
1. Log per request: corpus version, cache read/write/uncached tokens, latency, model, outcome.
2. Dashboards and alerts: cache hit rate, p95 TTFT, cost/query, error rate, hit-rate drops after deploys.
3. Cost model: compare cached-read spend against RAG infra + tokens at your expected QPS.

## Phase 7: Security and hardening
See doc 06. Then load test at target QPS, and cold-start/failover tests.

## Phase 8: Launch and iterate
1. Shadow mode against RAG, compare answers.
2. Canary rollout; monitor quality and cost.
3. Re-run the golden set on every corpus or model change in CI; block on regression.

## Suggested repo layout

```
cag-production/
  docs/
  corpus/            builder + versions
  service/           FastAPI app, prompt builder, warmer
  eval/              golden set, runners, reports
  deploy/            Dockerfile, IaC
```
