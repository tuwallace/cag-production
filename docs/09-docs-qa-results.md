# 09. Docs-QA: CAG vs RAG on the Ollama documentation

## Setup

- **Corpus:** 15 files from `github.com/ollama/ollama/docs` (MIT), commit `f580b54`, saved in `data/ollama-docs/`.
  Split at `##` headings into **118 chunks, ~25k tokens** (estimate; Ollama counted ~25.9k). `api.md` and `openapi.yaml` were excluded to stay in budget.
- **Questions:** 40, hand-written from the docs ([eval/docs_qa.jsonl](../eval/docs_qa.jsonl)): 18 single-chunk, 10 multi-chunk (must contain *all* required terms),
  1 on conflicting docs (default context is 4096 in the FAQ, 2048 in the Modelfile reference, VRAM-dependent in context-length), 11 unanswerable (topic checked absent by grep; one is a near-miss trap: "compute capability 10.0").
- **Systems:** same `qwen3:8b`, same prompt. CAG = all 118 chunks in the cached prefix. RAG = top-5 of **BM25 + nomic-embed-text, fused with RRF**.
- **Config:** `num_ctx` 40960 on a dedicated Ollama instance, temperature 0, thinking off.
- **Scoring:** keyword match (any/all of required strings), refusal detection for unanswerables, citation of gold chunk ids. Not an LLM judge.

```bash
PYTHONPATH=src uv run python -m cag.evaluate --dataset docs --n 40 --window 40960 --k 5
```

## Results (n=40)

| | CAG | RAG |
|---|---|---|
| Overall correct | 0.900 (36) | 0.925 (37) |
| Single-chunk (18) | 0.944 | 0.889 |
| Multi-chunk (10) | 0.900 | 0.900 |
| Conflicting docs (1) | 1.0 | 1.0 |
| Unanswerable, refused correctly (11) | 0.818 (9) | **1.0** (11) |
| Refused an answerable question | 0.000 | 0.034 |
| Cited a gold chunk | **0.05** | 0.65 |
| Retrieval hit@5 | - | 0.675 |
| p50 / p95 latency (s) | 4.2 / 15.6 | 6.2 / 13.4 |
| Mean prefill (s) | 0.38 (hit ratio 0.997) | 5.2 |
| Mean output tokens | 102 | 56 |

## Reading it

- **Accuracy is a statistical tie.** The overall gap is one question out of 40. Do not read a winner into 0.900 vs 0.925.
- **RAG's retrieval was imperfect.** hit@5 was only 0.675, yet RAG answered 0.89-0.90 correctly, so some of its answers likely came from partial context or the model's own
  knowledge of Ollama (untested; see the no-context control below). Keyword scoring cannot tell.
- **CAG failed more unanswerable questions (2 of 11)**: it answered instead of refusing. With the whole corpus in view the model finds something plausible to say. RAG's empty-ish context made refusing easy.
- **Attribution is CAG's weak spot here.** The model almost never cited chunk ids (0.05 vs 0.65) and in a spot check cited an unrelated chunk (`cli-03`) for the context-size question.
  Answers were correct but not traceable. The prompt asks for citations; an 8B model with 25k tokens of context mostly ignores it.
- **Latency favours CAG on this setup**: prefill 0.38 s vs 5.2 s for RAG's ~1.7k-token prompts. RAG answers were shorter (56 vs 102 tokens), which narrows the total-time gap.
- **Cold start cost:** the first CAG call prefills ~26k tokens (about 2 minutes on this machine).

## Caveats

- n=40 and a single run; temperature 0 but no repeats.
- Questions and keyword answers were written by the same agent that built the system. Review `eval/docs_qa.jsonl` before trusting the numbers.
- Qwen3 may have seen Ollama's docs in training, which blurs "answered from context".
- Per-question outputs are not saved; only aggregates are in `reports/`.

## Follow-up: forced attribution, saved outputs, closed-book control (run 2026-10-22)

Changes: a `--prompt quote` format (verbatim `Quotes:` lines with a `[doc-id]`, then `Answer:`, then `Sources:`); only the `Answer:` part is scored, so a keyword in a quote cannot rescue a wrong answer;
per-question outputs saved to `reports/*.answers.jsonl`; a `closed_book` control (same model, no documents, "from your own knowledge about Ollama").
The cite-style rerun reproduced run 1 exactly (temperature 0), so the two prompt styles are comparable.

```bash
PYTHONPATH=src uv run python -m cag.evaluate --dataset docs --n 40 --window 40960 --prompt quote --max-tokens 450 --systems cag,rag,closed_book
```

| n=40 | CAG cite | CAG quote | RAG cite | RAG quote | closed-book |
|---|---|---|---|---|---|
| Overall correct | 0.900 | 0.750 | 0.925 | 0.875 | **0.300** |
| Single (18) | 0.944 | 1.000 | 0.889 | 0.944 | 0.222 |
| Multi (10) | 0.900 | 0.800 | 0.900 | 0.800 | 0.000 |
| Unanswerable refused (11) | 0.818 | **0.273** | 1.000 | 0.818 | 0.727 |
| Cited a gold chunk | 0.05 | **0.65** | 0.65 | 0.675 | n/a |
| Quote lines present | n/a | 0.85 | n/a | 0.625 | n/a |
| Quotes found verbatim in the cited chunk | n/a | 0.74 | n/a | 0.88 | n/a |
| p50 latency (s) | 4.2 | 7.5 | 6.6 | 7.9 | 1.1 |

