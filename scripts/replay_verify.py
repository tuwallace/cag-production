"""Replay the verbatim-quote gate over SAVED generations (no model calls): same answers, different gate policy.
    PYTHONPATH=src uv run python scripts/replay_verify.py reports/<run>.answers.jsonl [--lenient] [--split dev|new]"""
import json, sys
from cag.adapters.docs_qa import build
from cag.evaluate import score, summarize, _usage_of
from cag.attribution import Attributor
from cag.systems import Result, NO_ANSWER, verify_quotes, verify_soft, true_sources

SPLIT = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else "dev"   # must match the split the answers were generated on
ds = build(hybrid=False, split=SPLIT)
ATTR = Attributor(ds.docs)
doc_text = {d.id: d.text for d in ds.docs}
LEN = "--lenient" in sys.argv     # also accept `> text [id]` quotes without quote marks
raw = [json.loads(l) for l in open(sys.argv[1])]
keys = ["correct", "acc_single", "acc_multi", "acc_unanswerable", "false_refusal", "rejected", "cite_hit"]
print("system".ljust(22), *[k[:13].ljust(13) for k in keys])
for name in ("cag", "rag"):
    MODES = ("strict", "any_chunk", "soft", "soft_rel25", "soft_rel50", "support50", "support60")
    rows_by_name = {n: [] for n in (name, *[f"{name}+{m}" for m in MODES])}
    for a, ex in zip([r for r in raw if r["system"] == name], ds.examples):
        base = Result(a["raw_answer"] if "raw_answer" in a else a["answer"], set(a["cited"]), _usage_of(a), a["latency_s"], a["retrieved"])
        rows_by_name[name].append(score(name, ex, base, doc_text))
        for mode in MODES:
            if mode in ("strict", "any_chunk"):
                ok, _ = verify_quotes(base.answer, doc_text, mode, LEN)
                cited = (true_sources(base.answer, doc_text, LEN) if mode == "any_chunk" else base.cited) if ok else set()
            elif mode.startswith("support"):             # system-side: refuse if <NN% of the answer's content words are in the attributed chunks
                at = ATTR.attribute(base.answer)
                ok, cited = (at.support >= int(mode[7:]) / 100 or not at.ids), set(at.ids)
                if base.answer.strip().lower().startswith("not in the knowledge base"): ok, cited = True, set()
            else:                                       # soft: drop bad quotes; soft_relNN also needs relevance >= NN%
                rel = {"soft": 0.0, "soft_rel25": 0.25, "soft_rel50": 0.50}[mode]
                ok, _, cited = verify_soft(base.answer, doc_text, ex.question, rel, LEN)
            res = Result(base.answer if ok else NO_ANSWER, cited if ok else set(), base.usage, base.latency_s, base.retrieved)
            row = score(f"{name}+{mode}", ex, res, None); row["rejected"] = float(not ok)
            rows_by_name[f"{name}+{mode}"].append(row)
    for n, rows in rows_by_name.items():
        s = summarize(rows)
        print(n.ljust(22), *[(f"{s[k]:.3f}" if k in s else "-").ljust(13) for k in keys])
