"""Regression gate (phase 8). Turns a run's saved answers into a few proportions, compares them with thresholds derived from a baseline run, and
reports pass / warn / fail. Thresholds come from the baseline's Wilson 95% lower (or upper) bound, rounded outward to 0.05, so normal sampling noise on
~90 questions does not fail a build but a real drop does. Also a corpus/prompt lock: a change to the corpus, the questions or the prompt text fails the
fast tier until the model tier has been re-run and the lock updated."""
import hashlib, json, math, pathlib
from dataclasses import dataclass
from . import metrics as M

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE_FILE = ROOT / "eval" / "gate.json"
LOCK_FILE = ROOT / "eval" / "corpus.lock.json"

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p, d = k / n, 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)

EPS = 1e-9                                        # proportions are floats: 0.9 - 0.95 must not fail a -0.05 bound by rounding error
floor05 = lambda x: math.floor(x * 20 + 1e-9) / 20
ceil05 = lambda x: math.ceil(x * 20 - 1e-9) / 20

def proportions(rows: list[dict]) -> dict:
    """k/n pairs for the gated metrics from answer rows of ONE system."""
    scored = [r for r in rows if "correct" in r]
    un = [r for r in scored if r["kind"] == "unanswerable"]
    ans = [r for r in scored if r["kind"] != "unanswerable"]
    tot_in = sum(r["uncached_in"] + r["cache_write"] + r["cache_read"] for r in rows)
    return {"overall_correct": (sum(r["correct"] == 1.0 for r in scored), len(scored)),
            "unanswerable_refused": (sum(r["correct"] == 1.0 for r in un), len(un)),
            "answerable_correct": (sum(r["correct"] == 1.0 for r in ans), len(ans)),
            "false_refusal": (sum(r["no_answer"] == 1.0 for r in ans), len(ans)),
            "cache_hit_ratio": (sum(r["cache_read"] for r in rows), tot_in),
            "p50_s": M.pct([r["latency_s"] for r in rows], 0.5)}

DIRECTION = {"overall_correct": "min", "unanswerable_refused": "min", "answerable_correct": "min", "false_refusal": "max", "cache_hit_ratio": "min"}

def calibrate(rows: list[dict], profile: dict, sources: list[str]) -> dict:
    prop = proportions(rows)
    metrics = {}
    for name, d in DIRECTION.items():
        k, n = prop[name]
        lo, hi = wilson(k, n)
        entry = {"baseline_k": k, "baseline_n": n, "baseline": round(k / n, 3) if n else None, "severity": "fail"}
        if d == "min":
            entry["min"] = 0.95 if name == "cache_hit_ratio" else floor05(lo)
        else:
            entry["max"] = ceil05(hi)
        metrics[name] = entry
    metrics["p50_s"] = {"baseline": round(prop["p50_s"], 2), "max": round(max(1.0, prop["p50_s"] * 3), 1), "severity": "warn"}   # hardware dependent: warn only
    return {"profile": profile, "sources": sources, "rule": "min = Wilson 95% lower bound of the baseline floored to 0.05; max = upper bound ceiled to 0.05; cache_hit_ratio >= 0.95; p50 <= 3x baseline (warn)",
            "metrics": metrics, "relative": {"cag_minus_rag_min": -0.05}}

@dataclass
class Check:
    name: str
    observed: float | None
    bound: str
    ok: bool
    severity: str
    n: int | None = None

def check(rows: list[dict], gate: dict, rag_rows: list[dict] | None = None) -> list[Check]:
    prop, out = proportions(rows), []
    for name, spec in gate["metrics"].items():
        if name == "p50_s":
            obs = prop["p50_s"]; out.append(Check(name, round(obs, 2), f"<= {spec['max']}", obs <= spec["max"] + EPS, spec["severity"], len(rows))); continue
        k, n = prop[name]
        obs = k / n if n else None
        if obs is None:
            out.append(Check(name, None, "no data", False, "fail", 0)); continue
        if "min" in spec: out.append(Check(name, round(obs, 3), f">= {spec['min']}", obs >= spec["min"] - EPS, spec["severity"], n))
        else: out.append(Check(name, round(obs, 3), f"<= {spec['max']}", obs <= spec["max"] + EPS, spec["severity"], n))
    if rag_rows:
        rp, margin = proportions(rag_rows), gate["relative"]["cag_minus_rag_min"]
        for name in ("overall_correct", "unanswerable_refused"):
            (k, n), (rk, rn) = prop[name], rp[name]
            diff = (k / n if n else 0) - (rk / rn if rn else 0)
            out.append(Check(f"cag_minus_rag:{name}", round(diff, 3), f">= {margin}", diff >= margin - EPS, "fail", n))
    return out

def load_rows(paths: list[str], system: str) -> list[dict]:
    return [r for p in paths for r in map(json.loads, open(p)) if r["system"] == system]

# ---- lock: what the baseline was measured on -------------------------------------------------------------------------------
def lock_state() -> dict:
    from .adapters.docs_qa import load_docs, QUESTIONS, QUESTIONS_NEW
    from .corpus import build_corpus
    from .systems import instructions
    c = build_corpus(load_docs())
    sha = lambda b: hashlib.sha256(b).hexdigest()[:16]
    return {"corpus_sha": c.sha, "n_docs": c.n_docs, "questions_sha": sha(QUESTIONS.read_bytes() + QUESTIONS_NEW.read_bytes()),
            "prompt_sha": sha((instructions("DOC-ID", "cite") + instructions("DOC-ID", "quote")).encode())}

def check_lock() -> list[Check]:
    if not LOCK_FILE.exists():
        return [Check("lock file", None, f"missing {LOCK_FILE.name}", False, "fail")]
    saved, now = json.loads(LOCK_FILE.read_text()), lock_state()
    return [Check(f"lock:{k}", None, "unchanged", saved.get(k) == v, "fail") for k, v in now.items()]
