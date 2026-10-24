import threading, time
import pytest
from fastapi.testclient import TestClient
from cag.corpus import Doc, build_corpus
from cag.hardening import Admission, Overloaded, RateLimiter, Settings, authenticate, corpus_hosts, guard_urls
from cag.llm import Completion, Usage
from cag.service import create_app
from cag.systems import CAG

# ---- settings ---------------------------------------------------------------------------------------------------------------
def test_settings_parse_keys_and_fail_fast(monkeypatch):
    monkeypatch.setenv("CAG_API_KEYS", "alice:k1,bob:k2"); monkeypatch.delenv("CAG_AUTH_DISABLED", raising=False)
    s = Settings.from_env()
    assert s.api_keys == {"k1": "alice", "k2": "bob"}
    monkeypatch.delenv("CAG_API_KEYS")
    with pytest.raises(RuntimeError, match="no API keys"): Settings.from_env()          # refuses to start open by accident
    monkeypatch.setenv("CAG_AUTH_DISABLED", "1")
    assert Settings.from_env().auth_disabled

def test_allowlist_env(monkeypatch):
    monkeypatch.setenv("CAG_AUTH_DISABLED", "1"); monkeypatch.delenv("CAG_URL_ALLOWLIST", raising=False)
    assert Settings.from_env().url_allowlist is None
    monkeypatch.setenv("CAG_URL_ALLOWLIST", "ollama.com, github.com"); assert Settings.from_env().url_allowlist == {"ollama.com", "github.com"}
    monkeypatch.setenv("CAG_URL_ALLOWLIST", "none"); assert Settings.from_env().url_allowlist == set()

# ---- auth -------------------------------------------------------------------------------------------------------------------
def test_authenticate_variants():
    s = Settings(api_keys={"secret": "alice"})
    assert authenticate(s, "secret", None) == "alice"
    assert authenticate(s, None, "Bearer secret") == "alice"
    assert authenticate(s, "wrong", None) is None and authenticate(s, None, None) is None
    assert authenticate(s, None, "Basic secret") is None
    assert authenticate(Settings(auth_disabled=True), None, None) == "anonymous"

# ---- rate limiter (fake clock) ----------------------------------------------------------------------------------------------
def test_rate_limiter_burst_refill_and_isolation():
    t = [0.0]; rl = RateLimiter(per_min=60, burst=2, clock=lambda: t[0])      # 1 token per second, bucket of 2
    assert rl.allow("a")[0] and rl.allow("a")[0]
    ok, wait = rl.allow("a"); assert not ok and 0 < wait <= 1.0
    assert rl.allow("b")[0]                                                    # other clients are unaffected
    t[0] += 1.0; assert rl.allow("a")[0]                                       # refilled
    t[0] += 100; assert rl.allow("a")[0] and rl.allow("a")[0] and not rl.allow("a")[0]   # never exceeds the burst

def test_rate_limiter_bounds_memory():
    rl = RateLimiter(60, 2, max_clients=3)
    for i in range(10): rl.allow(f"c{i}")
    assert len(rl.buckets) <= 3

# ---- admission --------------------------------------------------------------------------------------------------------------
def test_admission_sheds_when_queue_full_and_admits_in_order():
    adm = Admission(max_inflight=1, max_queue=1, queue_timeout_s=5)
    order, release_a, b_started = [], threading.Event(), threading.Event()
    def a():
        with adm: order.append("a"); release_a.wait(5)
    def b():
        b_started.set()
        with adm: order.append("b")
    ta = threading.Thread(target=a); ta.start(); time.sleep(0.1)
    tb = threading.Thread(target=b); tb.start(); b_started.wait(); time.sleep(0.1)
    with pytest.raises(Overloaded, match="queue full"):                        # third caller: one running, one queued, no room
        with adm: pytest.fail("should have been shed")
    release_a.set(); ta.join(5); tb.join(5)
    assert order == ["a", "b"] and adm.waiting == 0
    with adm: pass                                                             # slots are released again