### Findings

1. **Quote-then-answer fixed attribution but broke abstention.** CAG's gold-citation rate went from 0.05 to 0.65, matching RAG. But CAG now answered 8 of 11 unanswerable questions (refusal 0.82 -> 0.27), so overall correctness fell 0.90 -> 0.75.
   Asked to quote, the model **invents quotes**: for "mutual TLS" it quoted "Ollama does not support mutual TLS authentication out of the box" and attributed it to `cloud-00`; for the pull timeout it quoted "5 minutes" from `cli-00`. Neither text exists in the docs.
   Verbatim-quote rate on CAG's unanswerable answers was 0.45, versus 0.83 on answerable ones. A format that demands evidence pressures a small model to fabricate it.
2. **Citation validity is the right check, not citation presence.** Even on answerable questions about a quarter of CAG's quotes (0.74 overall) are not word-for-word in the cited chunk. Verify quotes mechanically before trusting a "Sources" line; the `quote_grounded` metric does this.
3. **The corpus is doing the work.** Closed-book scored 0.30 overall and 0.22 on single-chunk questions (0.00 on multi-chunk), so the 0.89-0.94 from CAG and RAG is mostly reading the docs, not memory. This answers the earlier worry that Qwen3 might simply know Ollama.
   The control also "refused" 0.73 of unanswerable questions, because it declines whenever unsure; its 0.30 is not a floor to beat on those.
4. **RAG held up better under the quote format** (0.875, refusing 9 of 11) because with five retrieved chunks and little relevant text, the model more often falls back to "Not in the knowledge base."
5. **Cost:** quote answers are longer (CAG 145 output tokens vs 102), so p50 latency rose from 4.2 to 7.5 s, now close to RAG's.

### Caveats

- Same single-run, n=40, hand-written, keyword-scored setup as before. A 2-point change is one question.
- The refusal check is a phrase match. Some "not refused" CAG answers say the feature is absent ("Ollama does not have a built-in speech-to-text feature"), which is arguably right in the real world but is not supported by the docs; the quote is fabricated either way.
- I did not test prompt variants beyond this one format.

## Follow-up 2: verbatim-quote gate (run 2026-10-22, `--verify`)

`verify_quotes` (in `systems.py`) accepts an answer only if it is a plain refusal, or it has at least one quote and **every** quote appears word for word
(case, punctuation and spacing ignored; `...` splits a quote into segments) in a chunk. Anything else becomes "Not in the knowledge base."
`strict` requires the chunk the quote cites; `any_chunk` accepts a quote found in any chunk and repairs the citation to the true chunk.
The gate is applied to the same generations as the ungated rows, so the comparison is paired. `strict` came from the live rerun; `any_chunk` is a replay over the saved answers
(`scripts/replay_verify.py`, no model calls). The live ungated rows reproduced the previous run exactly, and a replay of `strict` matched the live gated rows.

```bash
PYTHONPATH=src uv run python -m cag.evaluate --dataset docs --n 40 --window 40960 --prompt quote --max-tokens 450 --systems cag,rag,closed_book --verify
PYTHONPATH=src uv run python scripts/replay_verify.py reports/<run>.answers.jsonl
```

| n=40, quote prompt | correct | single | multi | unanswerable refused | answerable refused | cited gold chunk |
|---|---|---|---|---|---|---|
| CAG, no gate | 0.750 | 1.000 | 0.800 | 0.273 | 0.000 | 0.650 |
| CAG + strict gate | 0.700 | 0.833 | 0.400 | 0.818 | 0.310 | 0.475 |
| CAG + any_chunk gate | 0.750 | 0.833 | 0.600 | 0.818 | 0.207 | 0.550 |
| RAG, no gate | 0.875 | 0.944 | 0.800 | 0.818 | 0.034 | 0.675 |
| RAG + strict gate | 0.725 | 0.722 | 0.500 | 0.909 | 0.310 | 0.500 |
| RAG + any_chunk gate | 0.775 | 0.778 | 0.600 | 0.909 | 0.241 | 0.550 |

### Findings

1. **The gate restores abstention but costs recall, so overall accuracy does not improve.** CAG's refusals on unanswerable questions go from 0.27 to 0.82, but it also refuses 21-31% of answerable ones. Net: CAG 0.75 -> 0.70 (strict) or 0.75 (any_chunk); RAG falls from 0.875 to 0.73-0.78.
   Whether that is a win depends on what a wrong answer costs against a refusal. If wrong answers are costly (support, compliance), the gate is worth it; if not, it is not.
2. **Most answerable rejections are sloppy citations, not invention.** Classifying every quote: CAG answerable quotes were 41 verbatim in the cited chunk, 6 verbatim but in a different chunk (wrong id), 3 near-verbatim (small edits), 1 fabricated.
   That is why `any_chunk` recovers 10 points of false refusals over `strict`. Roughly 1 in 5 quotes carries the wrong chunk id, so do not trust a model-written citation without checking it.
