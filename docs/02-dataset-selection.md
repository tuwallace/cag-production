# 02. Dataset Selection

## Proposed dataset: `wonderfulworlds/multiplayer-456guys-sample`

Proposed by the project owner. Publisher and terms as shown on its Hugging Face page when inspected on 2026-10-21: published by **Wonderful Worlds 5G Ltd**,
license cc-by-4.0, **gated** (the files are visible only after logging in and accepting the publisher's conditions).

What was visible without access:
- Files: `recordings/` (a folder with a replay file, named like "replay 2026-08-18T12-18_in-2_00699"), `.gitattributes`, and a 27-byte `README.md`.
- No dataset card, schema, description or text documents.

**Assessment: not a fit for this project's purpose, a text corpus for question answering.** This is a statement about fit, not about the quality or value of the
dataset, and it rests on public metadata only: the folder name and a commit message suggest multiplayer game replay recordings, which is an inference because the
gated files were not opened. CAG needs a *text corpus that answers questions*; replay logs are telemetry, not knowledge, and using them would force a custom
event-to-text conversion that would not show what CAG is good at. If the files turn out to contain readable text or JSON, revisit this.
This project is not affiliated with the publisher.

## Recommended datasets (in order)

| Priority | Dataset | Why | Size fit |
|---|---|---|---|
| 1 | **SQuAD (train) subset**, as used by the CAG paper and its reference repo (`hhhuang/CAG`) | Reproducible baseline; many questions per document; lets you compare against the paper's numbers | ~21k-50k tokens at k=3..7 |
| 2 | **HotpotQA (train) subset**, same repo | Multi-hop questions, where CAG's "see everything" advantage vs RAG shows | ~1.4k-106k tokens depending on k |
| 3 | **A real product-docs corpus** (e.g. one project's public documentation, or the existing `../helpdesk-rag` content) | Most realistic for production: stable, FAQ-style, high query volume. Needs your own question set | Choose to fit under the context budget |

**Recommendation:** start with SQuAD for parity and correctness, then swap in the helpdesk corpus
from `../helpdesk-rag` to get a head-to-head RAG vs CAG comparison on the same questions.

## Corpus budget check (do this first for any dataset)

```
corpus_tokens + system_prompt + max_question + max_answer  <=  0.5 * context_window
```
Tokenize with the *serving model's* tokenizer. If it exceeds the budget, trim, summarize, or go hybrid.
