import json, threading, time
import pytest
from cag.llm import Usage
from cag.shadow import ShadowRunner, jaccard
from cag.systems import Result

class Sys:
    def __init__(self, text="Ollama binds 127.0.0.1 [a-00]", delay=0.0, exc=None, gate=None):
        self.text, self.delay, self.exc, self.gate, self.calls = text, delay, exc, gate, 0
    def answer(self, q):
        self.calls += 1
        if self.gate: self.gate.wait(5)
        if self.delay: time.sleep(self.delay)
        if self.exc: raise self.exc
        return Result(self.text, {"a-00"}, Usage(input=1), self.delay or 0.01)

def runner(primary, candidate, **kw):
    recs = []; r = ShadowRunner(primary, candidate, recs.append, **kw); return r, recs

def test_primary_returns_before_slow_candidate_finishes():
    gate = threading.Event(); r, recs = runner(Sys(), Sys(gate=gate))
    t0 = time.time(); res = r.answer("q"); assert time.time() - t0 < 0.5 and res.answer and recs == []     # caller is not blocked
    gate.set(); r.close(); assert len(recs) == 1 and recs[0]["agree_refusal"] is True

def test_candidate_crash_never_reaches_the_caller_and_is_recorded():
    r, recs = runner(Sys(), Sys(exc=RuntimeError("boom")))
    assert r.answer("q").answer; r.close()
    assert r.counts["candidate_errors"] == 1 and "boom" in recs[0]["candidate"]["error"] and "agree_refusal" not in recs[0]

def test_primary_error_propagates():
    r, _ = runner(Sys(exc=RuntimeError("primary down")), Sys())
    with pytest.raises(RuntimeError, match="primary down"): r.answer("q")

def test_backlog_is_bounded_and_overflow_is_dropped_not_queued_forever():
    gate = threading.Event(); r, recs = runner(Sys(), Sys(gate=gate), max_pending=2)
    for i in range(6): r.answer(f"q{i}")
    assert r.counts["dropped"] >= 3                                                            # worker is stuck: only 2 may wait
    gate.set(); r.close(); assert len(recs) <= 3 and r.counts["compared"] == len(recs)

def test_comparison_fields_refusal_disagreement_and_overlap():
    r, recs = runner(Sys("Not in the knowledge base."), Sys("Ollama binds 127.0.0.1 port 11434")); r.answer("q"); r.close()
    assert recs[0]["agree_refusal"] is False and recs[0]["answer_overlap"] is None and recs[0]["primary"]["refused"] and not recs[0]["candidate"]["refused"]
    r, recs = runner(Sys("Models are stored in the models folder"), Sys("Models are stored in the models folder.")); r.answer("q"); r.close()
    assert recs[0]["answer_overlap"] == 1.0 and recs[0]["cited_overlap"] == 1.0

def test_store_text_modes_protect_user_content():
    for mode, has_q, has_a in (("none", False, False), ("redacted", True, True), ("full", True, True)):
        r, recs = runner(Sys("mail jane@example.org"), Sys("mail jane@example.org"), store_text=mode); r.answer("my SSN is 123-45-6789"); r.close()
        s = json.dumps(recs[0])
        assert ("question" in recs[0]) == has_q and ("answer" in recs[0]["primary"]) == has_a
        if mode != "full": assert "123-45-6789" not in s and "jane@example.org" not in s
        if mode == "none": assert "SSN" not in s                                               # not even a fragment of the question
        assert len(recs[0]["id"]) == 12

def test_jaccard():
    assert jaccard({"a"}, {"a"}) == 1 and jaccard({"a"}, {"b"}) == 0 and jaccard(set(), set()) == 1