3. **Fabrication concentrates where the corpus is silent.** On unanswerable questions CAG produced 6 fabricated quotes, 15 genuine quotes from irrelevant chunks, and 1 near-verbatim.
   The gate catches the fabricated ones. It cannot catch an answer built on a real but irrelevant quote: 2 unanswerable questions still got through with grounded-looking evidence (the "grounded" outcome above). Verbatim-ness proves the quote exists, not that it answers the question.
4. **Multi-chunk questions suffer most** (CAG 0.80 -> 0.40 strict): they need several quotes, and one bad quote rejects the whole answer.
5. **Citation-correct rate fell** (0.65 -> 0.48-0.55) only because rejected answers carry no citation; among accepted answers under `any_chunk` the citations point to a chunk that really contains the quote (not necessarily the gold chunk).

### Caveats

- n=40, one run, hand-written keyword-scored questions. One question is 2.5 points; the `any_chunk` rows are a post-hoc replay, so that policy was chosen after seeing the failures and could be over-fitted to them.
- The gate is deliberately all-or-nothing. A softer policy (drop only the bad quote, require at least one good one) was not tested.
- Models: only `qwen3:8b`.

## Follow-up 3: soft gate and relevance check (replay)

`verify_soft` drops ungrounded quotes instead of rejecting the whole answer. It passes if at least one quote is word for word in *some* chunk, repairs the citation to the chunk that really holds the quote,
and optionally requires relevance: the share of the question's content words found in the best grounded quote plus its chunk's heading line must be >= a threshold (25% or 50%).
Replayed over the saved quote-prompt generations (`scripts/replay_verify.py`; no model calls). The thresholds were fixed before looking, but I tried two, so treat the choice as tuned on this set.

| n=40 | correct | single | multi | unanswerable refused | answerable refused |
|---|---|---|---|---|---|
| CAG, no gate | 0.750 | 1.000 | 0.800 | 0.273 | 0.000 |
| CAG + strict | 0.700 | 0.833 | 0.400 | 0.818 | 0.310 |
| CAG + any_chunk | 0.750 | 0.833 | 0.600 | 0.818 | 0.207 |
| CAG + soft | 0.750 | 0.833 | 0.700 | 0.727 | 0.172 |
| CAG + soft + relevance 25% | **0.775** | 0.778 | 0.700 | 0.909 | 0.241 |
| CAG + soft + relevance 50% | 0.625 | 0.667 | 0.200 | 1.000 | 0.517 |
| RAG, no gate | 0.875 | 0.944 | 0.800 | 0.818 | 0.034 |
| RAG + soft + relevance 25% | 0.800 | 0.778 | 0.600 | 1.000 | 0.241 |

### Findings

1. **Soft gating recovers multi-section questions** (CAG multi 0.40 strict -> 0.70 soft) because one bad quote no longer sinks the answer. It loses a little abstention (0.82 -> 0.73).
2. **A 25% relevance floor is the best CAG policy tried**: 0.775 correct, 0.91 of unanswerable questions refused. That is one question above the ungated 0.750, which is inside the noise.
   It does catch the real-but-irrelevant quotes that a pure existence check let through.
3. **A 50% floor over-rejects** (false refusals 0.52, multi 0.20): a lexical overlap test cannot be strict. Questions and docs use different words.
4. **No gate beats ungated RAG** (0.875). With retrieved context RAG's own refusals are already good, and every gate only adds false refusals.
5. **Net:** gating trades recall for safety. It is a dial, not a fix. Choose the threshold from the cost of a wrong answer versus a refusal in your use case, and validate it on questions you did not tune on.

### Caveats

- Replay on 40 questions, 11 unanswerable. One question is 2.5 points. The 25% threshold was selected from two tried values on the same data, so its edge is likely optimistic.
- The soft gate does not rewrite the answer, so an answer can still lean on a quote that was dropped.
- Lexical relevance is crude. A model-based "does this quote answer the question?" pass was not tried.

## Follow-up 4: qwen2.5:32b vs qwen3:8b (run 2026-10-22, quote prompt, same cached corpus)

`qwen2.5:32b-instruct-q4_K_M` (native 32k context) with the same 118 chunks cached at `num_ctx` 32768, KV cache `q8_0`, flash attention, on the dedicated Ollama instance. It fits 100% on the GPU (24 GB).

```bash
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_NUM_PARALLEL=1 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve
CAG_OLLAMA_HOST=http://127.0.0.1:11435 PYTHONPATH=src uv run python -m cag.evaluate --dataset docs --n 40 --model qwen2.5:32b-instruct-q4_K_M --window 32768 --ratio 0.85 --prompt quote --max-tokens 450 --systems cag,rag,closed_book --verify
```

| n=40, quote prompt | 8B CAG | 32B CAG | 8B RAG | 32B RAG |
|---|---|---|---|---|
| Overall correct | 0.750 | **0.900** | 0.875 | **0.950** |
| Single (18) | 1.000 | 0.833 | 0.944 | 0.944 |
| Multi (10) | 0.800 | 0.900 | 0.800 | 0.900 |
| Unanswerable refused (11) | 0.273 | **1.000** | 0.818 | **1.000** |
| Answerable refused | 0.000 | 0.103 | 0.034 | 0.034 |
| Cited a gold chunk / precision | 0.65 / 0.61 | 0.45 / 0.41 | 0.675 / 0.65 | 0.675 / 0.66 |
| Followed the quote format (strict parser) | 0.85 | **0.00** | 0.625 | 0.625 |
| Quotes verbatim in cited chunk | 0.74 | n/a | 0.88 | 1.00 |
| p50 / p95 latency (s) | 7.4 / 19.5 | 15.6 / 86 | 7.9 / 18.9 | 32.6 / 62.7 |
| Mean prefill (s) | 0.38 | 1.6 | 5.3 | 23.3 |

