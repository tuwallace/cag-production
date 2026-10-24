"""Analyse a shadow run and apply the promotion criteria.
    PYTHONPATH=src uv run python scripts/shadow_report.py reports/shadow-8b.jsonl
    PYTHONPATH=src uv run python scripts/shadow_report.py --from-answers <cag>.answers.jsonl [...] --rag <rag>.answers.jsonl [...]   # offline: pair saved CAG and RAG answers
Candidate = CAG, primary = RAG (the incumbent). Records carry the eval labels in `meta`, so the labelled view can check the unlabelled proxies
(agreement, unsafe disagreements) that a real deployment would have to rely on."""
import argparse, json, statistics as st, sys
from cag import metrics as M
from cag.adapters.docs_qa import build
from cag.systems import parse_answer

def from_answers(cag_paths, rag_paths):
    ex = {e.question: e for e in build(hybrid=False, split="all").examples}
    rows = lambda ps, s: {r["question"]: r for p in ps for r in map(json.loads, open(p)) if r["system"] == s}
    cag, rag = rows(cag_paths, "cag"), rows(rag_paths, "rag")
    out = []
    for q in cag.keys() & rag.keys():
        e = ex[q]; p, c = rag[q], cag[q]
        pf, cf = parse_answer(p["answer"]), parse_answer(c["answer"])
        from cag.shadow import jaccard, _tokens
        pr, cr = M.is_refusal(pf), M.is_refusal(cf)
        out.append({"question": q, "meta": {"kind": e.kind, "any": e.answers, "all": e.all_of},
                    "primary": {"answer": p["answer"], "refused": pr, "latency_s": p["latency_s"]}, "candidate": {"answer": c["answer"], "refused": cr, "latency_s": c["latency_s"]},
                    "agree_refusal": pr == cr, "answer_overlap": None if (pr or cr) else jaccard(_tokens(pf), _tokens(cf))})
    return out

def correct(side, meta):
    final = parse_answer(side["answer"])
    if meta["kind"] == "unanswerable": return side["refused"]
    return (not side["refused"]) and M.answer_correct(final, meta.get("any", []), meta.get("all", []))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("records", nargs="?"); ap.add_argument("--from-answers", nargs="*"); ap.add_argument("--rag", nargs="*")
    a = ap.parse_args()
    recs = from_answers(a.from_answers, a.rag) if a.from_answers else [json.loads(l) for l in open(a.records)]
    done = [r for r in recs if "error" not in r["candidate"]]; errors = len(recs) - len(done)
    print(f"records {len(recs)}  compared {len(done)}  candidate errors {errors}")
    pl, cl = [r["primary"]["latency_s"] for r in done], [r["candidate"]["latency_s"] for r in done]
    print(f"latency  primary(RAG) p50 {M.pct(pl, .5):.1f}s p95 {M.pct(pl, .95):.1f}s | candidate(CAG, off the request path) p50 {M.pct(cl, .5):.1f}s p95 {M.pct(cl, .95):.1f}s")
    agree = M.mean([float(r["agree_refusal"]) for r in done]); ov = [r["answer_overlap"] for r in done if r.get("answer_overlap") is not None]
    print(f"refusal agreement {agree:.2f}   answer word overlap (both answered): median {st.median(ov) if ov else float('nan'):.2f}   n={len(ov)}")
    unsafe = [r for r in done if r["primary"]["refused"] and not r["candidate"]["refused"]]; missed = [r for r in done if r["candidate"]["refused"] and not r["primary"]["refused"]]
    print(f"disagreements: candidate answered where primary refused {len(unsafe)} ({len(unsafe)/len(done):.0%})   candidate refused where primary answered {len(missed)} ({len(missed)/len(done):.0%})")
    lab = [r for r in done if r.get("meta", {}).get("kind")]
    verdict = {}
    if lab:
        pc, cc = [correct(r["primary"], r["meta"]) for r in lab], [correct(r["candidate"], r["meta"]) for r in lab]
        both, onlyp, onlyc, neither = (sum(p and c for p, c in zip(pc, cc)), sum(p and not c for p, c in zip(pc, cc)), sum(c and not p for p, c in zip(pc, cc)), sum(not p and not c for p, c in zip(pc, cc)))
        print(f"\nlabelled ({len(lab)}): primary correct {sum(pc)/len(lab):.3f}  candidate correct {sum(cc)/len(lab):.3f}   both {both}  only-primary {onlyp}  only-candidate {onlyc}  neither {neither}")
        for kind in ("answerable", "unanswerable"):
            sel = [(p, c) for p, c, r in zip(pc, cc, lab) if (r["meta"]["kind"] == "unanswerable") == (kind == "unanswerable")]
            print(f"  {kind:<13} n={len(sel):<3} primary {M.mean([float(p) for p, _ in sel]):.3f}  candidate {M.mean([float(c) for _, c in sel]):.3f}")
        fab_u = [r for r in unsafe if r["meta"]["kind"] == "unanswerable"]
        print(f"  of the {len(unsafe)} 'candidate answered, primary refused': {len(fab_u)} were unanswerable questions (fabrications), {len(unsafe)-len(fab_u)} were answerable (primary missed it)")
        un = [(p, c) for p, c, r in zip(pc, cc, lab) if r["meta"]["kind"] == "unanswerable"]
        verdict = {"C2 fabrication regression <= 5 points": (M.mean([float(p) for p, _ in un]) - M.mean([float(c) for _, c in un]) <= 0.05 + 1e-9) if un else None,
                   "C3 candidate correct >= primary - 0.05": M.mean([float(c) for c in cc]) >= M.mean([float(p) for p in pc]) - 0.05 - 1e-9}
    verdict = {"C1 candidate errors <= 1%": errors / len(recs) <= 0.01, **verdict, "C4 (info) candidate p50 <= primary p50": M.pct(cl, .5) <= M.pct(pl, .5)}
    print("\npromotion criteria:")
    for k, v in verdict.items(): print(f"  {'PASS' if v else 'FAIL' if v is not None else 'n/a '}  {k}")
    hard = [v for k, v in verdict.items() if not k.startswith("C4") and v is not None]
    print("VERDICT:", "promote CAG" if all(hard) else "HOLD: do not promote")
    return 0 if all(hard) else 1

if __name__ == "__main__":
    sys.exit(main())
