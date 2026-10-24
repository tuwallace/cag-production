# Video script: "I tested CAG against RAG on my laptop. The trick mattered less than the model."

Target length: about 7.5 minutes (about 950 spoken words at 133 words a minute, the same pace as the helpdesk-rag video).
Format: hybrid, like the helpdesk-rag video. **ANIM** = an animated clip built from the numbers in Appendix A. **TERM** = a terminal segment whose
output comes from a script in `demo/` (either recorded live or shown as a labelled replay of captured output).
Narration is written to be read aloud; change anything that doesn't sound like you. The narrator is you, so lines about what the AI assistant did say so.

All numbers come from this repository's own runs: 90 questions about a 26k-token slice of Ollama's documentation, on one MacBook, with local models.
The questions were written by the AI assistant that built the project and were **not reviewed by a human** (the owner waived that review; `docs/11-roadmap-status.md`).
The video says so out loud, and `check_numbers.py` re-computes every number below from the repository.

## Segment plan

Times are estimates at 133 words a minute; replace them with the real audio lengths once the narration is rendered.

| # | Time | Segment | Type | Demo |
|---|---|---|---|---|
| 1 | 0:00 | Hook | ANIM | |
| 2 | 0:30 | What CAG is | ANIM | |
| 3 | 1:10 | The test: local models, 90 questions | ANIM | |
| 4 | 1:55 | Does the cache work? | TERM | `demo/seg4_cache.py` (live, about 3 minutes) |
| 5 | 2:30 | Surprise 1: the cache got evicted | ANIM | |
| 6 | 2:55 | The result: model size decided it | TERM | `demo/seg6_results.py` (offline) |
| 7 | 3:35 | Surprise 2: asking for quotes backfired | TERM | `demo/seg7_quotes.py` (offline) |
| 8 | 4:15 | Surprise 3: my own benchmark fooled me | ANIM | |
| 9 | 4:50 | When Ollama dies | TERM | `demo/seg9_outage.py` (replay of captured data) |
| 10 | 5:30 | Attacks and load | ANIM | |
| 11 | 6:15 | The regression gate | TERM | `demo/seg11_gate.py` (offline) |
| 12 | 6:45 | Takeaways | ANIM | |

---

## 1. Hook (0:00)

**Visual (ANIM):** title card, then a split screen: left "CAG, 8B model: 28% right", right "CAG, 32B model: 98% right", with "same data, same trick" between them.

**Narration:**
> What if your AI never had to search? Cache-augmented generation, CAG, loads a whole knowledge base into the model once, keeps the model's memory of it,
> and answers every question without a retrieval step. I tested it against RAG on my own machine, with real numbers. It works. But what decided whether it
> works wasn't the trick. It was the size of the model.

## 2. What CAG is (0:30)

**Visual (ANIM):** two lanes. Top lane, RAG: question → search → a few passages → model. Bottom lane, CAG: knowledge base → model reads it once → "KV cache" box →
each question reuses the box. Three red tags appear at the end: "must fit in the context window", "same text for everyone", "slow first request".

**Narration:**
> RAG looks up a few relevant passages for every question. CAG skips the lookup. You put the entire knowledge base into the prompt once, and the model computes
> its internal memory of that text, the KV cache. Every later question reuses that memory, so only the question itself has to be read. The catch: everything
> must fit in the model's context window, everyone gets the same text, and the first request is slow. It suits a small, stable knowledge base that people ask about a lot.

## 3. The test (1:10)

**Visual (ANIM):** the stack as icons (Ollama, Qwen 8B, Qwen 32B, one MacBook, "no cloud API"); a document stack labelled "Ollama docs: 118 sections, about 26,000 tokens";
then a bar of 90 questions split into 39 answerable and 51 "not in the docs", and a second split into 40 dev and 50 held out. Last frame: a caption "written by an AI assistant · no human review".

**Narration:**
> Everything here is local. Ollama, a Qwen eight-billion model and a Qwen thirty-two-billion model, on one MacBook, no cloud API. The knowledge base is a slice of
> Ollama's own documentation: a hundred and eighteen sections, about twenty-six thousand tokens. I built this with an AI coding assistant, and it wrote the ninety
> test questions. Fifty-one of them ask about things the documentation never says, because the right answer to those is: not in the knowledge base. Forty questions
> for development, fifty held back. No human reviewed them. I'll come back to that.

