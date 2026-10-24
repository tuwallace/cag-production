"""Run CAG and RAG on the same questions with the same model; write a comparison report.
    PYTHONPATH=src uv run python -m cag.evaluate --dataset squad --articles 3 --n 50
    PYTHONPATH=src uv run python -m cag.evaluate --dataset helpdesk --n 26
"""
import argparse, json, os, time, pathlib
from dotenv import load_dotenv
from .corpus import build_corpus, check_budget
from .systems import CAG, RAG, ClosedBook, Result, NO_ANSWER, parse_answer, parse_quotes, verify_quotes
from . import metrics as M

def score(system_name, example, res, doc_text=None) -> dict:
    final = parse_answer(res.answer)
    row = {"system": system_name, "latency_s": res.latency_s, "uncached_in": res.usage.input, "prefill_s": res.usage.prefill_s,
           "cache_write": res.usage.cache_write, "cache_read": res.usage.cache_read, "out": res.usage.output,
           "cite_hit": float(bool(res.cited & example.gold_ids)),
           "cite_precision": len(res.cited & example.gold_ids) / len(res.cited) if res.cited else 0.0,
           "no_answer": float(M.is_refusal(final)), "kind": example.kind}
    quotes = parse_quotes(res.answer)
    if doc_text is not None and system_name != "closed_book":
        row["has_quote"] = float(bool(quotes))
        if quotes:
            row["quote_grounded"] = M.mean([float(i in doc_text and M.normalize(q) in M.normalize(doc_text[i])) for q, i in quotes])
    if example.kind == "unanswerable":
        row["correct"] = row["no_answer"]                  # right behaviour is to refuse
    elif example.answers or example.all_of:
        row["correct"] = float(M.answer_correct(final, example.answers, example.all_of))
    if system_name.startswith("rag"):
        row["retrieval_hit"] = float(bool(set(res.retrieved) & example.gold_ids))
    if example.answers and not example.all_of:
        row["contains"] = float(M.contains_answer(final, example.answers))
        row["f1"] = M.best_f1(final, example.answers)
    return row

def summarize(rows: list[dict]) -> dict:
    keys = ["correct", "rejected", "has_quote", "quote_grounded", "cite_hit", "cite_precision", "no_answer", "retrieval_hit", "contains", "f1"]
    out = {k: M.mean([r[k] for r in rows if k in r]) for k in keys if any(k in r for r in rows)}
    for kind in ("single", "multi", "conflict", "unanswerable"):
        ks = [r["correct"] for r in rows if r.get("kind") == kind and "correct" in r]
        if ks:
            out[f"acc_{kind}"] = M.mean(ks)
    answerable = [r for r in rows if r.get("kind") != "unanswerable" and "correct" in r]
    if answerable:
        out["false_refusal"] = M.mean([r["no_answer"] for r in answerable])
    lat = [r["latency_s"] for r in rows]
    tot = lambda k: sum(r[k] for r in rows)
    all_in = tot("uncached_in") + tot("cache_write") + tot("cache_read")
    out.update(n=len(rows), p50_s=M.pct(lat, .5), p95_s=M.pct(lat, .95),
               mean_uncached_in=tot("uncached_in") / len(rows), mean_prefill_s=tot("prefill_s") / len(rows), mean_cache_read=tot("cache_read") / len(rows),
               total_cache_write=tot("cache_write"), cache_hit_ratio=tot("cache_read") / all_in if all_in else 0.0,
               mean_out=tot("out") / len(rows))
    return out

def _usage_of(a):
    from .llm import Usage
    return Usage(a['uncached_in'], a['cache_write'], a['cache_read'], a['out'], a['prefill_s'])