Cold prefill of the 26k-token corpus took **508 s** on the 32B model (about 2 minutes on the 8B). Decoding is about 5 tokens/s.

### Findings

1. **The bigger model fixes abstention without a gate.** 32B CAG refused all 11 unanswerable questions (8B: 3 of 11) and scored 0.90 overall (+15 points, 6 questions). The 8B model's fabricated answers on silent topics were largely a capability problem, not a prompt problem.
2. **CAG's latency advantage grows with model size.** Warm prefill is 1.6 s against 23 s for RAG's ~1.7k-token prompts, so median latency is 15.6 s vs 32.6 s. Per question the cache saves about 21 s on this hardware; it costs an 8.5-minute cold start.
3. **But 32B CAG ignores the quote format and cites worse.** None of its answers match the strict `> "quote" [id]` shape. Of 40 answers: 17 start with `Quotes:` but drift (block quotes without quote marks, code fences, multi-line quotes), 9 are plain answers with no quotes, 14 are refusals.
   Citations are weak too (gold-chunk hit 0.45, precision 0.41), with wrong ids (e.g. it cited `cli-04` for the `ollama ps` FAQ answer) and one `Sources:` line listing about 70 chunk ids. RAG with the same model followed the format as often as the 8B model did (0.625) and its quotes were 100% verbatim.
   With 118 similar ids in view, the larger model is better at the answer and no better at attribution.
4. **Closed-book is degenerate on 32B**: it refused 97% of answerable questions ("Not in the knowledge base"), so its 0.275 says nothing about memorisation. The earlier 8B control (0.30 correct, 0.22 single) remains the only usable one.
5. **Gates behave very differently by model** (replay with the lenient parser below). On 32B CAG every policy hurts (correct 0.38-0.55 vs 0.90 ungated; false refusals 0.59-0.83) because the quotes are in the wrong shape or tagged with the wrong id. On 32B RAG the `any_chunk`/soft gates cost only 0.05 (0.95 -> 0.90).
   A gate that fits the 8B model does not transfer; it depends on how well a given model follows the output format.

### Correction to follow-ups 2 and 3: the gate results depend on the quote parser

The original parser only reads `> "text" [id]`. Answers in the slightly different shape `> text [id]` counted as "no quotes" and were rejected, which inflated false refusals. A lenient parser (`--lenient` in `scripts/replay_verify.py`; accepts unquoted block-quote lines) changes the 8B CAG numbers:

| qwen3:8b CAG, n=40 | correct | multi | unanswerable refused | answerable refused |
|---|---|---|---|---|
| no gate | 0.750 | 0.800 | 0.273 | 0.000 |
| strict, original parser (follow-up 2) | 0.700 | 0.400 | 0.818 | 0.310 |
| strict, lenient parser | 0.775 | 0.500 | 0.818 | 0.207 |
| any_chunk, lenient parser | 0.825 | 0.700 | 0.818 | 0.103 |
| soft, lenient parser | **0.825** | 0.800 | 0.727 | 0.069 |
| soft + relevance 25%, lenient parser | 0.800 | 0.800 | 0.909 | 0.207 |

So for the 8B model a gate **does** raise overall correctness (+8 points, 3 questions) once the parser is not the bottleneck, and "gating does not improve accuracy" in follow-up 2 was partly a parser artifact. The lenient parser was written after seeing these failures, so treat the improvement as tuned on this data.
The 8B RAG numbers move the same way (soft: 0.775 -> 0.800). The qualitative conclusions that hold in both parsers: gates trade recall for abstention, and a stricter relevance floor over-rejects.

### Caveats

- One run per model, n=40, 11 unanswerable, single-author keyword-scored questions. Six questions separate 0.75 from 0.90.
- The 32B model ran with a quantized KV cache (`q8_0`), a different Ollama version from the desktop server, and a 450-token output cap; the 8B ran with an f16 cache. The KV difference is a possible confound for attribution quality.
- Both gates and the lenient parser were tuned after the fact on these 40 questions.

## Follow-up 5: system-side citations (replay over saved answers, both models)

`Attributor` (`src/cag/attribution.py`) ignores the ids the model wrote. After generation it scores every chunk against the **answer text** (plus any quoted text) with BM25 and keeps up to 3 chunks scoring at least 60% of the best.
It also reports `support`: the share of the answer's content words found in those chunks. `CAG` can take an attributor and the service returns `sources` and `support` next to the model's own `cited`.
No new generations were needed: attribution is a post-processing step, so it was replayed over every saved run (`scripts/replay_attribution.py`; no model calls).

```bash
PYTHONPATH=src uv run python scripts/replay_attribution.py reports/docs-qa-118c-20261022-102041.answers.jsonl reports/docs-qa-118c-20261022-111700.answers.jsonl reports/docs-qa-118c-20261022-123448.answers.jsonl
```

