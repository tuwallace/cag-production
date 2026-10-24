# 13. Phase 8: regression gate and shadow mode

Built 2026-10-24. Scripts: `scripts/ci_gate.py`, `scripts/shadow_run.py`, `scripts/shadow_report.py`; modules `src/cag/gate.py`, `src/cag/shadow.py`; `Makefile`; `ci/workflow.example.yml` (an example for GitHub Actions: written, **not run on any CI system**, because the project is not in a git repository).

## Part 1: the regression gate

**Three tiers**, because the full evaluation is slow (about 30-60 minutes on the 32B model, 8.5 minutes of it the cold prefill):

| Tier | Time | Needs a model | What it checks |
|---|---|---|---|
| `fast` (`make gate-fast`) | ~5 s | no | the unit tests; a **lock** of the corpus hash, the question files and the prompt text; the token budget; every gold spec still resolves |
| `replay` | seconds | no | saved answers against the thresholds (also used to calibrate and to test the gate itself) |
| `model` (`make gate-model`) | 30-60 min | yes | runs the docs eval (90 questions) on the production configuration, then applies the same checks |

Exit code 0 = pass (warnings allowed), 1 = a failing check, 2 = error (no data).

**The lock.** `eval/corpus.lock.json` stores the corpus hash, the document count, a hash of both question files and a hash of the prompt text. If any of them changes, the fast tier fails with "unchanged" marked FAIL until the model tier has been re-run and `update-lock` executed. This is what keeps a silent edit to a document or the prompt from invalidating the baseline (the thresholds only mean something for the corpus and prompt they were measured on).

**Thresholds** (`eval/gate.json`) come from the held-out baseline: the 32B model with the quote prompt on all 90 questions (dev run and held-out run). Each is the Wilson 95% bound of the baseline proportion, rounded outward to 0.05, so ordinary sampling noise does not fail a build:

| Check | Baseline | Gate | Severity |
|---|---|---|---|
| overall correct | 85/90 = 0.944 | >= 0.85 | fail |
| unanswerable refused | 51/51 = 1.00 | >= 0.90 | fail |
| answerable correct | 34/39 = 0.872 | >= 0.70 | fail |
| false refusal (answerable questions refused) | 4/39 = 0.103 | <= 0.25 | fail |
| cache hit ratio | 0.997 | >= 0.95 | fail (a prefix that is no longer byte-stable, such as a timestamp in the prompt, shows up here) |
| p50 latency | 3.1 s | <= 9.3 s (3x) | warn only: hardware dependent |
| CAG minus RAG, overall correct / unanswerable refused | -0.011 / +0.039 | >= -0.05 | fail (only when RAG answers are supplied) |