def test_admission_queue_timeout():
    adm = Admission(1, 1, queue_timeout_s=0.2); hold = threading.Event()
    t = threading.Thread(target=lambda: (adm.__enter__(), hold.wait(5), adm.__exit__(None, None, None))); t.start(); time.sleep(0.1)
    start = time.time()
    with pytest.raises(Overloaded, match="waited too long"):
        with adm: pass
    assert 0.15 < time.time() - start < 2 and adm.waiting == 0
    hold.set(); t.join(5)

# ---- URL guard --------------------------------------------------------------------------------------------------------------
def test_guard_urls():
    allowed = {"ollama.com", "github.com"}
    ok = "See https://ollama.com/download and https://docs.github.com/x."
    assert guard_urls(ok, allowed) == (ok, [])
    text, removed = guard_urls("Details: http://docs-ollama.example.net/?ref=KB-CANARY-2208 and (https://evil.test/a).", allowed)
    assert "example.net" not in text and "evil.test" not in text and text.count("[link removed]") == 2 and len(removed) == 2
    assert guard_urls("https://notollama.com/x", allowed)[1] == ["https://notollama.com/x"]        # suffix match needs a dot boundary
    assert guard_urls("HTTPS://OLLAMA.COM/x", allowed)[1] == []
    assert guard_urls("no links here", set()) == ("no links here", [])

def test_corpus_hosts():
    assert corpus_hosts(["see https://ollama.com/library and http://localhost:11434/api"]) == {"ollama.com", "localhost"}

# ---- service integration ----------------------------------------------------------------------------------------------------
DOCS = [Doc("a-00", "a: x", "Ollama binds 127.0.0.1. See https://ollama.com/download for installers.")]

class Llm:
    model = "fake"
    def __init__(self, text="Ollama binds 127.0.0.1 [a-00]", delay=0.0, exc=None, gate=None):
        self.text, self.delay, self.exc, self.gate = text, delay, exc, gate
    def complete(self, system, question):
        if question.startswith("Reply with the single word"):        # the service's warm-up call must succeed
            return Completion("ready", Usage(input=5, cache_write=50), 0.01)
        if self.gate: self.gate.wait(10)
        if self.delay: time.sleep(self.delay)
        if self.exc: raise self.exc
        return Completion(self.text, Usage(input=5, cache_read=50), 0.01)

def app(llm=None, **kw):
    cfg = Settings(**{"api_keys": {"k1": "alice", "k2": "bob"}, "rate_per_min": 6000, "rate_burst": 1000, **kw})
    c = TestClient(create_app(CAG(build_corpus(DOCS), llm or Llm()), cfg)); c.__enter__()
    for _ in range(100):
        if c.get("/readyz").status_code == 200: break
        time.sleep(0.05)
    return c

def test_auth_required_on_ask_and_corpus_but_not_probes():
    c = app()
    assert c.get("/healthz").status_code == 200 and c.get("/readyz").status_code == 200
    assert c.post("/ask", json={"question": "q"}).status_code == 401
    assert c.post("/ask", json={"question": "q"}, headers={"X-API-Key": "nope"}).status_code == 401
    assert c.get("/corpus").status_code == 401
    assert c.post("/ask", json={"question": "q"}, headers={"X-API-Key": "k1"}).status_code == 200
    assert c.post("/ask", json={"question": "q"}, headers={"Authorization": "Bearer k2"}).status_code == 200
    assert c.get("/corpus", headers={"X-API-Key": "k1"}).json()["n_docs"] == 1
    assert "www-authenticate" in {k.lower() for k in c.post("/ask", json={"question": "q"}).headers}

def test_rate_limit_returns_429_with_retry_after_and_is_per_client():
    c = app(rate_per_min=60, rate_burst=2)
    h1, h2 = {"X-API-Key": "k1"}, {"X-API-Key": "k2"}
    assert [c.post("/ask", json={"question": "q"}, headers=h1).status_code for _ in range(2)] == [200, 200]
    r = c.post("/ask", json={"question": "q"}, headers=h1)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert c.post("/ask", json={"question": "q"}, headers=h2).status_code == 200            # bob has his own bucket