Scored on answerable questions where the system did not refuse. `hit` = any cited chunk is a gold chunk; `prec` = share of cited chunks that are gold; `ctrl` = BM25 on the *question* alone, top 3 (control: attribution must beat plain retrieval to add anything).

| Run | System | model-written hit / prec | system-side hit / prec (top-1 hit) | ctrl hit / prec |
|---|---|---|---|---|
| 8B, cite prompt | CAG (n=29) | 0.07 / 0.07 | **1.00 / 0.71** (0.86) | 0.83 / 0.35 |
| 8B, cite prompt | RAG (n=28) | 0.93 / 0.90 | 1.00 / 0.74 (0.82) | 0.86 / 0.36 |
| 8B, quote prompt | CAG (n=29) | 0.90 / 0.85 | 0.97 / 0.79 (0.86) | 0.83 / 0.35 |
| 8B, quote prompt | RAG (n=28) | 0.96 / 0.93 | 0.93 / 0.79 (0.93) | 0.86 / 0.36 |
| 32B, quote prompt | CAG (n=26) | 0.69 / 0.62 (3.7 ids/answer) | **0.96 / 0.80** (0.85) | 0.88 / 0.37 |
| 32B, quote prompt | RAG (n=28) | 0.96 / 0.95 | 0.96 / 0.79 (0.93) | 0.86 / 0.36 |

### Findings

1. **System-side attribution fixes CAG's citation problem, for either model and either prompt.** With the plain "cite" prompt the 8B model cited a gold chunk 7% of the time; attribution gets 100%. For the 32B model, which wrote 3.7 ids per answer on average (one answer listed about 70), hit goes 0.69 -> 0.96 and precision 0.62 -> 0.80. Nothing is asked of the model, so format drift stops mattering.
2. **It beats the control.** Attributing from the answer gives 0.93-1.00 hit and 0.71-0.80 precision, against 0.83-0.88 and 0.35-0.37 for retrieving from the question. The answer text points to the supporting chunk better than the question does.
3. **Where the model already cites well (RAG), attribution is not better**: model-written ids have the higher precision (0.90-0.95 vs 0.74-0.79) because attribution returns about 1.8 chunks to the model's 1.2. Use attribution as a fallback or cross-check there, and take `top1` (0.82-0.93) if you want a single citation.
4. **`support` carries some groundedness signal.** For 8B CAG on the quote prompt, answers to answerable questions scored 0.78 on average and answers to unanswerable questions that were not refused scored 0.52 (n=8). The sample is small, and 32B had nothing to compare (it refused every unanswerable question).

### Support-threshold gate (exploratory)

Refuse when `support` is below a threshold; accepted answers carry the system-side citations. No quotes are required, so it works on any prompt. Two thresholds were tried (50%, 60%) on the same 40 questions, so treat the winner as tuned.

| n=40 CAG | no gate | support >= 50% | support >= 60% |
|---|---|---|---|
| 8B, quote prompt | 0.750 | **0.825** | 0.800 |
| 8B, cite prompt | 0.900 | 0.875 | 0.800 |
| 32B, quote prompt | 0.900 | 0.875 | 0.825 |

For 8B on the quote prompt the gate refuses more unanswerable questions (0.27 -> 0.64) at 7% false refusals, matching the best quote gate without needing the quote format. Where the model already abstains (8B cite prompt, 32B), it only adds false refusals. RAG is unchanged at 50% and worse at 60%. The gate and its threshold are therefore model-dependent, and 50% beats 60% everywhere.

### Caveats

- Gold chunks were chosen by me from each question's topic, and BM25 favours lexical overlap, so attribution is likely stronger here than on paraphrased answers or a corpus with near-duplicate chunks.
- "Supported by a chunk" is not "the model used the chunk"; a wrong answer that reuses doc vocabulary also gets a citation and a high `support`.
- Attribution returns up to 3 chunks; `hit` is generous, `top1` is the stricter number.
- Same n=40 set, one run per model; thresholds explored after seeing results.

## Follow-up 6: semantic attribution on paraphrased answers (replay; no generation of answers)

`SemanticAttributor` (`src/cag/attribution.py`) adds dense retrieval (nomic-embed-text through Ollama, cached) to the BM25 attributor, in three modes:
`dense` (cosine only), `hybrid` (0.5 x BM25/best + 0.5 x min-max cosine) and `rerank` (hybrid shortlist of 8, then the `bge-reranker-base` cross-encoder reads answer and chunk together).
Same selection rule as before: top 3 chunks, keep those scoring at least 60% of the best. These settings were fixed in advance and not tuned.

**Test set.** 29 answerable questions, first correct non-refused answer per question from the saved 8B and 32B runs, reworded by `qwen3:8b` at two levels (`scripts/make_paraphrases.py` -> `eval/paraphrases.jsonl`):
P1 keeps technical terms, P2 asks for plain language with no exact commands or names. Gold chunks are the question's gold chunks. `ctrl` = hybrid retrieval over the **question** alone.

```bash
PYTHONPATH=src uv run python scripts/make_paraphrases.py reports/<cite-run>.answers.jsonl reports/<32b-run>.answers.jsonl > eval/paraphrases.jsonl
PYTHONPATH=src uv run python scripts/replay_paraphrase.py eval/paraphrases.jsonl
```

