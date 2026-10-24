import json, sys
import pytest
from cag import gate as G

def rows(n_ans=10, ans_ok=10, n_un=10, un_ok=10, hit=True, lat=3.0):
    out = []
    for i in range(n_ans):
        ok = i < ans_ok
        out.append({"system": "cag", "kind": "single", "correct": 1.0 if ok else 0.0, "no_answer": 0.0, "uncached_in": 50, "cache_write": 0,
                    "cache_read": 25000 if hit else 0, "latency_s": lat})
    for i in range(n_un):
        ok = i < un_ok
        out.append({"system": "cag", "kind": "unanswerable", "correct": 1.0 if ok else 0.0, "no_answer": 1.0 if ok else 0.0, "uncached_in": 50,
                    "cache_write": 0, "cache_read": 25000 if hit else 0, "latency_s": lat})
    return out

def test_wilson_known_values():
    lo, hi = G.wilson(51, 51); assert 0.92 < lo < 0.94 and hi == pytest.approx(1.0)
    lo, hi = G.wilson(0, 10); assert lo == 0.0 and 0.25 < hi < 0.31
    assert G.wilson(0, 0) == (0.0, 1.0)

def test_rounding_goes_outward():
    assert G.floor05(0.9299) == 0.9 and G.floor05(0.95) == 0.95 and G.ceil05(0.2501) == 0.3 and G.ceil05(0.25) == 0.25

def test_calibration_thresholds_are_below_baseline_and_documented():
    gate = G.calibrate(rows(30, 27, 30, 30), {"model": "m"}, ["x.jsonl"])
    m = gate["metrics"]
    assert m["unanswerable_refused"]["min"] <= m["unanswerable_refused"]["baseline"]
    assert m["answerable_correct"]["min"] < 0.9 and m["false_refusal"]["max"] > 0.0 and m["cache_hit_ratio"]["min"] == 0.95
    assert m["p50_s"]["severity"] == "warn" and gate["sources"] == ["x.jsonl"]

def results(gate, r, rag=None): return {c.name: c for c in G.check(r, gate, rag)}

def test_baseline_passes_its_own_gate_and_regressions_fail():
    gate = G.calibrate(rows(40, 36, 40, 40), {}, [])
    assert all(c.ok for c in G.check(rows(40, 36, 40, 40), gate))
    worse = results(gate, rows(40, 36, 40, 25))                                  # abstention collapses to 62%
    assert not worse["unanswerable_refused"].ok and not worse["overall_correct"].ok
    assert not results(gate, rows(40, 20, 40, 40))["answerable_correct"].ok
    assert not results(gate, rows(40, 36, 40, 40, hit=False))["cache_hit_ratio"].ok      # e.g. a timestamp slipped into the prompt prefix

def test_latency_is_warn_only():
    gate = G.calibrate(rows(10, 10, 10, 10, lat=3.0), {}, [])
    slow = G.check(rows(10, 10, 10, 10, lat=30.0), gate)
    p50 = next(c for c in slow if c.name == "p50_s")
    assert not p50.ok and p50.severity == "warn"

def test_no_data_fails_instead_of_passing_silently():
    gate = G.calibrate(rows(), {}, [])
    only_answerable = [r for r in rows() if r["kind"] != "unanswerable"]
    assert not results(gate, only_answerable)["unanswerable_refused"].ok

def test_relative_gate_against_rag():
    gate = G.calibrate(rows(40, 36, 40, 40), {}, [])
    rag = [dict(r, system="rag") for r in rows(40, 40, 40, 40)]
    res = results(gate, rows(40, 36, 40, 40), rag)
    assert res["cag_minus_rag:overall_correct"].ok                                # -0.05: exactly at the margin
    res = results(gate, rows(40, 30, 40, 40), rag)
    assert not res["cag_minus_rag:overall_correct"].ok

def test_lock_detects_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "LOCK_FILE", tmp_path / "lock.json")
    assert not G.check_lock()[0].ok                                               # missing lock file
    (tmp_path / "lock.json").write_text(json.dumps(G.lock_state()))
    assert all(c.ok for c in G.check_lock())
    stale = G.lock_state(); stale["corpus_sha"] = "0" * 16; stale["prompt_sha"] = "1" * 16
    (tmp_path / "lock.json").write_text(json.dumps(stale))
    bad = {c.name for c in G.check_lock() if not c.ok}
    assert bad == {"lock:corpus_sha", "lock:prompt_sha"}

def test_committed_lock_matches_the_repository():
    assert all(c.ok for c in G.check_lock()), "corpus, questions or prompt changed: re-run the model tier, then `ci_gate.py update-lock`"

def test_cli_exit_codes(tmp_path):
    import subprocess, os
    good, bad = tmp_path / "good.jsonl", tmp_path / "bad.jsonl"
    good.write_text("\n".join(json.dumps(r) for r in rows(40, 36, 40, 40)))
    bad.write_text("\n".join(json.dumps(r) for r in rows(40, 36, 40, 10)))
    gate = tmp_path / "gate.json"; gate.write_text(json.dumps(G.calibrate(rows(40, 36, 40, 40), {}, [])))
    env = {**os.environ, "PYTHONPATH": "src"}
    run = lambda f, *extra: subprocess.run([sys.executable, "scripts/ci_gate.py", "replay", "--gate", str(gate), "--answers", str(f), *extra], env=env, capture_output=True, text=True)
    assert run(good).returncode == 0
    r = run(bad); assert r.returncode == 1 and "FAIL" in r.stdout and "GATE: FAILED" in r.stdout
    assert subprocess.run([sys.executable, "scripts/ci_gate.py", "replay", "--gate", str(gate), "--answers", str(good), "--system", "nope"], env=env, capture_output=True).returncode == 2


def test_bounds_are_not_failed_by_float_rounding():
    gate = {"metrics": {"overall_correct": {"min": 0.9, "severity": "fail"}}, "relative": {"cag_minus_rag_min": -0.05}}
    r = [{"system": "cag", "kind": "single", "correct": 1.0 if i < 9 else 0.0, "no_answer": 0.0, "uncached_in": 1, "cache_write": 0, "cache_read": 1, "latency_s": 1} for i in range(10)]
    assert G.check(r, gate)[0].ok                                                  # exactly 0.9 against min 0.9
