# 02. Dataset Selection

## Proposed dataset: `wonderfulworlds/multiplayer-456guys-sample`

Inspected 2026-10-21 from the public repo page:

- Files: `recordings/` (game replay files, e.g. "replay 2026-08-18T12-18_in-2_00699"), `.gitattributes`, and a 27-byte `README.md`.
- License: cc-by-4.0. **Gated**: files require login and accepting conditions.
- No dataset card, schema or text documents.

**Verdict: not suitable for CAG.** It appears to be multiplayer game replay recordings (my reading of the folder
name and commit message; the contents were not accessible). CAG needs a *text corpus that answers questions*.
Replay logs are telemetry, not knowledge. Using them would force a custom
event-to-text conversion and would not demonstrate CAG's strengths. If you can open the gated files and they turn
out to contain readable text or JSON, revisit this.

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
