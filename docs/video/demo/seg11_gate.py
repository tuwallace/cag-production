"""Segment 11 on-screen demo: the regression gate. Offline and safe: works on a throw-away copy of the last commit (plus eval/baselines), never on your files.   python docs/video/demo/seg11_gate.py"""
import pathlib, shutil, subprocess, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[3]; PY = sys.executable
tmp = pathlib.Path(tempfile.mkdtemp(prefix="cag-gate-demo-"))
subprocess.run(f"git -C {ROOT} archive HEAD | tar -x -C {tmp}", shell=True, check=True)
shutil.copytree(ROOT / "eval" / "baselines", tmp / "eval" / "baselines", dirs_exist_ok=True)   # include baselines that are not committed yet
def run(label, cmd):
    print(f"\n  $ {label}", flush=True)
    r = subprocess.run(cmd, cwd=tmp, env={"PYTHONPATH": str(tmp / "src"), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    for l in lines[:10]: print("    " + l)
    if not lines and r.stderr: print("    " + r.stderr.strip().splitlines()[-1])
    print(f"    exit code {r.returncode}")
try:
    base = ["eval/baselines/32b-quote-dev.answers.jsonl", "eval/baselines/32b-quote-new.answers.jsonl"]
    run("make gate-baseline        # 32B answers vs the thresholds", [PY, "scripts/ci_gate.py", "replay", "--answers", *base])
    run("same check on the 8B model's answers", [PY, "scripts/ci_gate.py", "replay", "--answers", "eval/baselines/8b-quote-dev.answers.jsonl", "eval/baselines/8b-quote-new.answers.jsonl"])
    run("make gate-fast            # lock on the docs, questions and prompt", [PY, "scripts/ci_gate.py", "fast"])
    faq = tmp / "data/ollama-docs/faq.mdx"; faq.write_text(faq.read_text().replace("Ollama binds 127.0.0.1 port 11434 by default", "Ollama binds 127.0.0.1 port 11435 by default", 1))
    print("\n  (change ONE fact in the docs: port 11434 -> 11435)")
    run("make gate-fast", [PY, "scripts/ci_gate.py", "fast"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print()
