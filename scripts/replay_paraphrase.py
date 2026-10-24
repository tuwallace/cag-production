"""Attribution on original vs paraphrased answers, for four attributors (no generation).
    PYTHONPATH=src uv run python scripts/replay_paraphrase.py eval/paraphrases.jsonl
Rows: levels = src (original answer), P1 (reworded), P2 (plain language), P2-clean (P2 rows that dropped every exact identifier of the source).
Methods: bm25, dense, hybrid, rerank, and ctrl = hybrid over the QUESTION alone. hit = any attributed chunk is gold; top1 = best chunk is gold;
prec = share of attributed chunks that are gold."""
import json, re, sys
from cag.adapters.docs_qa import build
from cag.attribution import Attributor, SemanticAttributor
from cag import metrics as M

ds = build(hybrid=False)
rows = [json.loads(l) for l in open(sys.argv[1])]
strip = lambda t: re.sub(r"\[[a-z0-9-]+(?:,\s*[a-z0-9-]+)*\]", " ", t)          # drop model-written ids so they cannot leak into attribution
IDENT = re.compile(r"[A-Z][A-Z0-9]*_[A-Z0-9_]{2,}|--[a-z][a-z-]+|ollama [a-z]{2,}|\b\d{4,5}\b")
def retained(r): return any(i in r["paraphrase"] for i in set(IDENT.findall(r["source"])))

methods = {"bm25": Attributor(ds.docs), "dense": SemanticAttributor(ds.docs, "dense"),
           "hybrid": SemanticAttributor(ds.docs, "hybrid"), "rerank": SemanticAttributor(ds.docs, "rerank")}
cases = {"src": [], "P1": [], "P2": [], "P2-clean": []}
seen = set()
for r in rows:
    if r["question"] not in seen:
        seen.add(r["question"]); cases["src"].append((r, r["source"]))
    cases[r["level"]].append((r, r["paraphrase"]))
    if r["level"] == "P2" and not retained(r):
        cases["P2-clean"].append((r, r["paraphrase"]))
print("P2 paraphrases that kept an exact identifier from the source:", sum(retained(r) for r in rows if r["level"] == "P2"), "/", sum(r["level"] == "P2" for r in rows))
print("level".ljust(10), "method".ljust(8), "n".ljust(4), "hit".ljust(7), "top1".ljust(7), "prec".ljust(7), "avg_ids", " sem")
for level, items in cases.items():
    for name in (*methods, "ctrl"):
        hit, top1, prec, n_ids, sem = [], [], [], [], []
        for r, text in items:
            g = set(r["gold"])
            at = (methods["hybrid"].attribute(r["question"]) if name == "ctrl" else methods[name].attribute(strip(text)))
            hit.append(float(bool(set(at.ids) & g))); top1.append(float(bool(at.ids) and at.ids[0] in g))
            prec.append(len(set(at.ids) & g) / len(at.ids) if at.ids else 0.0); n_ids.append(len(at.ids)); sem.append(at.sem)
        print(level.ljust(10), name.ljust(8), str(len(items)).ljust(4), f"{M.mean(hit):.3f}".ljust(7), f"{M.mean(top1):.3f}".ljust(7),
              f"{M.mean(prec):.3f}".ljust(7), f"{M.mean(n_ids):.1f}".ljust(7), f"{M.mean(sem):.2f}" if name != "bm25" else "-")
