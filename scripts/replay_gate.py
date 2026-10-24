"""Groundedness gate: lexical `support` (BM25 word coverage) vs semantic `sem` (best cosine to the attributed chunks), on original and
paraphrased answers. No generation. Needs Ollama (embeddings).
    PYTHONPATH=src uv run python scripts/replay_gate.py [runs.answers.jsonl ...]
good = correct answers to answerable questions (eval/paraphrases.jsonl); bad = non-refused (fabricated) answers to unanswerable questions
(eval/paraphrases_bad.jsonl). Each is scored as the original ('src') and two rewordings (P1, P2). A threshold is fitted on `src` only
(two operating points: Youden's J = best TPR - FPR, and "keep 90%" = the 10th percentile of good scores) and then applied unchanged to
P1/P2, which is the transfer test. AUROC is threshold-free."""
import json, random, re, sys
from cag.adapters.docs_qa import build
from cag.attribution import Attributor, SemanticAttributor
from cag import metrics as M

ds = build(hybrid=False)
strip = lambda t: re.sub(r"\[[a-z0-9-]+(?:,\s*[a-z0-9-]+)*\]", " ", t)
lex_att, sem_att = Attributor(ds.docs), SemanticAttributor(ds.docs, "hybrid")

def load(path, label):
    by = {}
    for l in open(path):
        r = json.loads(l)
        by.setdefault((r["question"], r["source"]), {"label": label, "src": r["source"]})[r["level"]] = r["paraphrase"]
    return list(by.values())

items = load("eval/paraphrases.jsonl", "good") + load("eval/paraphrases_bad.jsonl", "bad")
feat = {}
def features(text):
    if text not in feat:
        t = strip(text)
        feat[text] = {"lex": lex_att.attribute(t).support, "sem": sem_att.attribute(t).sem}
    return feat[text]

def auroc(pos, neg):
    if not pos or not neg: return float("nan")
    return M.mean([1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg])

def boot_ci(pos, neg, n=1000, seed=0):
    rng, vals = random.Random(seed), []
    for _ in range(n):
        vals.append(auroc([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg]))
    vals.sort(); return vals[int(.025 * n)], vals[int(.975 * n)]

def youden(pos, neg):
    best = (-1, 0)
    for t in sorted(set(pos + neg)):
        j = M.mean([float(p >= t) for p in pos]) - M.mean([float(x >= t) for x in neg])
        if j > best[0] or (j == best[0] and t > best[1]): best = (j, t)
    return best[1]

levels = {"src": lambda it: it["src"], "P1": lambda it: it["P1"], "P2": lambda it: it["P2"]}
tau, tau90 = {}, {}
print(f"good={sum(i['label']=='good' for i in items)} bad={sum(i['label']=='bad' for i in items)} (bad = {len({i['src'] for i in items if i['label']=='bad'})} fabricated answers)\n")
print("signal".ljust(6), "level".ljust(6), "AUROC [95% CI]".ljust(22), "tau(J)".ljust(7), "good kept".ljust(10), "bad refused".ljust(12), "tau(90%)".ljust(9), "good kept".ljust(10), "bad refused")
for sig in ("lex", "sem"):
    for lv, get in levels.items():
        pos = [features(get(i))[sig] for i in items if i["label"] == "good"]
        neg = [features(get(i))[sig] for i in items if i["label"] == "bad"]
        if lv == "src":
            tau[sig] = youden(pos, neg)
            tau90[sig] = sorted(pos)[int(0.1 * len(pos))]                    # keeps ~90% of good answers on src
        lo, hi = boot_ci(pos, neg)
        print(sig.ljust(6), lv.ljust(6), f"{auroc(pos, neg):.3f} [{lo:.2f}, {hi:.2f}]".ljust(22), f"{tau[sig]:.3f}".ljust(7),
              f"{M.mean([float(p >= tau[sig]) for p in pos]):.2f}".ljust(10), f"{M.mean([float(x < tau[sig]) for x in neg]):.2f}".ljust(12),
              f"{tau90[sig]:.3f}".ljust(9), f"{M.mean([float(p >= tau90[sig]) for p in pos]):.2f}".ljust(10), f"{M.mean([float(x < tau90[sig]) for x in neg]):.2f}")
    print()
print("sem mean good/bad by level:", {lv: (round(M.mean([features(get(i))['sem'] for i in items if i['label']=='good']), 3), round(M.mean([features(get(i))['sem'] for i in items if i['label']=='bad']), 3)) for lv, get in levels.items()})

# end-to-end, in-sample: apply tau to the original generations in saved runs
from cag.systems import parse_answer
if len(sys.argv) > 1:
    print("\nEnd-to-end on saved runs (tau fitted above on the same answers, so in-sample):")
    print("run / system".ljust(34), "ungated".ljust(9), "lex(J)".ljust(9), "sem(J)".ljust(9), "lex(90%)".ljust(9), "sem(90%)")
    for path in sys.argv[1:]:
        rows = [json.loads(l) for l in open(path)]
        for name in ("cag", "rag"):
            rs = [r for r in rows if r["system"] == name]
            out = {"none": [], "lex": [], "sem": [], "lex90": [], "sem90": []}
            for r in rs:
                final = parse_answer(r["answer"]); refused = M.is_refusal(final)
                f = features(final) if not refused else None
                for k in out:
                    rej = (not refused) and k != "none" and f[k[:3]] < (tau90 if k.endswith("90") else tau)[k[:3]]
                    out[k].append(float(r["no_answer"] or rej) if r["kind"] == "unanswerable" else float(r.get("correct") == 1.0 and not rej))
            print((path.split("-")[-1].split(".")[0] + " " + name).ljust(34), *[f"{M.mean(v):.3f}".ljust(9) for v in out.values()])