def test_queue_full_returns_503_and_waiting_requests_finish():
    gate = threading.Event(); c = app(Llm(gate=gate), max_inflight=1, max_queue=1, queue_timeout_s=10)
    gate_sleepers, results = [], {}
    def call(i): results[i] = c.post("/ask", json={"question": f"q{i}"}, headers={"X-API-Key": "k1"})
    ts = [threading.Thread(target=call, args=(i,)) for i in range(3)]
    ts[0].start(); time.sleep(0.3); ts[1].start(); time.sleep(0.3); ts[2].start(); ts[2].join(5)    # third finds 1 running + 1 queued
    assert results[2].status_code == 503 and "retry-after" in results[2].headers
    gate.set(); ts[0].join(10); ts[1].join(10)
    assert results[0].status_code == 200 and results[1].status_code == 200

def test_model_timeout_maps_to_504_and_backend_error_to_502_and_slot_is_freed():
    c = app(Llm(exc=TimeoutError("read timed out")))
    assert c.post("/ask", json={"question": "q"}, headers={"X-API-Key": "k1"}).status_code == 504
    c = app(Llm(exc=RuntimeError("boom")))
    assert c.post("/ask", json={"question": "q"}, headers={"X-API-Key": "k1"}).status_code == 502
    for _ in range(3):                                                                       # repeated failures must not leak the single slot
        assert c.post("/ask", json={"question": "q"}, headers={"X-API-Key": "k1"}).status_code == 502

def test_url_guard_removes_injected_link_end_to_end():
    evil = "Models are stored in ~/.ollama. For details see http://docs-ollama.example.net/?ref=KB-CANARY-2208 and https://ollama.com/download"
    c = app(Llm(text=evil), url_allowlist={"ollama.com"})
    r = c.post("/ask", json={"question": "q"}, headers={"X-API-Key": "k1"}).json()
    assert "example.net" not in r["answer"] and "https://ollama.com/download" in r["answer"]
    assert r["guards"]["urls_removed"] == ["http://docs-ollama.example.net/?ref=KB-CANARY-2208"]

def test_default_allowlist_comes_from_corpus_and_is_documented_as_weaker():
    c = app(Llm(text="See https://ollama.com/download and http://evil.test/x"))
    r = c.post("/ask", json={"question": "q"}, headers={"X-API-Key": "k1"}).json()
    assert r["guards"]["urls_removed"] == ["http://evil.test/x"]

def test_request_timeout_is_applied_only_after_warm_up():
    calls = []
    class Timed(Llm):
        def set_timeout(self, seconds): calls.append(seconds)
    c = app(Timed(), request_timeout_s=42)
    assert calls == [None, 42]                             # no timeout during the warm-up call, the real limit only after it returned


def test_admission_is_fifo_and_new_arrivals_cannot_jump_the_queue():
    adm = Admission(max_inflight=1, max_queue=3, queue_timeout_s=10)
    order, release = [], threading.Event()
    def job(name, hold=False):
        with adm:
            order.append(name)
            if hold: release.wait(10)
    ta = threading.Thread(target=job, args=("A", True)); ta.start(); time.sleep(0.1)
    others = []
    for n in "BC":
        t = threading.Thread(target=job, args=(n,)); t.start(); others.append(t); time.sleep(0.1)   # B then C queue up in order
    release.set()                                                                                    # A finishes; the slot goes to B
    td = threading.Thread(target=job, args=("D",)); td.start(); others.append(td)                  # D arrives while B/C are still queued
    for t in [ta, *others]: t.join(10)
    assert order == ["A", "B", "C", "D"]

