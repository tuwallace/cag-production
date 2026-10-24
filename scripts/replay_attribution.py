"""Compare model-written citations with system-side attribution over SAVED generations (no model calls).
    PYTHONPATH=src uv run python scripts/replay_attribution.py reports/<run>.answers.jsonl [...]
Rows: model = ids the model wrote; sys = Attributor on the answer; sys+q = answer plus question; ctrl = BM25 on the question alone
(control: if sys is no better than ctrl, attribution adds nothing beyond retrieval). Only answerable questions with a non-refusal answer are scored."""
import json, sys, statistics as st
from cag.adapters.docs_qa import build
from cag.attribution import Attributor, SemanticAttributor
from cag.systems import parse_answer
from cag import metrics as M

ds = build(hybrid=False)
gold = {e.question: e for e in ds.examples}
variants = {"sys": Attributor(ds.docs), "hyb": SemanticAttributor(ds.docs, "hybrid"), "sys+q": Attributor(ds.docs, use_question=True)}
ctrl = Attributor(ds.docs)

def cell(v): return f"{v:.3f}" if isinstance(v, float) else str(v)

for path in sys.argv[1:]:
    rows = [json.loads(l) for l in open(path)]
    print(f"\n== {path.split('/')[-1]}")
    print("system".ljust(26), "n".ljust(4), "hit".ljust(7), "top1".ljust(7), "prec".ljust(7), "avg_ids".ljust(8), "support(ans/unans)")
    for name in dict.fromkeys(r["system"] for r in rows):
        if name.endswith("+verify") or name == "closed_book":
            continue
        rs = [r for r in rows if r["system"] == name and r["kind"] != "unanswerable" and not M.is_refusal(parse_answer(r["answer"]))]
        sup = {"ans": [], "unans": []}
        out = {"model": [], "sys": [], "hyb": [], "sys+q": [], "ctrl": []}
        for r in rs:
            g = set(r["gold"]); ex = gold[r["question"]]
            out["model"].append((sorted(r["cited"]), None))
            for v, a in variants.items():
                at = a.attribute(r["answer"], ex.question); out[v].append((at.ids, at.support))
            ctrl_ids = ctrl.bm25.get_scores(__import__("re").findall(r"[a-z0-9_]+", ex.question.lower()))
            top = [ctrl.ids[j] for j in sorted(range(len(ctrl.ids)), key=lambda j: -ctrl_ids[j])[:3]]
            out["ctrl"].append((top, None))
            sup["ans"].append(variants["sys"].attribute(r["answer"]).support)
        for u in [r for r in rows if r["system"] == name and r["kind"] == "unanswerable" and not M.is_refusal(parse_answer(r["answer"]))]:
            sup["unans"].append(variants["sys"].attribute(u["answer"]).support)
        for key, vals in out.items():
            gl = [set(r["gold"]) for r in rs]
            hit = M.mean([float(bool(set(ids) & g)) for (ids, _), g in zip(vals, gl)])
            top1 = M.mean([float(bool(ids) and ids[0] in g) for (ids, _), g in zip(vals, gl)]) if key != "model" else float("nan")
            prec = M.mean([len(set(ids) & g) / len(ids) if ids else 0.0 for (ids, _), g in zip(vals, gl)])
            avg = M.mean([len(ids) for ids, _ in vals])
            extra = f"{M.mean(sup['ans']):.2f} / {M.mean(sup['unans']):.2f} (n={len(sup['unans'])})" if key == "sys" and sup["unans"] else ""
            print(f"{name+' '+key:<26}", str(len(rs)).ljust(4), cell(hit).ljust(7), (cell(top1) if top1 == top1 else "-").ljust(7), cell(prec).ljust(7), f"{avg:.1f}".ljust(8), extra)
