"""FastAPI service. Readiness only after the cache is warm. Hardened for phase 7: API keys, per-client rate limit, bounded queue with timeouts, output URL guard.
    CAG_API_KEYS=alice:key1,bob:key2 PYTHONPATH=src uv run uvicorn cag.service:app_factory --factory
Set CAG_AUTH_DISABLED=1 for local use without keys. Corpus comes from CAG_DATASET (squad|helpdesk|docs). Also CAG_MODEL, CAG_NUM_CTX, CAG_BUDGET_RATIO,
CAG_PROMPT (cite|quote), CAG_MAX_TOKENS, CAG_ATTRIBUTION. Limits: CAG_RATE_PER_MIN, CAG_RATE_BURST, CAG_MAX_INFLIGHT, CAG_MAX_QUEUE, CAG_QUEUE_TIMEOUT_S,
CAG_REQUEST_TIMEOUT_S, CAG_URL_ALLOWLIST (comma-separated hosts, 'none' = no links). See hardening.py."""
import json, logging, math, os, threading, time
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from .corpus import build_corpus, check_budget
from .pii import redact, redact_docs
from .hardening import Admission, Overloaded, RateLimiter, Settings, authenticate, corpus_hosts, guard_urls
from .systems import CAG

log = logging.getLogger("cag.service")

class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

def prepare_docs(docs, cfg: Settings):
    """Scrub the corpus before it is cached: whatever is cached is visible to every caller."""
    if cfg.pii_corpus != "redact":
        return docs
    docs, found = redact_docs(docs)
    log.info(json.dumps({"event": "corpus_pii", "redacted": found}))
    return docs

