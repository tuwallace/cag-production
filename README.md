# CAG (Cache-Augmented Generation): Production Guide

> **Status: research prototype, not a production system.** Everything here was built and measured with local models (Ollama; Qwen 2.5 32B and Qwen 3 8B) on one Apple-silicon machine, against a 25k-token slice of Ollama's documentation and 90 questions written by the AI assistant that built it, with no independent human review (the owner waived it; see [docs/11](docs/11-roadmap-status.md)). Results will not transfer unchanged to other models, corpora or hardware.
> The service has hardening (API keys, rate limits, PII and URL guards, outage recovery) but has not been security-audited, has no TLS, and its limits are per process: **do not expose it to the internet as it is.** [docs/12](docs/12-security-tests.md) and [docs/13](docs/13-phase8-gate-and-shadow.md) list what was and was not tested. Security reports: see [SECURITY.md](SECURITY.md).

**Video walkthrough:** [I tested CAG against RAG on my laptop](https://youtu.be/1iEjZISdaeo) (about 6.5 minutes; synthetic narration; the plan and checks are in [docs/video](docs/video/README.md)).

A sandbox for learning and deploying **CAG**, the retrieval-free alternative to RAG.
Optional sibling project: [`../helpdesk-rag`](https://github.com/tuwallace/helpdesk-rag), used as a RAG baseline for the helpdesk dataset only (see "Optional dependency" below).

## Docs

| # | Doc | Purpose |
|---|-----|---------|
| 01 | [Concepts: CAG vs RAG](docs/01-concepts-cag-vs-rag.md) | What CAG is, when to use it, when not to |
| 02 | [Dataset selection](docs/02-dataset-selection.md) | Assessment of the proposed dataset and recommended alternatives |
| 03 | [Technical stack](docs/03-technical-stack.md) | Two deployment paths: managed API vs self-hosted |
| 04 | [Architecture](docs/04-architecture.md) | Components, request flow, cache lifecycle |
| 05 | [Implementation steps](docs/05-implementation-steps.md) | Ordered, phase-by-phase build plan |
| 06 | [Production best practices](docs/06-production-best-practices.md) | Cache hygiene, security, observability, cost, eval |
| 07 | [Sources](docs/07-sources.md) | References and confidence notes |
| 08 | [Prototype](docs/08-prototype.md) | Runnable local CAG vs RAG eval (Ollama, ollmcp, helpdesk-rag, SQuAD) |
| 09 | [Docs-QA results](docs/09-docs-qa-results.md) | CAG vs RAG on the Ollama documentation, 40 golden questions |
| 10 | [Command reference](docs/10-commands.md) | Every command used so far, with a one-line explanation |
| 11 | [Roadmap status](docs/11-roadmap-status.md) | Where the project stands against the implementation plan |
| 12 | [Security tests](docs/12-security-tests.md) | Prompt injection, output guards, hardening, PII redaction, outage recovery, load and soak tests |
| 13 | [Phase 8: gate and shadow mode](docs/13-phase8-gate-and-shadow.md) | CI-style regression gate with thresholds from the held-out results, and a CAG vs RAG shadow comparison |

## One-paragraph summary

CAG loads the whole knowledge base into the model's context once and reuses the precomputed
attention state (the KV cache) on every query, so there is no retriever, vector DB or chunking
at query time. It wins when the corpus is **small enough to fit the context window, changes
rarely, and is queried often**. Production CAG is mostly an exercise in *prompt-prefix
discipline* and *cache lifecycle management*, not in new model code.

## Optional dependency: helpdesk-rag

The `helpdesk` dataset adapter and `--baseline helpdesk-rag` use the sibling project [helpdesk-rag](https://github.com/tuwallace/helpdesk-rag) (MIT, a separate repository).
It is **not included here**. To use that part: clone it next to this repository as `../helpdesk-rag`, follow its README to download the data and build its Qdrant index, and run
`uv sync --python 3.12 --group helpdesk` here. Even `--baseline bm25` reads the ticket CSVs from `../helpdesk-rag/data/raw`.
The ticket dataset it uses (`mindweave/help-desk-tickets`) is CC-BY-NC-4.0 (non-commercial) and is not redistributed in this repository.
Everything else runs without it: the docs-QA evaluation (the main results), the SQuAD adapter, the unit tests, the regression gate and the service.

## Repository notes

- `data/ollama-docs/` holds unmodified copies of Ollama's documentation (MIT, see `data/ollama-docs/LICENSE`); it is the corpus the eval and the gate are locked to.
- `eval/baselines/` holds the 32B baseline answers the gate thresholds were calibrated from, and the 8B answers used for comparison. `reports/` is generated output and is not tracked.
- CI entry points: `make gate-fast`, `make gate-baseline` (seconds, no model) and `make gate-model` (needs Ollama and the 32B model). See `docs/13-phase8-gate-and-shadow.md`.

## Trademarks and affiliation

Ollama, Qwen, Llama, Claude, Anthropic, Hugging Face and other product names are trademarks of their respective owners. They are used here only to identify the software and models that were tested. This project is not affiliated with, endorsed by or sponsored by any of them. The documentation slice in `data/ollama-docs/` is copyright Ollama, used under its MIT licence (`data/ollama-docs/LICENSE`).
