"""Held-out test of the groundedness gate: fit thresholds on the dev questions' answers, apply them unchanged to answers to the NEW questions.
    PYTHONPATH=src uv run python scripts/replay_gate_heldout.py --pair 8B dev.answers.jsonl new.answers.jsonl [--pair 32B dev.jsonl new.jsonl] [--fit-from 8B]
Signals: lex = BM25 word coverage (`support`), sem = best cosine to the attributed chunks. good = correct answers to answerable questions,
bad = non-refused answers to unanswerable questions. Thresholds: J = Youden's J, 90 = keeps 90% of good dev answers. Pairs with fewer than
3 bad dev answers cannot be fitted and borrow the thresholds of --fit-from (cross-model transfer)."""
import argparse, json, random, re
from cag.adapters.docs_qa import build
from cag.attribution import Attributor, SemanticAttributor
from cag.systems import parse_answer
from cag import metrics as M

ap = argparse.ArgumentParser()
ap.add_argument("--pair", nargs=3, action="append", metavar=("NAME", "DEV", "NEW"), required=True)
ap.add_argument("--fit-from", default=None)
a = ap.parse_args()

ds = build(hybrid=False, split="all")
strip = lambda t: re.sub(r"\[[a-z0-9-]+(?:,\s*[a-z0-9-]+)*\]", " ", t)
lex_att, sem_att = Attributor(ds.docs), SemanticAttributor(ds.docs, "hybrid")
_f = {}
def feats(final):
    if final not in _f:
        t = strip(final); _f[final] = {"lex": lex_att.attribute(t).support, "sem": sem_att.attribute(t).sem}
    return _f[final]

def rows_of(path):
    out = []
    for l in open(path):
        r = json.loads(l)
        if r["system"] not in ("cag", "rag"): continue
        final = parse_answer(r["answer"]); r["_final"] = final; r["_refused"] = M.is_refusal(final)
        out.append(r)
    return out

def split_gb(rows):
    good = [feats(r["_final"]) for r in rows if r["kind"] != "unanswerable" and not r["_refused"] and r.get("correct") == 1.0]
    bad = [feats(r["_final"]) for r in rows if r["kind"] == "unanswerable" and not r["_refused"]]
    return good, bad

def auroc(pos, neg):
    return M.mean([1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg]) if pos and neg else float("nan")

def ci(pos, neg, n=1000):
    rng, v = random.Random(0), []
    for _ in range(n): v.append(auroc([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg]))
    v.sort(); return v[int(.025 * n)], v[int(.975 * n)]

def fit(good, bad, sig):
    pos, neg = [g[sig] for g in good], [b[sig] for b in bad]
    best = (-9, 0)
    for t in sorted(set(pos + neg)):
        j = M.mean([float(p >= t) for p in pos]) - M.mean([float(x >= t) for x in neg])
        if j > best[0] or (j == best[0] and t > best[1]): best = (j, t)
    return {"J": best[1], "90": sorted(pos)[int(0.1 * len(pos))]}

taus = {}
for name, dev, new in a.pair:
    g, b = split_gb(rows_of(dev))
    print(f"[{name}] dev answers: {len(g)} good, {len(b)} bad")
    if len(b) >= 3:
        taus[name] = {s: fit(g, b, s) for s in ("lex", "sem")}
    elif a.fit_from:
        taus[name] = taus[a.fit_from]; print(f"   too few bad dev answers; using {a.fit_from}'s thresholds")
    else:
        raise SystemExit(f"{name}: need --fit-from")
    print("   thresholds:", {s: {k: round(v, 3) for k, v in t.items()} for s, t in taus[name].items()})
    print("   dev mean sem good/bad:", round(M.mean([x["sem"] for x in g]), 3), "/", round(M.mean([x["sem"] for x in b]), 3) if b else "-")

print("\n== Held-out (new questions): separation")
print("model".ljust(6), "signal".ljust(6), "good".ljust(5), "bad".ljust(4), "AUROC [95% CI]".ljust(22), "J: kept/refused".ljust(17), "90%: kept/refused")
for name, dev, new in a.pair:
    rows = rows_of(new); g, b = split_gb(rows)
    for sig in ("lex", "sem"):
        pos, neg = [x[sig] for x in g], [x[sig] for x in b]
        lo, hi = ci(pos, neg) if neg and pos else (float("nan"),) * 2
        cells = []
        for k in ("J", "90"):
            t = taus[name][sig][k]
            cells.append(f"{M.mean([float(p >= t) for p in pos]):.2f} / {M.mean([float(x < t) for x in neg]):.2f}" if neg and pos else "-")
        print(name.ljust(6), sig.ljust(6), str(len(g)).ljust(5), str(len(b)).ljust(4), f"{auroc(pos, neg):.3f} [{lo:.2f}, {hi:.2f}]".ljust(22), cells[0].ljust(17), cells[1])
    print(f"       mean sem good/bad: {M.mean([x['sem'] for x in g]):.3f} / {M.mean([x['sem'] for x in b]):.3f}" if b else "")

print("\n== Held-out (new questions): end to end, correct rate (thresholds fitted on dev)")
print("model/system".ljust(14), "n".ljust(4), "ungated".ljust(9), "lex(J)".ljust(9), "sem(J)".ljust(9), "lex(90)".ljust(9), "sem(90)", " | unanswerable refused: ungated -> sem(90)")
for name, dev, new in a.pair:
    rows = rows_of(new)
    for sysn in ("cag", "rag"):
        rs = [r for r in rows if r["system"] == sysn]
        res, un = {}, {}
        for key, (sig, k) in {"none": (None, None), "lex(J)": ("lex", "J"), "sem(J)": ("sem", "J"), "lex(90)": ("lex", "90"), "sem(90)": ("sem", "90")}.items():
            c, u = [], []
            for r in rs:
                rej = sig is not None and not r["_refused"] and feats(r["_final"])[sig] < taus[name][sig][k]
                refused = r["_refused"] or rej
                if r["kind"] == "unanswerable": c.append(float(refused)); u.append(float(refused))
                else: c.append(float(r.get("correct") == 1.0 and not rej))
            res[key], un[key] = M.mean(c), M.mean(u)
        print(f"{name+' '+sysn:<14}", str(len(rs)).ljust(4), *[f"{v:.3f}".ljust(9) for v in res.values()], f"| {un['none']:.2f} -> {un['sem(90)']:.2f}")