**What the gate can and cannot catch** (exact binomial, probability that the check fails when the true rate is p; sample sizes are the baseline's):

| True rate p | 0.99 | 0.95 | 0.90 | 0.85 | 0.80 | 0.70 | 0.60 |
|---|---|---|---|---|---|---|---|
| unanswerable refused (n=51, needs 46) | 0.00 | 0.04 | 0.40 | 0.80 | 0.96 | 1.00 | 1.00 |
| overall correct (n=90, needs 77) | 0.00 | 0.00 | 0.06 | 0.49 | 0.88 | 1.00 | 1.00 |
| answerable correct (n=39, needs 28) | 0.00 | 0.00 | 0.00 | 0.01 | 0.07 | 0.52 | 0.91 |

It rarely cries wolf if the true rate is still near the baseline (4% at a true unanswerable rate of 0.95), and it almost always catches a collapse to 80% or lower (96% or more), but a slide in abstention to 90% passes about 60% of the time and to 85% still passes 20% of the time. Answerable correctness is the weakest check (39 questions, only 52% detection even at a true 0.70). More questions would tighten it; the unanswerable side has the most.

**Checked on saved runs (no model):** the 32B baseline passes all 8 checks including the RAG-relative ones; the 8B CAG runs on the same 90 questions **fail** `overall_correct` (0.489) and `unanswerable_refused` (0.137), correctly, and pass the answerable-side checks (the 8B model rarely refuses an answerable question; its problem is fabrication). Tests (`tests/test_gate.py`, 11) cover the Wilson bounds, calibration, regressions in each metric, the cache-hit collapse, no-data failing instead of passing, the relative gate, lock detection (and that the committed lock matches the repository), and the CLI exit codes. They caught a real flaw while being written: `0.9 - 0.95` fails a `>= -0.05` bound by floating-point error, now tolerated with an epsilon.

**Model tier, run end to end (2026-10-24).** `ci_gate.py model` on qwen2.5:32b (quote prompt, 90 questions, dedicated Ollama with a `q8_0` KV cache) ran from a cold start and **passed all six checks** (0.944 overall, 51/51 unanswerable refused, 0.872 answerable correct, 0.103 false refusal, cache hit ratio 0.997, p50 3.1 s). All 90 answers were **byte-identical** to the baseline answers saved two days earlier, so with the same model, quantisation, prompt and temperature 0 the pipeline is fully reproducible.
That makes the gate sharp for detecting *any* change, but it also means this passing run says nothing about run-to-run noise; noise appears when the model, the quantisation, the Ollama version or the prompt changes, which is when the thresholds (and the lock) earn their keep. The gate was never run against a deliberately broken model; its failure path was exercised on saved 8B answers and in the unit tests.

**Repository and CI rehearsal (2026-10-24).** The project is now a git repository (branch `main`, first commit `69567ee`, 90 files). Not tracked: `.venv`, `.env`, caches, everything generated in `reports/`, the embedding cache. Tracked on purpose: the Ollama-docs slice with its MIT licence (the lock and the gate depend on it), the 32B baseline answers in `eval/baselines/`, and `uv.lock`.
The example workflow's fast job was rehearsed locally on a **fresh clone** in a scratch directory: `uv sync --python 3.12` (162 packages), then `make gate-fast` and `make gate-baseline`. Results: gate-fast passed (lock, budget, gold specs, 95 tests); the committed baseline answers pass the committed thresholds; the working tree stayed clean. With Ollama unreachable the suite gives 94 passed, 1 skipped (the one test that needs embeddings), which is what a CI runner without a model would see.
Negative check: changing one fact inside an existing chunk (`port 11434` to `11435` in `faq.mdx`) made `make gate-fast` fail on `lock:corpus_sha` and on the unit test that guards the lock, and exit non-zero; restoring the file made it pass again.
Two gotchas from this: (1) the chunker drops any section shorter than 40 characters, so appending a tiny new section to a doc changes neither the corpus nor the lock; edits inside existing chunks and any section of 40+ characters are caught. (2) The corpus loader reads every `*.md*` file in `data/ollama-docs/`, so adding a README or notice there (use `SOURCE.txt`) silently changes the corpus.
This was **not** run on a hosted CI service: there is no remote, and `ci/workflow.example.yml` has never been executed.

## Part 2: shadow mode

**Design** (`src/cag/shadow.py`, 7 tests). The incumbent (RAG) answers the caller. The candidate (CAG) answers the same question in a separate worker with a bounded backlog (`max_pending`); anything that does not fit is **dropped and counted**, never queued forever. The caller never waits for the candidate, a candidate crash or timeout is recorded as a finding and cannot reach the caller, and a primary error propagates unchanged. Each comparison record has: refusal agreement, word overlap of the two answers, overlap of the cited chunks, both latencies. `store_text` is `none` on real traffic (hashes and metrics only), `redacted` (PII-scrubbed text) or `full` (experiments only).

**Promotion criteria** (`scripts/shadow_report.py`):
- C1 candidate errors <= 1%.
- C2 fabrication regression <= 5 points (on labelled data: candidate answers no more unanswerable questions than the primary; on unlabelled traffic the proxy is "candidate answered where the primary refused", which needs human review).
- C3 candidate correctness >= primary - 0.05.
- C4 (information) candidate p50 latency <= primary p50.
Verdict is "promote" only if C1-C3 pass.

**Results.** Candidate CAG vs incumbent RAG, quote prompt, 90 questions (40 dev + 50 held-out; 51 unanswerable):

| Run | Compared | Primary correct | Candidate correct | Candidate fabricates where primary refuses | Verdict |
|---|---|---|---|---|---|
| 32B, offline pairing of saved answers | 90 | 0.956 | 0.944 | 0 cases (0%); candidate refused where primary answered: 5 (6%) | **promote** (C1-C4 pass) |
| 8B, offline pairing of saved answers | 90 | 0.856 | 0.489 | 35 cases (39%); 34 were fabrications | hold (C2, C3 fail) |
| 8B, **live** shadow run | 51 of 90 | 0.804 | 0.510 | 15 of 51 (29%), all on unanswerable questions | hold (C2, C3 fail) |

- **32B:** CAG matches RAG on correctness (83 questions right for both; 3 only RAG; 2 only CAG; 2 neither), never fabricates where RAG refused, and answers in a median 3.1 s against RAG's 26.6 s. Its weakness is answerable questions: 0.872 against RAG's 0.949 (CAG refused 5 answers that RAG gave), made up for by perfect abstention (51/51 against RAG's 49/51).
- **8B:** the live run reached the same verdict as the offline pairing. The agreement signal alone (refusal agreement 0.71 live, 0.61 offline; the candidate answering where the primary refuses) flags the problem without labels, which is what a real deployment would have.
- **The live run thinned itself.** Requests came back to back; the candidate (CAG on 8B) took longer than the incumbent per question, so its bounded backlog filled and **39 of 90 comparisons were dropped** (43%). That is the designed behaviour, but a shadow candidate must have at least the primary's throughput or the sample shrinks and may be biased toward the questions it answers quickly. `--interval` paces the traffic.
- **"Off the request path" is logical, not physical, on one machine.** Both models ran on the same GPU, so the incumbent's median latency rose to 10.8 s from 7.2 s in the standalone runs, and the candidate's to 17.0 s from 6.9 s. Shadow mode on shared hardware slows the primary; real use needs separate hardware.
- **Cache isolation:** one Ollama server has one prefix-cache slot, so a RAG request (a new prompt every time) would evict CAG's cached corpus. The live run used two Ollama servers (:11434 for RAG, :11435 for CAG); candidate cache hit ratio stayed about 0.997.

## Limits of what was done

- The "live" shadow run used eval questions with labels, not real traffic, and 8B models. The decisive 32B comparison is an offline pairing of two completed runs, which uses the same records and criteria but was not run through the shadow runner; a live 32B shadow needs two 24 GB models and does not fit on this machine.
- A promotion verdict from 90 questions is a screen, not proof; thresholds were not tuned on the shadow data.
- The shadow runner is a library and script; it is not yet wired into the service.
- There is no canary rollout, traffic splitter or automatic rollback.
