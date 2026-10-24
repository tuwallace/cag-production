from fastapi.testclient import TestClient
from cag.corpus import Doc, build_corpus, check_budget
from cag.llm import Usage, Completion
from cag.systems import CAG, RAG, extract_citations
from cag.adapters.squad import from_rows
from cag.evaluate import run, to_markdown
from cag.service import create_app
from cag.hardening import Settings
OPEN = Settings(auth_disabled=True, rate_per_min=60000, rate_burst=1000)   # tests that are not about auth or limits
import pytest

class FakeLLM:
    """Simulates Ollama prefix reuse: the first call with a given system prefix prefills it all, later calls only the question."""
    model = "fake"
    def __init__(self): self.seen = {}; self.calls = []
    def complete(self, system, question):
        import re
        self.calls.append((system, question))
        n = len(system) // 4
        u = Usage(output=5)
        if system in self.seen:
            u.input = 20; u.cache_read = self.seen[system] - 20
        else:
            u.input = u.cache_write = n + 20; self.seen[system] = n + 20
        ids = re.findall(r'<doc id="([^"]+)"', system)
        return Completion(f"Answer is Paris [{ids[0]}]" if ids else "Not in the knowledge base.", u, 0.01)

ROWS = [
    {"title": "France", "context": "Paris is the capital of France.", "question": "Capital of France?", "answers": {"text": ["Paris"]}},
    {"title": "France", "context": "The Seine flows through Paris.", "question": "Which river?", "answers": {"text": ["Seine"]}},
]

def test_corpus_is_deterministic_and_order_independent():
    a = [Doc("b", "t", "x"), Doc("a", "t", "y")]
    assert build_corpus(a).sha == build_corpus(list(reversed(a))).sha

def test_duplicate_ids_rejected():
    with pytest.raises(ValueError): build_corpus([Doc("a", "t", "x"), Doc("a", "t", "y")])

def test_budget_check():
    c = build_corpus([Doc("a", "t", "x" * 4000)])
    check_budget(c, 200_000)
    with pytest.raises(ValueError): check_budget(c, 3_000)

def test_citation_extraction_ignores_unknown_ids():
    assert extract_citations("see [a, b] and [zzz]", {"a", "b"}) == {"a", "b"}

def test_prefix_is_byte_identical_and_cache_is_hit_on_second_call():
    ds = from_rows(ROWS, 2)
    corpus = build_corpus(ds.docs); llm = FakeLLM(); cag = CAG(corpus, llm)
    r1, r2 = cag.answer("q1"), cag.answer("q2 different")
    assert llm.calls[0][0] == llm.calls[1][0]            # nothing dynamic in the prefix
    assert r1.usage.cache_write > 0 and r2.usage.cache_read > 0 and r2.usage.cache_write == 0

def test_question_never_in_cached_block():
    corpus = build_corpus(from_rows(ROWS, 2).docs); llm = FakeLLM(); CAG(corpus, llm).answer("SECRET-QUESTION")
    assert "SECRET-QUESTION" not in llm.calls[0][0]

def test_eval_report_cag_hits_cache_and_rag_does_not():
    rep = run(from_rows(ROWS, 2), FakeLLM(), k=1)
    assert rep["systems"]["cag"]["cache_hit_ratio"] > 0.5
    assert rep["systems"]["rag"]["cache_hit_ratio"] == 0
    assert "cag" in to_markdown(rep)

def test_service_ready_after_warm_and_ask():
    corpus = build_corpus(from_rows(ROWS, 2).docs)
    with TestClient(create_app(CAG(corpus, FakeLLM()), OPEN)) as c:
        for _ in range(50):
            if c.get("/readyz").status_code == 200: break
            __import__("time").sleep(0.1)
        assert c.get("/readyz").status_code == 200
        r = c.post("/ask", json={"question": "Capital?"}).json()
        assert r["cited"] and r["usage"]["cache_read"] > 0
        assert c.get("/corpus").json()["n_docs"] == 2
        assert c.post("/ask", json={"question": ""}).status_code == 422


def test_service_answers_health_while_warming_and_reports_not_ready():
    import threading, time
    class SlowLLM(FakeLLM):
        gate = threading.Event()
        def complete(self, system, question):
            self.gate.wait(5); return super().complete(system, question)
    corpus = build_corpus(from_rows(ROWS, 2).docs)
    with TestClient(create_app(CAG(corpus, SlowLLM()), OPEN)) as c:
        assert c.get("/healthz").status_code == 200            # alive while warming
        assert c.get("/readyz").status_code == 503              # but not ready
        assert c.post("/ask", json={"question": "q"}).status_code == 503
        SlowLLM.gate.set()
        for _ in range(50):
            if c.get("/readyz").status_code == 200: break
            time.sleep(0.1)
        assert c.get("/readyz").status_code == 200

def test_service_reports_warmup_failure():
    class BrokenLLM(FakeLLM):
        def complete(self, system, question): raise RuntimeError("ollama down")
    corpus = build_corpus(from_rows(ROWS, 2).docs)
    with TestClient(create_app(CAG(corpus, BrokenLLM()), OPEN)) as c:
        time_left = 50
        while time_left and "ollama down" not in c.get("/readyz").text: time_left -= 1; __import__("time").sleep(0.1)
        r = c.get("/readyz"); assert r.status_code == 503 and "ollama down" in r.text