The generator ignored the "no exact names" instruction for 16 of 29 P2 paraphrases (they kept an identifier such as `OLLAMA_HOST`). P2-clean is the 13 that dropped every identifier: the genuinely hard subset.

| Answer text | Method | hit | top-1 | precision | chunks kept |
|---|---|---|---|---|---|
| original (n=29) | BM25 | 1.00 | 0.86 | 0.72 | 2.1 |
| | dense | 0.90 | 0.79 | 0.47 | 2.9 |
| | **hybrid** | 1.00 | **0.90** | 0.61 | 2.6 |
| | rerank | 0.79 | 0.69 | 0.35 | 3.0 |
| | ctrl (question) | 0.93 | 0.72 | 0.49 | 2.7 |
| P1 reworded (n=29) | BM25 | 0.97 | 0.86 | 0.66 | 2.3 |
| | hybrid | 0.97 | 0.83 | 0.58 | 2.6 |
| | rerank | 0.90 | 0.62 | 0.37 | 3.0 |
| P2 plain language (n=29) | BM25 | 0.90 | 0.76 | 0.52 | 2.6 |
| | dense | 0.86 | 0.76 | 0.43 | 2.9 |
| | **hybrid** | 0.93 | **0.86** | 0.52 | 2.7 |
| | rerank | 0.86 | 0.55 | 0.36 | 3.0 |
| | ctrl (question) | 0.93 | 0.72 | 0.49 | 2.7 |
| P2-clean, no identifiers (n=13) | BM25 | 0.92 | 0.69 | 0.58 | 2.3 |
| | dense | 0.77 | 0.77 | 0.36 | 2.8 |
| | **hybrid** | 0.92 | **0.85** | 0.55 | 2.5 |
| | rerank | 0.85 | 0.62 | 0.33 | 3.0 |
| | ctrl (question) | 0.92 | 0.77 | 0.47 | 2.5 |

On the real saved model answers (BM25 -> hybrid): hit 0.93-1.00 -> 0.96-1.00, top-1 0.82-0.93 -> 0.79-0.93, precision 0.71-0.80 -> 0.61-0.72. No gain; hybrid keeps more chunks.

### Findings

1. **Hybrid is the most robust choice for the top citation.** Its top-1 accuracy holds at 0.83-0.90 across original, reworded and plain-language answers, while BM25's falls from 0.86 to 0.76 (0.69 on P2-clean). Pure dense is worse than BM25, so the gain comes from combining them.
2. **BM25 is still as good, and more precise, when answers keep the docs' identifiers.** On original and P1 answers BM25 has the higher precision (0.72 and 0.66 vs 0.61 and 0.58) and about the same top-1 (hybrid is 0.90 vs 0.86 on original, 0.83 vs 0.86 on P1). On real model answers the two are indistinguishable on hit and top-1. Embeddings add cost (a model server and a vector cache) for no benefit there.
3. **The reranker did worse here, and I would not read that as a general verdict.** It kept 3 chunks every time (its sigmoid scores bunch together, so the 60% rule prunes nothing), and top-1 was 0.55-0.69. Plausible causes, none tested: a long multi-sentence answer is a poor reranker query, chunks were cut at 1,800 characters, and the model is a general web reranker.
4. **Answer-based attribution loses most of its edge on paraphrases.** On P2 the question-only control reaches the same hit (0.93) and precision (0.49 vs 0.52) as hybrid-on-answer; only top-1 stays ahead (0.86 vs 0.72). Once the answer stops echoing the docs, the answer carries little more signal than the question.
5. **Lexical `support` would collapse on paraphrases** (BM25 coverage depends on shared words); the semantic score (`sem`, best cosine) stayed at 0.81-0.86 across levels, so it is the better basis for any support-threshold gate on reworded answers. That gate was not tested.

### Caveats

- n=29 (13 for P2-clean): a difference of one question is 3-8 points. Hybrid vs BM25 on top-1 is about 3 questions.
- Paraphrases come from the same 8B model family and were spot-checked on about ten examples, not all; they only cover answers that were already correct.
- Gold chunks are single-author; selection rules (k=3, 60%, alpha 0.5) were not tuned, and a stricter rule would raise precision for every method.
- Replay only: no live model answers were reworded in the loop.

## Follow-up 7: semantic vs lexical groundedness gate, on original and paraphrased answers (replay)

> **Superseded by follow-up 8:** on 50 held-out questions the semantic signal did *not* hold up (AUROC 0.66) and the lexical one did (0.90).

Question: can an answer's *support* tell good answers from fabricated ones, and does it survive rewording? Two signals per answer, both computed after generation with no quotes needed:
`lex` = share of the answer's content words found in the BM25-attributed chunks (the earlier `support`); `sem` = best cosine between the answer and the hybrid-attributed chunks (nomic-embed-text).

**Data.** Good = the 29 correct answers to answerable questions (`eval/paraphrases.jsonl`). Bad = the 12 distinct non-refused answers to unanswerable questions, i.e. fabricated or ungrounded
(`eval/paraphrases_bad.jsonl`, from 8 questions). Every answer is scored as the original and as two rewordings by `qwen3:8b` (P1 keeps technical terms, P2 plain language). Thresholds are fitted on the **originals only** and applied unchanged to the rewordings, which is the transfer test.