**On-screen caption:** "Ollama · qwen3:8b · qwen2.5:32b · 90 questions · 51 have no answer in the docs"

## 4. Does the cache work? (1:55)

**Visual (TERM):** run `demo/seg4_cache.py`. The table prints four rows: the cold first call (about 25,900 tokens read, two to three minutes) and three questions (almost all of the
prompt read from the cache, a fraction of a second to read it), then the line with the cache percentage. Speed up the wait during the first row.

**Narration:**
> First question: does the cache actually work? Here is the eight-billion model on the documentation. The first call has to read all twenty-six thousand tokens, which took me between two and three minutes.
> After that, reading the prompt takes a fraction of a second, because more than ninety-nine percent of it comes from the cache. With the thirty-two-billion model that first call takes eight and a half
> minutes. That cold start is the real price of CAG.

**On-screen caption:** "8B: 2-3 min cold, then ~0.4 s · 32B: ~8.5 min cold"

## 5. Surprise 1: the cache got evicted (2:30)

**Visual (ANIM):** one box labelled "Ollama server: 1 cache slot" holding a green "docs cache". A second model slides in and the green box turns grey; a stopwatch shows "65 s" again.
Then two boxes, one per server, both green: "dedicated Ollama for the cached model".

**Narration:**
> My first surprise. The cache lives inside Ollama, and one Ollama server has exactly one slot for it. When I loaded a second model for chat, it pushed the cache out, and the next question paid the full
> cold start again, sixty-five seconds in that test. The fix was a dedicated Ollama server for the cached model.

## 6. The result (2:55)

**Visual (TERM):** run `demo/seg6_results.py`. Four rows, two models by two methods. Hold on the 8B CAG row (28%, 4 of 40) and then on the 32B CAG row (98%, 40 of 40, 3.0 s).

**Narration:**
> Now the result, on the fifty held-out questions. The eight-billion model with CAG got twenty-eight percent right. It answered thirty-six of the forty questions the documentation can't answer,
> inventing details instead of saying it didn't know. RAG with the same small model got eighty-four. The thirty-two-billion model with CAG got ninety-eight percent, refused all forty unanswerable
> questions, and answered in three seconds, where RAG on the same model takes nineteen. Same trick, same data. The difference was the size of the model.

**On-screen caption:** "held-out: 50 questions, 40 with no answer in the docs"

## 7. Surprise 2: asking for quotes backfired (3:35)

**Visual (TERM):** run `demo/seg7_quotes.py`. Hold on the mutual-TLS question: the quoted sentence, the section it names, and the red "sentence is in that section: NO". Scroll to the other two.
Then an overlay: "citations 5% → 65%, but refusals 82% → 27%" (small model, first 40 questions).

**Narration:**
> I tried to make answers traceable by telling the model to quote its sources. Citations went from five percent to sixty-five percent. But the small model started inventing evidence. Asked about mutual TLS,
> which the documentation never mentions, it wrote a sentence that isn't in the documentation and pinned it on a real section. So I stopped asking the model. After it answers, I find the supporting section by
> matching the answer against the documents. That found the right section ninety-three to a hundred percent of the time.

**Honesty note:** in the demo output the second quote of the mutual-TLS question is a near-copy of a real sentence with a few words added; the check is word-for-word, so it says NO. Don't call it "made up".

## 8. Surprise 3: my own benchmark fooled me (4:15)

**Visual (ANIM):** two small bar charts. Left, "first 40 questions": semantic check 0.87, word-overlap check 0.69. Right, "50 new questions": semantic 0.66, word-overlap 0.90. An arrow flips between them.
Underneath: "small model refuses unanswerable questions: 27% (first 40) → 10% (new 50)".

**Narration:**
> The next surprise was about my own measurements. On the first forty questions, a semantic similarity check looked like the best way to catch invented answers. Then I wrote fifty new questions, and it flipped:
> the simple word-overlap check won. Forty questions had been too few to choose a method. The small model's refusal rate told the same story: twenty-seven percent on the first set, ten percent on the new one.
> Always keep questions you haven't tuned on.

