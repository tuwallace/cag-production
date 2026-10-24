# Targets mirror the CI tiers. PYTHONPATH=src is required (the project is not installed as a package).
export PYTHONPATH := src

.PHONY: test gate-fast gate-baseline gate-replay gate-model update-lock shadow-report

test:            ## 77+ offline unit tests (fake LLM, seconds)
	uv run pytest -q

gate-fast:       ## tests + corpus/question/prompt lock + token budget + gold specs (seconds, no model)
	uv run python scripts/ci_gate.py fast --with-tests

gate-baseline:   ## sanity-check the gate itself: the committed 32B baseline answers must pass the committed thresholds (seconds, no model)
	uv run python scripts/ci_gate.py replay --answers eval/baselines/32b-quote-dev.answers.jsonl eval/baselines/32b-quote-new.answers.jsonl --rag-answers eval/baselines/32b-quote-dev.answers.jsonl eval/baselines/32b-quote-new.answers.jsonl

gate-replay:     ## check saved answers against eval/gate.json: make gate-replay ANSWERS="reports/a.answers.jsonl reports/b.answers.jsonl"
	uv run python scripts/ci_gate.py replay --answers $(ANSWERS)

gate-model:      ## full docs eval on the production model (30-60 min, needs the dedicated Ollama on :11435 started with OLLAMA_KV_CACHE_TYPE=q8_0)
	CAG_OLLAMA_HOST=http://127.0.0.1:11435 uv run python scripts/ci_gate.py model --model qwen2.5:32b-instruct-q4_K_M --window 32768 --ratio 0.85 --prompt quote

update-lock:     ## after a deliberate corpus / question / prompt change AND a passing gate-model run
	uv run python scripts/ci_gate.py update-lock

shadow-report:   ## make shadow-report RECORDS=reports/shadow-8b.jsonl
	uv run python scripts/shadow_report.py $(RECORDS)