```bash
PYTHONPATH=src uv run python scripts/make_paraphrases.py --bad reports/<run>.answers.jsonl [...] > eval/paraphrases_bad.jsonl
PYTHONPATH=src uv run python scripts/replay_gate.py reports/docs-qa-118c-20261022-102041.answers.jsonl reports/docs-qa-118c-20261022-111700.answers.jsonl reports/docs-qa-118c-20261022-123448.answers.jsonl
```

| Signal | Answer text | AUROC [95% bootstrap CI] | "Keep 90% of good" threshold: good kept / bad refused |
|---|---|---|---|
| lexical | original | 0.69 [0.47, 0.87] | 0.93 / 0.33 |
| | P1 reworded | 0.62 [0.39, 0.82] | 0.83 / 0.50 |
| | P2 plain language | 0.80 [0.64, 0.92] | 0.66 / 0.75 |
| **semantic** | original | **0.87** [0.76, 0.97] | 0.93 / 0.58 |
| | P1 reworded | **0.85** [0.73, 0.96] | 0.90 / 0.58 |
| | P2 plain language | 0.81 [0.68, 0.92] | 0.72 / 0.58 |

Mean `sem`, good vs bad: 0.862 vs 0.791 (original), 0.857 vs 0.789 (P1), 0.835 vs 0.778 (P2).

End to end on the saved generations (n=40 each; thresholds fitted on the same answers, so **in-sample**), correct rate by gate:

| run | no gate | lexical gate | semantic gate |
|---|---|---|---|
| 8B CAG, quote prompt | 0.750 | 0.800 | **0.825** |
| 8B CAG, cite prompt | 0.900 | 0.900 | 0.900 |
| 32B CAG, quote prompt | 0.900 | 0.900 | 0.825 |
| 8B RAG, quote prompt | 0.875 | 0.875 | 0.825 |
| 8B RAG, cite prompt | 0.925 | 0.925 | 0.900 |
| 32B RAG, quote prompt | 0.950 | 0.950 | 0.875 |

(Both gates at their "keep 90% of good" threshold. Using the Youden-optimal threshold instead refused too many good answers: the semantic gate fell to 0.58-0.75 everywhere, the lexical gate to 0.83-0.93, except one case where it rose from 0.75 to 0.85.)

### Findings

1. **The semantic signal is the better detector, and it degrades more gracefully.** AUROC 0.87 / 0.85 / 0.81 across original, P1 and P2, against 0.69 / 0.62 / 0.80 for the lexical one. The two are not clearly different on P2, and the confidence intervals overlap on every row, so call it a modest edge, not a proven one.
2. **A fitted threshold transfers better with `sem`.** At the keep-90% threshold, `sem` refuses 58% of bad answers at every level, while the lexical gate swings from 33% to 75% as the wording changes. Both lose good answers on plain-language rewrites (`sem` keeps 72%, lexical 66%): the rewrites sit slightly lower on the similarity scale.
3. **Neither is a strong gate on its own.** The bad answers (mean `sem` 0.79) sit close to the good ones (0.86); the whole usable range is under 0.1 cosine. Several bad answers are partly true or restate real chunk content (for example, "Ollama supports NVIDIA and AMD GPUs but Gaudi is not mentioned"), so they score as supported.
4. **The gate helps only the model that needs it.** 8B CAG on the quote prompt gains 3 questions (0.750 -> 0.825). Where the model already refuses well (32B, 8B on the cite prompt) the gate adds false refusals; for 32B CAG the semantic gate costs 3 questions. The lexical gate rarely changes anything at this threshold.
5. **Operating point matters more than the signal.** The Youden-optimal threshold (refuse all bad answers) destroys accuracy by dropping a third of good answers. For a gate, pick the threshold from the cost of a false refusal, and re-fit it per model and prompt.

### Caveats

- Small samples: 29 good and 12 bad answers (8 distinct questions) with bootstrap intervals that overlap. The bad set is dominated by the 8B model, and three of its fabrications are plausible real-world statements that the docs happen not to contain.
- Rewordings were produced by an 8B model, spot-checked on only a few, and cover answers that were already correct or already fabricated; they are not independent samples of model behaviour.
- The thresholds, and the end-to-end numbers, are in-sample: fitted on the same answers they are scored on (the rewordings are the only out-of-sample element).
- Cosine values depend on the embedding model (`nomic-embed-text`), the chunking and the Ollama version; a threshold does not carry over to another corpus.

## Follow-up 8: held-out test with 50 new questions (run 2026-10-23)

Everything above was developed on the same 40 questions. To test it out of sample I wrote **50 new questions** (`eval/docs_qa_new.jsonl`, split `new`): 10 answerable and **40 unanswerable**.
Each unanswerable question was kept only if none of its key terms appears anywhere in the corpus (`scripts/make_heldout.py` greps and drops those that do; 8 candidates were dropped, for example "export" and "LoRA adapters").
Both models were run on them with the quote prompt (8B with an f16 KV cache, 32B with `q8_0`, as before), and gate thresholds were **fitted on the original 40 and applied unchanged**.

