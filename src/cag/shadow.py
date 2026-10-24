"""Shadow mode (phase 8). The incumbent (primary) answers the caller. The candidate answers the same question in the background; its answer is
compared with the primary's and logged, never shown. A candidate that is slow, crashes or is overloaded cannot affect the caller: the candidate
runs in its own worker with a bounded backlog, and anything that does not fit is dropped and counted.
store_text: "none" keeps only hashes and metrics (use this on real traffic); "redacted" keeps PII-scrubbed text; "full" keeps everything
(for experiments on non-user questions only)."""
import hashlib, json, threading, time
from concurrent.futures import ThreadPoolExecutor
from .pii import redact
from .systems import parse_answer, Result
from . import metrics as M

def _tokens(text: str) -> set:
    return set(M.normalize(text).split())

def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a | b) else 1.0

def _view(res: Result | None, store_text: str, err: str | None) -> dict:
    if res is None:
        return {"error": err}
    final = parse_answer(res.answer)
    v = {"refused": M.is_refusal(final), "latency_s": round(res.latency_s, 3), "chars": len(res.answer), "cited": sorted(res.cited), "sources": list(res.sources)}
    if store_text == "full": v["answer"] = res.answer
    elif store_text == "redacted": v["answer"] = redact(res.answer)[0][:600]
    return v

class ShadowRunner:
    def __init__(self, primary, candidate, sink, store_text: str = "none", max_pending: int = 8):
        assert store_text in ("none", "redacted", "full")
        self.primary, self.candidate, self.sink, self.store_text, self.max_pending = primary, candidate, sink, store_text, max_pending
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="shadow")     # one worker: the candidate's single model slot is the limit
        self.pending, self.lock = 0, threading.Lock()
        self.counts = {"requests": 0, "compared": 0, "dropped": 0, "candidate_errors": 0}

    def answer(self, question: str, meta: dict | None = None) -> Result:
        res = self.primary.answer(question)            # primary errors propagate: shadow never hides them
        self.counts["requests"] += 1
        with self.lock:
            if self.pending >= self.max_pending:
                self.counts["dropped"] += 1; return res
            self.pending += 1
        self.pool.submit(self._shadow, question, res, meta or {})
        return res                                      # the caller never waits for the candidate

    def _shadow(self, question: str, pres: Result, meta: dict):
        t0, cres, err = time.time(), None, None
        try:
            cres = self.candidate.answer(question)
        except Exception as e:                         # noqa: a broken candidate is a finding, not an outage
            err = f"{type(e).__name__}: {e}"; self.counts["candidate_errors"] += 1
        finally:
            with self.lock: self.pending -= 1
        p, c = _view(pres, self.store_text, None), _view(cres, self.store_text, err)
        rec = {"id": hashlib.sha256(question.encode()).hexdigest()[:12], "ts": round(t0, 1), "q_chars": len(question), "primary": p, "candidate": c, "meta": meta}
        if self.store_text == "full": rec["question"] = question
        elif self.store_text == "redacted": rec["question"] = redact(question)[0][:300]
        if cres is not None:
            pf, cf = parse_answer(pres.answer), parse_answer(cres.answer)
            rec["agree_refusal"] = p["refused"] == c["refused"]
            rec["answer_overlap"] = round(jaccard(_tokens(pf), _tokens(cf)), 3) if not (p["refused"] or c["refused"]) else None
            rec["cited_overlap"] = round(jaccard(set(p["cited"]) | set(p["sources"]), set(c["cited"]) | set(c["sources"])), 3)
            self.counts["compared"] += 1
        self.sink(rec)

    def close(self, wait: bool = True):
        self.pool.shutdown(wait=wait)

def jsonl_sink(path):
    lock, f = threading.Lock(), open(path, "a")
    def write(rec):
        with lock: f.write(json.dumps(rec) + "\n"); f.flush()
    return write
