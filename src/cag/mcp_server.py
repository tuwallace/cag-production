"""CAG as an MCP tool for ollmcp. Runs over stdio: NOTHING may be printed to stdout except protocol messages.
The server owns the cached corpus and its own Ollama model; the chat model in ollmcp just decides when to ask.
Use a DIFFERENT model name for ollmcp (e.g. qwen3:8b-16k) than CAG_MODEL, or Ollama will reload the model with
a different num_ctx on every hop and throw the KV cache away."""
import os, threading
from dotenv import load_dotenv
from fastmcp import FastMCP
from .corpus import build_corpus, check_budget

load_dotenv()
mcp = FastMCP("cag")
_state: dict = {}
_lock = threading.Lock()

def _cag():
    with _lock:                                    # one request at a time: a single Ollama slot keeps the cache hot
        if "cag" not in _state:
            from .llm import OllamaLLM
            from .systems import CAG
            if os.getenv("CAG_DATASET", "helpdesk") == "helpdesk":
                from .adapters.helpdesk import load_docs
                docs = load_docs()[:int(os.getenv("CAG_MAX_DOCS", "200"))]
            else:
                from .adapters.squad import build
                docs = build().docs
            corpus = build_corpus(docs)
            check_budget(corpus, int(os.getenv("CAG_NUM_CTX", "32768")), 0.7)
            _state["cag"] = CAG(corpus, OllamaLLM())
            _state["cag"].warm()
        return _state["cag"]

threading.Thread(target=lambda: _cag(), daemon=True).start()     # prefill at startup so the first question is fast

@mcp.tool()
def ask_knowledge_base(question: str) -> dict:
    """Answer a question from the full, pre-loaded knowledge base (IT help-desk tickets by default).
    Use for any employee IT problem or ticket-history question. Do not use for greetings or general knowledge.
    Returns the grounded answer, the ticket ids it cites, and cache statistics."""
    cag = _cag()
    with _lock:
        r = cag.answer(question)
    u = r.usage
    return {"answer": r.answer, "cited_ids": sorted(r.cited),
            "cache": {"tokens_prefilled": u.input, "tokens_reused": u.cache_read, "prefill_s": round(u.prefill_s, 2)}}

@mcp.tool()
def knowledge_base_info() -> dict:
    """Describe the loaded knowledge base: version hash, document count, approximate token size."""
    return _cag().corpus.manifest()

if __name__ == "__main__":
    mcp.run(show_banner=False)