def run(ds, llm, systems=("cag", "rag", "closed_book"), k=5, window=32_768, ratio=0.7, style="cite", verify=False) -> dict:
    if verify and style != "quote":
        raise ValueError("--verify needs --prompt quote")
    corpus = build_corpus(ds.docs)
    check_budget(corpus, window, ratio)
    doc_text = {d.id: d.text for d in ds.docs}
    built = {"cag": lambda: CAG(corpus, llm, style), "rag": lambda: RAG(ds.retriever, llm, corpus.ids, k, style),
             "closed_book": lambda: ClosedBook(llm)}
    report = {"dataset": ds.name, "corpus": corpus.manifest(), "model": getattr(llm, "model", "?"), "k": k, "prompt": style,
              "systems": {}, "_answers": []}
    for name in systems:
        sysm, rows = built[name](), []
        if name == "cag":
            sysm.warm()                                   # priming write; excluded from rows so steady state is measured
        for ex in ds.examples:
            res = sysm.answer(ex.question)
            row = score(name, ex, res, doc_text)
            rows.append(row)
            report["_answers"].append({"system": name, "kind": ex.kind, "question": ex.question, "gold": sorted(ex.gold_ids),
                                       "answer": res.answer, "cited": sorted(res.cited), "retrieved": res.retrieved, **row})
        report["systems"][name] = summarize(rows)
        if verify and name in ("cag", "rag"):
            # Same generations, gated: rejected answers become a refusal. Paired comparison with the ungated rows above.
            vrows = []
            for a, ex in zip([x for x in report["_answers"] if x["system"] == name], ds.examples):
                ok, reason = verify_quotes(a["answer"], doc_text)
                res = Result(a["answer"] if ok else NO_ANSWER, set(a["cited"]) if ok else set(), _usage_of(a), a["latency_s"], a["retrieved"])
                row = score(name + "+verify", ex, res, None)
                row["rejected"] = float(not ok)
                vrows.append(row)
                report["_answers"].append({"system": name + "+verify", "kind": ex.kind, "question": ex.question, "gold": sorted(ex.gold_ids),
                                           "answer": res.answer, "raw_answer": a["answer"], "verify": reason, "cited": sorted(res.cited),
                                           "retrieved": a["retrieved"], **row})
            report["systems"][name + "+verify"] = summarize(vrows)
    return report

def to_markdown(rep: dict) -> str:
    cols = [c for c in ["n", "correct", "rejected", "has_quote", "quote_grounded", "acc_single", "acc_multi", "acc_conflict", "acc_unanswerable", "false_refusal", "cite_hit", "cite_precision", "retrieval_hit", "contains", "f1", "no_answer",
                        "p50_s", "p95_s", "mean_prefill_s", "mean_uncached_in", "mean_cache_read", "cache_hit_ratio", "mean_out"]
            if any(c in s for s in rep["systems"].values())]
    f = lambda v: f"{v:.3f}" if isinstance(v, float) else str(v)
    lines = [f"# {rep['dataset']}  (model {rep['model']}, prompt {rep.get('prompt', 'cite')}, corpus ~{rep['corpus']['est_tokens']} tok, {rep['corpus']['n_docs']} docs, rag k={rep['k']})",
             "", "| system | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for name, s in rep["systems"].items():
        lines.append(f"| {name} | " + " | ".join(f(s.get(c, "-")) for c in cols) + " |")
    return "\n".join(lines) + "\n"

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["squad", "helpdesk", "docs"], default="squad")
    ap.add_argument("--split", choices=["dev", "new", "all"], default="dev", help="docs dataset only: original 40 questions, the 50 held-out ones, or both")
    ap.add_argument("--articles", type=int, default=3)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--model")
    ap.add_argument("--prompt", choices=["cite", "quote"], default="cite", help="answer format given to CAG and RAG")
    ap.add_argument("--systems", default="cag,rag", help="comma list from: cag, rag, closed_book")
    ap.add_argument("--verify", action="store_true", help="quote prompt only: also score a verbatim-quote-gated copy of cag and rag (+verify rows)")
    ap.add_argument("--max-tokens", type=int, default=300)
    ap.add_argument("--window", type=int, default=int(os.getenv("CAG_NUM_CTX", "32768")), help="Ollama num_ctx (must match CAG_NUM_CTX)")
    ap.add_argument("--ratio", type=float, default=0.7, help="max fraction of the window the corpus may use")
    ap.add_argument("--max-docs", type=int, default=200, help="helpdesk only: use the first N tickets so the corpus fits num_ctx")
    ap.add_argument("--baseline", choices=["helpdesk-rag", "bm25"], default="helpdesk-rag",
                    help="helpdesk dataset only: which retriever feeds RAG")
    a = ap.parse_args()
    from .llm import OllamaLLM
    if a.dataset == "docs":
        from .adapters.docs_qa import build
        ds = build(a.n, split=a.split)
    elif a.dataset == "squad":
        from .adapters.squad import build
        ds = build(a.articles, a.n)
    else:
        from .adapters.helpdesk import build
        ds = build(a.n, a.baseline, a.max_docs)
    rep = run(ds, OllamaLLM(a.model, num_ctx=a.window, max_tokens=a.max_tokens), systems=tuple(a.systems.split(",")),
              k=a.k, window=a.window, ratio=a.ratio, style=a.prompt, verify=a.verify)
    out = pathlib.Path(__file__).resolve().parents[2] / "reports"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    answers = rep.pop("_answers")
    (out / f"{ds.name}-{stamp}.answers.jsonl").write_text("\n".join(json.dumps(x) for x in answers) + "\n")
    (out / f"{ds.name}-{stamp}.json").write_text(json.dumps(rep, indent=2))
    md = to_markdown(rep); (out / f"{ds.name}-{stamp}.md").write_text(md); print(md)

if __name__ == "__main__":
    main()