**On-screen caption:** "AUROC: how well each check separates good answers from invented ones"

## 9. When Ollama dies (4:50)

**Visual (TERM, labelled replay):** run `demo/seg9_outage.py`. Hold on the 502 line, then the healthz 200 / readyz 503 line, then the recovery line.

**Narration:**
> A production service has to survive failures. So I killed Ollama in the middle of a request. The caller got an error in under a tenth of a second. The health check stayed up, readiness switched to not ready,
> and when I restarted Ollama the service re-read the whole knowledge base by itself and recovered, in two and a half minutes for the small model. For the big one, just re-reading takes eight and a half minutes,
> so you would want a second copy running.

**On-screen caption:** "REPLAY of a captured run (2026-10-23, qwen3:8b)"

## 10. Attacks and load (5:30)

**Visual (ANIM):** left, a document with a hidden line "ignore all other instructions": a checkmark "0 of 39 obeyed (both models)", then a red mark "1 tracking link (32B)", then a red mark "false fact repeated: 2 of 2".
Middle, a card with planted values (email, phone, card, key, SSN): "5 of 5 leaked" turning into "0 of 5" after "redaction". Right, a queue graphic: "about 5 requests a minute", extra requests bounced with "10 ms".

**Narration:**
> Then I attacked it. I hid instructions inside the documents. Neither model obeyed a command like ignore your rules, but the bigger one followed a hidden instruction once and added a tracking link, and both repeated a
> false fact I planted as if it were true. No prompt fixes that: you have to control what goes into the knowledge base. A test asking for planted emails, card numbers and keys got all five back, until I added redaction.
> And under load the service handles about five requests a minute however many people ask, so now it turns the extras away in ten milliseconds.

## 11. The regression gate (6:15)

**Visual (TERM):** run `demo/seg11_gate.py`. Hold on the first PASS, then on the FAIL line after the one-fact change, then the 8B model failing the same thresholds.

**Narration:**
> Last, I wanted to catch regressions. A gate re-runs the questions and fails if accuracy or abstention drops below thresholds taken from the held-out results. It also locks the knowledge base and the prompt: change
> one fact in the documentation and the check fails until you re-run the full evaluation. It runs in seconds, and a secret scanner checks every push.

## 12. Takeaways (6:45)

**Visual (ANIM):** five bullets, one at a time, then a closing card with the caveat line.

**Narration:**
> Five things. One: CAG fits a small, stable knowledge base that gets asked about a lot. Two: the cache is the product, so budget for the cold start. Three: model size mattered more than any trick I tried. Four: measure
> what happens on questions the knowledge base can't answer. Five: keep questions you didn't tune on. Everything here is local and open, with the caveats stated: one machine, ninety questions written by an AI, no human review.

---

## Appendix A: data for the animated clips (re-computed by `check_numbers.py`)

Entries with a `source` are checked against the text of that file in this repository; the rest are re-computed from `eval/baselines/`, `demo/data/` and the corpus.

```json
{
  "corpus": {"sections": 118, "files": 15, "prompt_tokens_thousands_qwen3": 26},
  "questions": {"total": 90, "dev": 40, "held_out": 50, "unanswerable": 51, "answerable": 39, "held_out_unanswerable": 40},
  "held_out": {
    "8b_cag":  {"correct": 0.28, "unanswerable_refused": 4,  "p50_s": 6.7},
    "8b_rag":  {"correct": 0.84, "unanswerable_refused": 32, "p50_s": 5.0},
    "32b_cag": {"correct": 0.98, "unanswerable_refused": 40, "p50_s": 3.0},
    "32b_rag": {"correct": 0.96, "unanswerable_refused": 38, "p50_s": 18.6}
  },
  "small_model_unanswerable_refused": {"first_40": "3 of 11", "new_50": "4 of 40"},
  "cache": {"hit_ratio": 0.997, "cold_8b_s_range": [147, 175], "cold_32b_s": 508, "eviction_cold_again_s": 65.7},
  "quotes": {"citations_before": 0.05, "citations_after": 0.65, "refused_before": 0.82, "refused_after": 0.27, "system_side_hit_range": [0.93, 1.0]},
  "check_flip_auroc": {"first_40": {"semantic": 0.87, "word_overlap": 0.69}, "new_50": {"semantic": 0.66, "word_overlap": 0.90}},
  "outage": {"inflight_error_s": 0.08, "idle_detected_s": 3.1, "recovered_s": 147},
  "security": {"commands_obeyed": "0 of 39", "tracking_link_32b": "1 of 39", "false_fact_adopted": "2 of 2", "pii_leaked_raw": 5, "pii_leaked_redacted": 0},
  "load": {"requests_per_minute": 5, "bounce_ms": 10},
  "gate": {"overall_min": 0.85, "unanswerable_min": 0.9, "checks_on_32b": "pass", "checks_on_8b": "fail"}
}
```

