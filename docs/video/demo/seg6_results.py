"""Segment 6 on-screen demo: the held-out results. Offline, reads the committed answers in eval/baselines/.   python docs/video/demo/seg6_results.py"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[3]; sys.path.insert(0, str(ROOT / "src"))
from cag.metrics import pct

def rows(name, system): return [r for r in map(json.loads, open(ROOT / "eval" / "baselines" / name)) if r["system"] == system]
print("\n  Held-out questions: 50, of which 40 have NO answer in the docs (right answer: \"not in the knowledge base\")\n")
print(f"  {'model':<12}{'method':<8}{'answered right':>16}{'refused the 40':>16}{'median time':>14}")
for model, file in (("qwen3 8B", "8b-quote-new.answers.jsonl"), ("qwen2.5 32B", "32b-quote-new.answers.jsonl")):
    for system in ("cag", "rag"):
        rs = rows(file, system); un = [r for r in rs if r["kind"] == "unanswerable"]
        print(f"  {model:<12}{system.upper():<8}{sum(r['correct'] == 1.0 for r in rs) / len(rs):>15.0%} {sum(r['correct'] == 1.0 for r in un):>10} of {len(un)}{pct([r['latency_s'] for r in rs], .5):>12.1f} s")
print()
