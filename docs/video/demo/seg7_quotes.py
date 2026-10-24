"""Segment 7 on-screen demo: asking for quotes made the small model invent them. Offline, uses the committed 8B answers and the docs.   python docs/video/demo/seg7_quotes.py"""
import json, pathlib, sys, textwrap
ROOT = pathlib.Path(__file__).resolve().parents[3]; sys.path.insert(0, str(ROOT / "src"))
from cag.adapters.docs_qa import load_docs
from cag.metrics import normalize
from cag.systems import parse_quotes

docs = {d.id: d for d in load_docs()}
rows = [r for r in map(json.loads, open(ROOT / "eval" / "baselines" / "8b-quote-dev.answers.jsonl")) if r["system"] == "cag" and r["kind"] == "unanswerable"]
pick = ["mutual TLS", "timeout when pulling", "speech-to-text"]
print("\n  Questions the docs do NOT answer. The model was told to quote its evidence. What it quoted:\n")
for key in pick:
    r = next(x for x in rows if key in x["question"])
    print(f"  Q: {r['question']}")
    for q, doc_id in parse_quotes(r["answer"]):
        found = normalize(q) in normalize(docs[doc_id].text) if doc_id in docs else False
        print(textwrap.fill(f"\"{q}\"", 92, initial_indent="     ", subsequent_indent="      "))
        print(f"       cited section: {doc_id} ({docs[doc_id].title if doc_id in docs else '?'})   sentence is in that section: {'YES' if found else 'NO'}")
    print()