Where the recorded (not re-computed) numbers come from: cold starts and eviction `docs/08-prototype.md`, `docs/12-security-tests.md`; quote and check-flip numbers `docs/09-docs-qa-results.md`;
security and load `docs/12-security-tests.md`.

## Appendix B: before you record

1. Start the dedicated Ollama: `OLLAMA_HOST=127.0.0.1:11435 OLLAMA_NUM_PARALLEL=1 OLLAMA_FLASH_ATTENTION=1 ollama serve` (a separate terminal), and check `ollama list` shows `qwen3:8b`.
2. Sync the project: `uv sync --python 3.12 --group helpdesk` (a plain `uv sync` removes the helpdesk packages).
3. Segment 4 is the only slow one (about 3 minutes, the first row). Record it once and speed up the wait, or record it twice: once for the cold row, once for the warm rows.
4. Close notifications, use a large terminal font and a short prompt (`PROMPT='$ '`), and do not show `.env` or any file under `~/.config`.
5. Rehearse each demo once. Segment 4's timings will differ by a few seconds from the narration; the narration says "about".
6. Record each segment separately so you can re-take one without redoing the video. Details and cue tables: `recording-guide.md`.

## Appendix C: upload text

**Title options**
- "I tested CAG against RAG on my laptop. The trick mattered less than the model."
- "Cache-augmented generation vs RAG: real numbers, run locally with Ollama"
- "CAG: 28% right, then 98%. What changed?"

**Thumbnail text:** "CAG: 28% → 98%" (big), with "same data · same trick · bigger model" underneath.

**Description (draft)**
```
Cache-augmented generation (CAG) loads a whole knowledge base into the model once and reuses the model's memory of it, instead of searching for every question.
I tested it against RAG on a MacBook with local models (Ollama; Qwen 3 8B and Qwen 2.5 32B): what the cache costs, what surprised me, how it failed, and how I
checked it.

Chapters
0:00 Hook
0:30 What CAG is
1:10 The test
1:55 Does the cache work?
2:30 Surprise 1: the cache got evicted
2:55 The result
3:35 Surprise 2: asking for quotes backfired
4:15 Surprise 3: my own benchmark fooled me
4:50 When Ollama dies
5:30 Attacks and load
6:15 The regression gate
6:45 Takeaways

Caveats: one machine, one run per setting, 90 test questions about a 26k-token slice of Ollama's documentation. The questions were written by an AI coding assistant and
were not reviewed by a human; treat the numbers as a comparison of setups on the same questions, not as a benchmark.

Knowledge base: Ollama's documentation (MIT licence, github.com/ollama/ollama). Models: Qwen (Alibaba Cloud), run with Ollama; check their licences before reuse.
Code and commands: <link when the repository is public>
```

**Tags:** CAG, cache-augmented generation, RAG, Ollama, local LLM, Qwen, KV cache, prompt caching, AI engineering, evaluation

**Disclosure:** the narration is synthetic if you use a synthetic voice, and the test questions were written by an AI assistant. If you use synthetic narration or AI-generated visuals that could be
mistaken for real footage, use YouTube's altered/synthetic content disclosure when uploading. Real screen recordings and charts don't need it. Replay segments should stay labelled as replays on screen.
