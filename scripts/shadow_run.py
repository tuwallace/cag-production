"""Live shadow run: RAG is the incumbent that answers; CAG shadows it on the same questions in the background; every comparison is logged.
Two separate Ollama servers keep the CAG prefix cache from being overwritten by RAG's changing prompts (one server has ONE cache slot).
    PYTHONPATH=src uv run python scripts/shadow_run.py --model qwen3:8b --rag-host http://127.0.0.1:11434 --cag-host http://127.0.0.1:11435 --out reports/shadow-8b.jsonl"""
import argparse, random, time
from dotenv import load_dotenv
from cag.adapters.docs_qa import build
from cag.corpus import build_corpus, check_budget
from cag.llm import OllamaLLM
from cag.shadow import ShadowRunner, jsonl_sink
from cag.systems import CAG, RAG

def main():
    load_dotenv()
    ap = argparse.ArgumentParser(); ap.add_argument("--model", required=True)
    ap.add_argument("--rag-host", required=True); ap.add_argument("--cag-host", required=True)
    ap.add_argument("--cag-window", type=int, default=40960); ap.add_argument("--rag-window", type=int, default=8192); ap.add_argument("--ratio", type=float, default=0.7)
    ap.add_argument("--prompt", default="quote"); ap.add_argument("--n", type=int, default=90); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--interval", type=float, default=0, help="seconds between requests (0 = back to back); pace it so the candidate can keep up")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ds = build(split="all"); corpus = build_corpus(ds.docs); check_budget(corpus, a.cag_window, a.ratio)
    primary = RAG(ds.retriever, OllamaLLM(a.model, num_ctx=a.rag_window, host=a.rag_host, max_tokens=450), corpus.ids, 5, a.prompt)
    candidate = CAG(corpus, OllamaLLM(a.model, num_ctx=a.cag_window, host=a.cag_host, max_tokens=450), a.prompt)
    t = time.time(); candidate.warm(); print(f"candidate warmed in {time.time() - t:.0f}s", flush=True)
    shadow = ShadowRunner(primary, candidate, jsonl_sink(a.out), store_text="full")        # "full": these are eval questions, not user data
    qs = list(ds.examples); random.Random(a.seed).shuffle(qs)
    for i, e in enumerate(qs[: a.n]):
        t_req = time.time()
        shadow.answer(e.question, meta={"kind": e.kind, "gold": sorted(e.gold_ids), "any": e.answers, "all": e.all_of})
        time.sleep(max(0.0, a.interval - (time.time() - t_req)))
        if i % 10 == 9: print(i + 1, "served;", shadow.counts, flush=True)
    shadow.close(wait=True); print("final", shadow.counts)

if __name__ == "__main__":
    main()
