# 07. Sources and Confidence

| Source | Used for | Confidence |
|---|---|---|
| [Don't Do RAG: CAG paper (arXiv 2412.15605)](https://arxiv.org/pdf/2412.15605) | Core CAG concept and phases | High (primary) |
| [hhhuang/CAG reference repo](https://github.com/hhhuang/CAG) | SQuAD/HotpotQA setups, token sizes, limitations | High (primary) |
| [Anthropic prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) | TTLs, pricing multipliers, minimums, invalidation, usage fields | High, but only the first ~100k chars of the page were read; re-check before launch |
| [vLLM Automatic Prefix Caching docs](https://docs.vllm.ai/en/v0.8.0/design/v1/prefix_caching.html) | Block hashing, enabling prefix caching | High, but version-specific (v0.7-0.8 retrieved); check the current release |
| [NVIDIA Dynamo LMCache guide](https://docs.nvidia.com/dynamo/v1.0.1/integrations/lm-cache.md) | LMCache chunk size and CPU cache tuning | Medium |
| [LMCache vs vLLM benchmark write-up](https://levelup.gitconnected.com/vllm-prefix-caching-vs-lmcache-benchmarking-kv-reuse-tradeoffs-944fbaf98b56) | "Benchmark before adopting LMCache" | Medium (blog) |
| [Louis Bouchard](https://www.louisbouchard.ai/cag-vs-rag/), [PromptHub](https://prompthub.us/blog/retrieval-augmented-generation-vs-cache-augmented-generation), [Neural Maze](https://theneuralmaze.substack.com/p/rag-vs-cag-a-deep-technical-breakdown) | Decision rules, hybrid framing | Medium (secondary) |
| [Hugging Face page of `wonderfulworlds/multiplayer-456guys-sample`](https://huggingface.co/datasets/wonderfulworlds/multiplayer-456guys-sample/tree/main) (publisher: Wonderful Worlds 5G Ltd; cc-by-4.0; gated) | Dataset assessment, inspected 2026-10-21 | High for what is visible; files are gated and were not inspected |

Not verified: blog-quoted figures (hit-rate targets, "10x" cost or throughput claims) were left out of these docs.
The "cache salt" multi-tenant feature in vLLM comes from a secondary source; confirm in current docs.
