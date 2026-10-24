"""Segment 4 on-screen demo: does the cache work? LIVE: needs Ollama on CAG_OLLAMA_HOST (default :11435) and the model pulled.
Unloads the model, then asks four questions about the Ollama docs and prints, for each call, how much of the prompt was read from the cache.
    CAG_OLLAMA_HOST=http://127.0.0.1:11435 PYTHONPATH=src python docs/video/demo/seg4_cache.py   (about 3 minutes for qwen3:8b; the first call is the slow one)"""
import os, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[3]; sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
from cag.adapters.docs_qa import load_docs
from cag.corpus import build_corpus
from cag.llm import OllamaLLM
from cag.systems import CAG

MODEL, CTX = os.getenv("CAG_MODEL", "qwen3:8b"), int(os.getenv("CAG_NUM_CTX", "40960"))
QUESTIONS = ["Which environment variable changes the directory where Ollama stores models?",
             "What is the default value of OLLAMA_MAX_QUEUE?",
             "How do I keep a model loaded in memory indefinitely when calling the API?"]
corpus = build_corpus(load_docs()); llm = OllamaLLM(MODEL, num_ctx=CTX, max_tokens=150); cag = CAG(corpus, llm, "cite")
print(f"\n  CAG on the Ollama docs: {corpus.n_docs} sections, model {MODEL}\n")
llm.client.generate(model=MODEL, keep_alive=0); time.sleep(3)                      # start cold: unload the model and its cache
rows = []
def call(label, fn):
    t = time.time(); r = fn(); total = time.time() - t; u = r.usage
    rows.append((label, u.input + u.cache_read, u.cache_read, u.prefill_s, total, u.hit_ratio))
    print(f"  {label:<34}{rows[-1][1]:>14,}{rows[-1][2]:>12,}{u.prefill_s:>12.1f} s{total:>7.1f} s", flush=True)
print(f"  {'call':<34}{'prompt tokens':>14}{'from cache':>12}{'read prompt':>14}{'total':>10}")
call("first call (cold: reads it all)", cag.warm)
for i, q in enumerate(QUESTIONS, 1): call(f"question {i}", lambda q=q: cag.answer(q))
warm = [r for r in rows[1:]]
print(f"\n  after the first call: {sum(r[2] for r in warm) / sum(r[1] for r in warm):.1%} of every prompt comes from the cache\n")
