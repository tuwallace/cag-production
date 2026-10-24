# 06. Production Best Practices

## Cache hygiene
- Static first, dynamic last. Everything before the breakpoint is byte-identical.
- Strip timestamps, session IDs, per-user strings from the prefix.
- Keep tool definitions, `tool_choice`, images and thinking settings constant when you rely on the cache; the Anthropic docs list which changes invalidate which layers.
- Put the breakpoint on the last stable block, not on the user message.
- Version the corpus immutably; never edit in place.
- Mind the TTL: pick 5 min (cheap writes, needs steady traffic) or 1 hour (2x write cost, better for sparse traffic). Do the math at your QPS.
- Verify a hit on the second request in every environment (`cache_read_input_tokens > 0`).

## Quality
- Measure CAG against RAG on your own questions; long-context accuracy varies by model and by position of facts.
- Put the most critical documents near the start or end of the corpus, and test ordering effects.
- Require citations with doc IDs; reject answers that cite unknown IDs.
- Include unanswerable questions in evals; instruct the model to say "not in the knowledge base."
- Gate every corpus/model/prompt change on the eval in CI.

## Cost and capacity
- API path: cost is write (once per TTL window) plus cheap reads; verify current multipliers.
- Self-host: KV cache memory grows with corpus tokens x concurrent sequences. Prefix sharing helps, but size for peak. Quantized KV cache can cut memory at some quality risk; test it.
- Keep answers short (`max_tokens`); decoding cost is still per query.

## Security and privacy
- A shared cached prefix means **every user can elicit anything in the corpus**. Only include content all callers may see.
- Per-tenant corpora need separate caches. API caches are isolated per organization/workspace; for self-host use per-request cache salts or separate deployments.
- Treat the corpus as untrusted input (prompt-injection in documents). Delimit docs, instruct the model that doc text is data, and review sources.
- Redact PII before assembly. Log metadata, not full prompts.
- Secrets in a secret manager; rate limit and authenticate the gateway.

## Reliability
- Readiness gate on cache warmth (self-host) so cold replicas don't take traffic.
- Graceful degradation: on cache miss, still answer (slower/costlier); alert on sustained miss rate.
- Blue/green corpus rollouts with one-step rollback.
- Timeouts, retries with backoff, and a fallback model or the RAG baseline.

## Observability (minimum set)
- Cache hit ratio = cache_read / (cache_read + cache_creation + uncached input).
- TTFT and total latency p50/p95/p99.
- Cost per query and per corpus version.
- Eval score trend, citation-validity rate, refusal rate.
- Alerts: hit ratio drop, latency spike, cost spike, eval regression.

## Anti-patterns
- Timestamps in the system prompt.
- Reordering documents between builds without re-evaluating.
- Stuffing a corpus that is 90% of the context window.
- Using CAG for per-user private data.
- Assuming the cache survives deploys, model swaps, or TTL gaps.
