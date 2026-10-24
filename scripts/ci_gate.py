"""CI-style regression gate. Exit 0 = pass (warnings allowed), 1 = fail, 2 = error.
    fast   (seconds, no model): unit tests (--with-tests), corpus / question / prompt lock, token budget, gold specs resolve
    replay (seconds, no model): check saved answers against the thresholds
    model  (about 30-60 min, needs the model): run the docs eval, then check it
    PYTHONPATH=src uv run python scripts/ci_gate.py fast --with-tests
    PYTHONPATH=src uv run python scripts/ci_gate.py replay --answers reports/<a>.answers.jsonl reports/<b>.answers.jsonl [--rag-answers ...]
    CAG_OLLAMA_HOST=... PYTHONPATH=src uv run python scripts/ci_gate.py model --model qwen2.5:32b-instruct-q4_K_M --window 32768 --ratio 0.85 --prompt quote
    PYTHONPATH=src uv run python scripts/ci_gate.py calibrate --answers ... [--rag-answers ...]   # (re)write eval/gate.json from a baseline
    PYTHONPATH=src uv run python scripts/ci_gate.py update-lock                                    # after re-running the model tier on a changed corpus/prompt"""
import argparse, json, subprocess, sys, time, pathlib
from cag import gate as G

def show(checks) -> int:
    print(f"{'check':<34} {'observed':>9}  {'bound':<14} n    result")
    bad = 0
    for c in checks:
        res = "ok" if c.ok else ("WARN" if c.severity == "warn" else "FAIL")
        bad += (not c.ok) and c.severity == "fail"
        print(f"{c.name:<34} {str(c.observed):>9}  {c.bound:<14} {str(c.n or ''):<4} {res}")
    print("\nGATE:", "FAILED" if bad else "passed", f"({bad} failing check{'s' if bad != 1 else ''})")
    return 1 if bad else 0

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("tier", choices=["fast", "replay", "model", "calibrate", "update-lock"])
    ap.add_argument("--answers", nargs="*", default=[]); ap.add_argument("--rag-answers", nargs="*", default=[]); ap.add_argument("--system", default="cag")
    ap.add_argument("--with-tests", action="store_true"); ap.add_argument("--gate", default=str(G.GATE_FILE))
    ap.add_argument("--model"); ap.add_argument("--window", type=int, default=32768); ap.add_argument("--ratio", type=float, default=0.85)
    ap.add_argument("--prompt", default="quote"); ap.add_argument("--with-rag", action="store_true")
    a = ap.parse_args()

    if a.tier == "update-lock":
        G.LOCK_FILE.write_text(json.dumps(G.lock_state(), indent=2) + "\n"); print("wrote", G.LOCK_FILE); return 0

    if a.tier == "fast":
        checks = G.check_lock()
        from cag.adapters.docs_qa import build, load_docs
        from cag.corpus import build_corpus, check_budget
        gate = json.loads(pathlib.Path(a.gate).read_text()); prof = gate["profile"]
        try:
            check_budget(build_corpus(load_docs()), prof["window"], prof["ratio"]); checks.append(G.Check("token budget", None, f"<= {prof['ratio']:.0%} of {prof['window']}", True, "fail"))
        except ValueError as e:
            checks.append(G.Check("token budget", None, str(e)[:40], False, "fail"))
        try:
            n = len(build(hybrid=False, split="all").examples); checks.append(G.Check("gold specs resolve", n, "all questions", True, "fail"))
        except ValueError as e:
            checks.append(G.Check("gold specs resolve", None, str(e)[:40], False, "fail"))
        if a.with_tests:
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x"], env={**__import__("os").environ, "PYTHONPATH": "src"}, capture_output=True, text=True)
            checks.append(G.Check("unit tests", None, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output", r.returncode == 0, "fail"))
        return show(checks)

    if a.tier == "calibrate":
        rows = G.load_rows(a.answers, a.system)
        prof = {"system": a.system, "model": a.model or "qwen2.5:32b-instruct-q4_K_M", "prompt": a.prompt, "window": a.window, "ratio": a.ratio, "questions": "docs dev+new (90)"}
        gate = G.calibrate(rows, prof, [pathlib.Path(p).name for p in a.answers])
        pathlib.Path(a.gate).write_text(json.dumps(gate, indent=2) + "\n"); print(json.dumps(gate["metrics"], indent=1)); return 0

    gate = json.loads(pathlib.Path(a.gate).read_text())
    if a.tier == "model":
        from dotenv import load_dotenv; load_dotenv()
        from cag.adapters.docs_qa import build
        from cag.evaluate import run
        from cag.llm import OllamaLLM
        ds = build(split="all")
        rep = run(ds, OllamaLLM(a.model or gate["profile"]["model"], num_ctx=a.window, max_tokens=450), systems=("cag", "rag") if a.with_rag else ("cag",),
                  window=a.window, ratio=a.ratio, style=a.prompt)
        out = pathlib.Path("reports") / f"gate-run-{time.strftime('%Y%m%d-%H%M%S')}.answers.jsonl"
        out.write_text("\n".join(json.dumps(x) for x in rep["_answers"]) + "\n"); print("answers saved:", out)
        a.answers, a.rag_answers = [str(out)], ([str(out)] if a.with_rag else [])
    rows = G.load_rows(a.answers, a.system)
    if not rows:
        print("no rows for system", a.system); return 2
    checks = G.check(rows, gate, G.load_rows(a.rag_answers, "rag") if a.rag_answers else None)
    code = show(checks)
    pathlib.Path("reports").mkdir(exist_ok=True)
    pathlib.Path("reports", f"gate-{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(json.dumps([c.__dict__ for c in checks], indent=1))
    return code

if __name__ == "__main__":
    sys.exit(main())