```bash
python3 scripts/make_heldout.py
PYTHONPATH=src uv run python -m cag.evaluate --dataset docs --split new --n 50 --window 40960 --prompt quote --max-tokens 450 --systems cag,rag
PYTHONPATH=src uv run python -m cag.evaluate --dataset docs --split new --n 50 --model qwen2.5:32b-instruct-q4_K_M --window 32768 --ratio 0.85 --prompt quote --max-tokens 450 --systems cag,rag
PYTHONPATH=src uv run python scripts/replay_gate_heldout.py --pair 8B <dev-8b>.answers.jsonl <new-8b>.answers.jsonl --pair 32B <dev-32b>.answers.jsonl <new-32b>.answers.jsonl --fit-from 8B
PYTHONPATH=src uv run python scripts/replay_verify.py <new-run>.answers.jsonl --lenient --split new
```

### Ungated results, new questions (n=50)

| | 8B CAG | 8B RAG | 32B CAG | 32B RAG |
|---|---|---|---|---|
| Overall correct | **0.28** | 0.84 | **0.98** | 0.96 |
| Answerable correct (10) | 10/10 | 10/10 | 9/10 | 10/10 |
| Unanswerable refused (40) | **4/40 (0.10)** | 32/40 (0.80) | **40/40** | 38/40 |
| p50 latency (s) | 6.7 | 5.0 | **3.0** | 18.6 |
| Mean prefill (s) | 0.33 | 4.7 | 1.6 | 20.4 |

### Findings

1. **The dev set overstated 8B CAG's abstention, and it was already poor.** It refused 27% of unanswerable questions on dev and only 10% on the new ones: in 36 of 40 cases it answered a question the docs cannot answer. 8B RAG held steady (0.82 -> 0.80).
2. **The 32B model holds up out of sample.** CAG refused all 40 unanswerable questions and scored 0.98 overall (RAG 0.96). With the cache warm it answers in 3.0 s median against 18.6 s for RAG. Model scale mattered far more than any prompt or gate we tried.
3. **The "semantic is better" finding from follow-up 7 did not replicate.** Thresholds fitted on dev, applied to 8B answers on the new set (20 good, 44 fabricated answers): lexical support AUROC **0.90** [0.82, 0.97], semantic **0.66** [0.50, 0.80]. On dev the order was reversed (0.69 vs 0.87). Taken together the two sets say we cannot tell the signals apart with samples this small; the new set's much larger bad sample favours lexical.
   One untested explanation: many new fabrications are short generic denials ("Ollama does not support X") that sit near real chunks in embedding space but contain words found nowhere in the docs, which lexical coverage catches.
4. **Gates, with thresholds fixed on dev (correct rate, n=50):**

| | no gate | lexical support (keep-90% threshold) | semantic (keep-90%) | quote gate: strict | any_chunk | soft + relevance 25% | soft + relevance 50% |
|---|---|---|---|---|---|---|---|
| 8B CAG | 0.28 | **0.72** | 0.54 | 0.72 | 0.66 | 0.78 | 0.86 (half of answerable refused) |
| 8B RAG | 0.84 | **0.96** | 0.78 | 0.80 | 0.86 | 0.84 | 0.86 |
| 32B CAG | 0.98 | 0.96 | 0.96 | 0.82 | 0.84 | 0.82 | 0.82 |
| 32B RAG | 0.96 | 0.94 | 0.94 | 0.92 | 0.96 | 0.94 | 0.94 |

   For 8B a lexical support gate does the most for the least: CAG 0.28 -> 0.72 and RAG 0.84 -> 0.96, without touching the answerable questions. It still leaves 8B CAG well below 32B CAG. For 32B no gate helps; the quote gates cost 14-16 points because 32B does not follow the quote format.
   The 0.86 for `soft + relevance 50%` on 8B CAG comes from refusing 50% of the answerable questions; with only 10 answerable questions that is a coarse estimate.
5. **Rankings among quote gates changed between dev and held-out.** On dev `any_chunk`/`soft` were best for 8B CAG; on the new set `strict` beat them (0.72 vs 0.66 and 0.58). Gate ordering from 40 questions was not reliable.

### Caveats

- Only 10 answerable held-out questions, so false-refusal rates are poorly measured (one question = 10 points among answerable ones). The unanswerable side is better measured (40).
- I wrote the new unanswerable questions after seeing which kinds of questions fooled the 8B model, and they lean toward "feature does not exist" phrasings. 32B's 40/40 may partly reflect that style, and results on other question types are untested.
- Refusal and correctness are keyword and phrase matches. One run per model; thresholds still come from only 8-10 fabricated dev answers (32B had none, so it borrowed the 8B thresholds).
- Still one author (the AI assistant that built the project). The independent human review was waived by the owner on 2026-10-24; see the review status in doc 11.

## What to do next

1. Refit the gate on all 90 questions' answers, then test on a freshly written third set (ideally by a second author, with more answerable questions).
2. Try a model-based relevance pass ("does this quote answer the question?") in place of the lexical overlap, and test it on questions not used for tuning.
3. A second-person review of `eval/docs_qa.jsonl` was waived (doc 11 lists the known defects). If these numbers are ever relied on, do that review first and grow the answerable set.
4. Wire the chosen gate into the service and log rejected answers; they are a signal of corpus gaps.