def create_app(cag: CAG | None = None, settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    state = {"cag": cag, "ready": False, "recovering": False}
    state_lock = threading.Lock()
    limiter = RateLimiter(cfg.rate_per_min, cfg.rate_burst)
    admission = Admission(cfg.max_inflight, cfg.max_queue, cfg.queue_timeout_s)

    @asynccontextmanager
    async def lifespan(app):
        if state["cag"] is None:
            from dotenv import load_dotenv; load_dotenv()
            from .llm import OllamaLLM
            ds_name = os.getenv("CAG_DATASET", "squad")
            if ds_name == "helpdesk":
                from .adapters.helpdesk import load_docs; docs = load_docs()[:int(os.getenv("CAG_MAX_DOCS", "200"))]
            elif ds_name == "docs":
                from .adapters.docs_qa import load_docs; docs = load_docs()
            else:
                from .adapters.squad import build; docs = build().docs
            docs = prepare_docs(docs, cfg)
            corpus = build_corpus(docs)
            check_budget(corpus, int(os.getenv("CAG_NUM_CTX", "32768")), float(os.getenv("CAG_BUDGET_RATIO", "0.7")))
            from .attribution import Attributor, SemanticAttributor
            attr = SemanticAttributor(docs) if os.getenv("CAG_ATTRIBUTION", "bm25") == "hybrid" else Attributor(docs)
            llm = OllamaLLM(max_tokens=int(os.getenv("CAG_MAX_TOKENS", "300")))
            state["cag"] = CAG(corpus, llm, os.getenv("CAG_PROMPT", "cite"), attributor=attr)
        # Links the model may emit. Default = hosts found in the served corpus; this is weaker than an explicit CAG_URL_ALLOWLIST,
        # because a poisoned chunk would allowlist its own link.
        state["allowed"] = cfg.url_allowlist if cfg.url_allowlist is not None else corpus_hosts([state["cag"].corpus.text])
        stop = state["stop"] = threading.Event()
        llm = state["cag"].llm
        def warm_up():
            set_timeout = getattr(llm, "set_timeout", None)
            if set_timeout: set_timeout(None)                         # no request timeout here: a cold 32B prefill takes ~8 minutes
            state["cag"].warm()
            if set_timeout: set_timeout(cfg.request_timeout_s)        # from now on a stuck model call fails instead of holding the slot
        def recover():              # backend was lost: wait for it, re-prefill the corpus (the KV cache died with it), then serve again
            while not stop.is_set():
                stop.wait(cfg.recover_interval_s)
                if getattr(llm, "ping", lambda: True)():
                    try:
                        warm_up(); state["error"] = None; state["ready"] = True; state["recovering"] = False
                        log.info(json.dumps({"event": "recovered"})); return
                    except Exception as e:  # noqa: still down or died again while warming: keep trying
                        state["error"] = f"recovering: {type(e).__name__}"
        def mark_down(reason: str):
            with state_lock:
                if state["recovering"]: return
                state["ready"], state["recovering"], state["error"] = False, True, f"model backend unavailable ({reason}); recovering"
            log.warning(json.dumps({"event": "backend_down", "reason": reason}))
            threading.Thread(target=recover, daemon=True).start()
        state["mark_down"] = mark_down
        def warm():                 # background: a blocking warm-up makes /healthz unreachable for minutes (a liveness probe would kill the pod)
            try:
                warm_up(); state["ready"] = True
            except Exception as e:  # noqa: surfaced via /readyz
                state["error"] = f"{type(e).__name__}: {e}"
        def monitor():              # notice an outage even when nobody is calling
            while not stop.wait(cfg.health_interval_s):
                if state["ready"] and not getattr(llm, "ping", lambda: True)():
                    mark_down("health check failed")
        threading.Thread(target=warm, daemon=True).start()
        threading.Thread(target=monitor, daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title="CAG", lifespan=lifespan)

    def client_of(request: Request, x_api_key: str | None = Header(None), authorization: str | None = Header(None)) -> str:
        name = authenticate(cfg, x_api_key, authorization)
        if name is None:
            raise HTTPException(401, "invalid or missing API key", headers={"WWW-Authenticate": "Bearer"})
        # with auth off every caller is "anonymous", so rate limit by network address instead
        return name if not cfg.auth_disabled else (request.client.host if request.client else "unknown")

    @app.get("/healthz")
    def healthz(): return {"ok": True}

    @app.get("/readyz")
    def readyz():
        if not state["ready"]: raise HTTPException(503, state.get("error") or "cache not warm")
        return {"ready": True}

    @app.get("/corpus")
    def corpus(client: str = Depends(client_of)): return state["cag"].corpus.manifest()

    @app.post("/ask")
    def ask(body: Ask, client: str = Depends(client_of)):
        t0 = time.time()
        def done(status: int, **extra):
            log.info(json.dumps({"event": "ask", "client": client, "status": status, "s": round(time.time() - t0, 2), **extra}))
        if not state["ready"]:
            done(503, reason="warming"); raise HTTPException(503, state.get("error") or "cache not warm", headers={"Retry-After": "30"})
        ok, wait = limiter.allow(client)
        if not ok:
            done(429); raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(max(1, math.ceil(wait)))})
        try:
            with admission:
                queued = time.time() - t0
                r = state["cag"].answer(body.question)
        except Overloaded as o:
            done(503, reason=o.reason); raise HTTPException(503, f"overloaded: {o.reason}", headers={"Retry-After": str(o.retry_after)})
        except Exception as e:
            name = type(e).__name__
            llm = state["cag"].llm
            alive = getattr(llm, "ping", lambda: True)()
            if not alive:
                state["mark_down"](name)                          # readiness flips to 503 and the service re-warms once the backend is back
            if alive and ("Timeout" in name or isinstance(e, TimeoutError)):
                done(504, reason="model timeout"); raise HTTPException(504, "the model took too long to answer")
            log.warning(json.dumps({"event": "backend_error", "type": name, "backend_alive": alive}))
            done(502, reason=name); raise HTTPException(502, "model backend error")
        text, removed = guard_urls(r.answer, state["allowed"])
        pii = {}
        if cfg.pii_output:
            text, pii = redact(text)
        u = r.usage
        done(200, queue_s=round(queued, 2), hit_ratio=round(u.hit_ratio, 3), urls_removed=len(removed), pii_redacted=sum(pii.values()))
        return {"answer": text, "cited": sorted(r.cited), "sources": r.sources, "support": round(r.support, 3),
                "guards": {"urls_removed": removed, "pii_redacted": pii},
                "usage": {"uncached_in": u.input, "cache_write": u.cache_write, "cache_read": u.cache_read,
                          "out": u.output, "hit_ratio": u.hit_ratio}, "latency_s": r.latency_s}
    return app

def app_factory():
    logging.basicConfig(level=logging.INFO, format="%(message)s")      # structured request lines go to stdout/stderr
    return create_app()