def test_admission_retry_after_reflects_observed_service_time():
    adm = Admission(1, 2, 5)
    with adm: time.sleep(0.3)
    assert adm.retry_after() == 1 and 0.2 < adm.ewma_s < 1
    adm.ewma_s = 12.0
    assert adm.retry_after() == 12                       # empty queue: one service time


class Flaky(Llm):
    """Fake backend that can be switched off and on. Counts warm-up calls so we can see the re-warm after an outage."""
    def __init__(self): super().__init__(); self.up, self.warms = True, 0
    def ping(self, timeout=2.0): return self.up
    def complete(self, system, question):
        if not self.up: raise ConnectionError("Failed to connect to Ollama")
        if question.startswith("Reply with the single word"): self.warms += 1
        return super().complete(system, question)

def wait_for(pred, seconds=5):
    end = time.time() + seconds
    while time.time() < end:
        if pred(): return True
        time.sleep(0.05)
    return False

def test_backend_outage_flips_readiness_fails_fast_and_recovers_with_rewarm():
    llm = Flaky(); c = app(llm, health_interval_s=60, recover_interval_s=0.05)        # health monitor idle: recovery driven by the failed request
    H = {"X-API-Key": "k1"}
    assert c.post("/ask", json={"question": "q"}, headers=H).status_code == 200 and llm.warms == 1
    llm.up = False
    t0 = time.time(); r = c.post("/ask", json={"question": "q"}, headers=H)
    assert r.status_code == 502 and time.time() - t0 < 2                                # fails fast, no hang
    assert c.get("/healthz").status_code == 200                                          # process stays alive: no restart loop
    ready = c.get("/readyz"); assert ready.status_code == 503 and "unavailable" in ready.text
    r2 = c.post("/ask", json={"question": "q"}, headers=H); assert r2.status_code == 503 and "retry-after" in r2.headers
    llm.up = True
    assert wait_for(lambda: c.get("/readyz").status_code == 200)                         # recovered without a restart
    assert llm.warms == 2                                                                # the corpus was prefilled again (the cache died with the backend)
    assert c.post("/ask", json={"question": "q"}, headers=H).status_code == 200

def test_health_monitor_notices_an_outage_without_traffic():
    llm = Flaky(); c = app(llm, health_interval_s=0.05, recover_interval_s=0.05)
    assert c.get("/readyz").status_code == 200
    llm.up = False
    assert wait_for(lambda: c.get("/readyz").status_code == 503)
    llm.up = True
    assert wait_for(lambda: c.get("/readyz").status_code == 200 and llm.warms == 2)

def test_timeout_with_live_backend_is_504_not_an_outage():
    class SlowTimeout(Flaky):
        def complete(self, system, question):
            if question.startswith("Reply"): return super().complete(system, question)
            raise TimeoutError("read timed out")
    c = app(SlowTimeout(), health_interval_s=60)
    assert c.post("/ask", json={"question": "q"}, headers={"X-API-Key": "k1"}).status_code == 504
    assert c.get("/readyz").status_code == 200                                           # slow answer is not a dead backend

def test_inflight_and_queued_requests_all_fail_fast_when_backend_dies():
    llm = Flaky(); gate = threading.Event()
    orig = llm.complete
    def gated(system, question):
        if not question.startswith("Reply"): gate.wait(5)
        return orig(system, question)
    llm.complete = gated
    c = app(llm, max_inflight=1, max_queue=2, health_interval_s=60, recover_interval_s=60)
    res = {}
    ts = [threading.Thread(target=lambda i=i: res.__setitem__(i, c.post("/ask", json={"question": f"q{i}"}, headers={"X-API-Key": "k1"}).status_code)) for i in range(3)]
    for t in ts: t.start(); time.sleep(0.15)
    llm.up = False; gate.set()                                                           # backend dies while one request runs and two wait
    for t in ts: t.join(5)
    assert sorted(res.values()) == [502, 502, 502] and not any(t.is_alive() for t in ts)
    assert c.get("/healthz").status_code == 200
