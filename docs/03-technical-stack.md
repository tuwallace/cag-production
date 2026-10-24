# 03. Technical Stack

> The runnable prototype (doc 08) uses a third, fully local path: Ollama + qwen3:8b + ollmcp, no API calls. Ollama reuses the KV cache of the previous prompt prefix; it is single-slot and has no explicit cache controls, so treat it as a learning/dev setup. Path B below (vLLM) is the production equivalent.

Two viable production paths. Pick one per deployment; the architecture in doc 04 is the same.

## Path A: Managed API with prompt caching (recommended to start)

| Layer | Choice | Notes |
|---|---|---|
| Model | Claude (Sonnet 5.5 / Opus 5.5 / Haiku 5.5 / Fable 5.1) | Long context; prompt caching built in |
| Caching | Anthropic prompt caching (`cache_control`) | Explicit breakpoints (up to 4) or automatic top-level caching |
| API/service | Python 3.12 + FastAPI + uvicorn | Async, streaming responses |
| Corpus build | Python script, versioned output artifact | Deterministic text assembly |
| Storage | Git + object storage (S3/GCS) for corpus versions | Immutable, hash-named |
| Config/secrets | Env vars via a secret manager | Never in repo |
| Observability | OpenTelemetry + Prometheus/Grafana (or Datadog) | Track cache hit rate from usage fields |
| Eval | Pytest + a golden Q&A set; LLM-as-judge optional | Run in CI on every corpus change |
| Deploy | Container on Cloud Run / ECS / Kubernetes | Stateless; no GPU needed |

Verified API facts (Anthropic docs, retrieved 2026-10-21):
- 5-minute cache (default, refreshed free on each hit) or 1-hour TTL.
- Write cost: 1.25x base input price (5m) or 2x (1h). Reads: 0.1x standard; 0.05x on Opus 5.5 / Sonnet 5.5; 0.025x on Fable 5.1.
- Minimum cacheable prompt: 512 tokens on current 5.x models, but 1,024-4,096 on older ones. Below it, no caching and no error.
- Prefix order is tools -> system -> messages. Any one-character change to cached content is a miss.
- Monitor `cache_creation_input_tokens`, `cache_read_input_tokens`, `input_tokens` in every response.
- Re-check pricing and minimums before launch; they change.

## Path B: Self-hosted open-weights model

| Layer | Choice | Notes |
|---|---|---|
| Model | Llama 3.1 8B/70B Instruct (paper's baseline) or any long-context open model | Match context to corpus size |
| Inference server | **vLLM** with automatic prefix caching (`enable_prefix_caching=True`) | Hashes KV blocks by tokens + prefix; output unchanged |
| KV offload/sharing | **LMCache** (optional) | Offloads KV to CPU/disk, shares across instances. Benchmark vs plain prefix caching first; benefit appears mainly with repeated prefixes and GPU KV pressure, mostly in time-to-first-token |
| Alternative | SGLang (RadixAttention), TensorRT-LLM | Similar prefix-reuse features |
| Hardware | GPU memory sized for weights + KV cache of the corpus x concurrent requests | KV size scales with tokens, layers, heads |
| Serving | vLLM OpenAI-compatible endpoint behind FastAPI or directly | |
| Orchestration | Kubernetes + KServe or Ray Serve; sticky routing to warm replicas | Cache is per replica unless LMCache shares it |
| Multi-tenant safety | vLLM per-request cache salt | Prevents cross-tenant prefix hits; verify against current docs |

## Shared components (both paths)

- **Corpus builder** with stable ordering, doc IDs, and a content hash.
- **Cache warmer**: sends a priming request on deploy and before TTL expiry.
- **Gateway**: auth, rate limiting, request validation.
- **Eval harness** and **baseline RAG** (`../helpdesk-rag`) for regression comparison.

## Choosing

| If you... | Choose |
|---|---|
| want to learn fast, have no GPUs | Path A |
| have data-residency or cost-at-scale needs | Path B |
| are unsure | Build A, keep the model client behind an interface so B can swap in |
