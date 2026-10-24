"""Short soak test against the running service: steady low traffic for N minutes while sampling the service process.
    PYTHONPATH=src uv run python scripts/soak_test.py --pid <uvicorn pid> --key KEY --minutes 20 --interval 8 --out reports/soak.json
Every 10th request is deliberately bad (wrong key or invalid body) so the error paths run too. Samples RSS, thread count and open files every 30 s,
and reports latency per 5-minute window, error counts, cache hit ratio, answer accuracy (keyword check on dev questions) and growth of RSS/threads/fds."""
import argparse, json, statistics as st, subprocess, threading, time
import httpx
from cag.adapters.docs_qa import build
from cag import metrics as M
from cag.systems import parse_answer

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://127.0.0.1:8000"); ap.add_argument("--pid", type=int, required=True); ap.add_argument("--key", required=True)
ap.add_argument("--minutes", type=float, default=20); ap.add_argument("--interval", type=float, default=8); ap.add_argument("--out", default="reports/soak.json")
a = ap.parse_args()
qs = [e for e in build(hybrid=False).examples if e.kind != "unanswerable" and (e.answers or e.all_of)]
unans = [e for e in build(hybrid=False).examples if e.kind == "unanswerable"]
samples, results, stop = [], [], threading.Event()

def sample():
    ps = subprocess.run(["ps", "-o", "rss=", "-p", str(a.pid)], capture_output=True, text=True).stdout.split()
    thr = subprocess.run(["ps", "-M", "-p", str(a.pid)], capture_output=True, text=True).stdout.strip().splitlines()
    fds = subprocess.run(["lsof", "-p", str(a.pid)], capture_output=True, text=True).stdout.strip().splitlines()
    return {"t": round(time.time() - t0), "rss_mb": round(int(ps[0]) / 1024, 1) if ps else None, "threads": max(0, len(thr) - 1), "fds": max(0, len(fds) - 1)}

def sampler():
    while not stop.wait(30): samples.append(sample())

t0 = time.time(); samples.append(sample()); threading.Thread(target=sampler, daemon=True).start()
H = {"X-API-Key": a.key}
with httpx.Client(timeout=300) as cl:
    i = 0
    while time.time() - t0 < a.minutes * 60:
        i += 1; start = time.time(); kind = "normal"
        if i % 10 == 0: kind = "bad_key" if (i // 10) % 2 else "bad_body"
        try:
            if kind == "bad_key": r = cl.post(a.base + "/ask", json={"question": "x"}, headers={"X-API-Key": "wrong"}); exp = 401
            elif kind == "bad_body": r = cl.post(a.base + "/ask", json={"question": ""}, headers=H); exp = 422
            else:
                e = unans[i % len(unans)] if i % 5 == 0 else qs[i % len(qs)]
                r = cl.post(a.base + "/ask", json={"question": e.question}, headers=H); exp = 200
            rec = {"t": round(start - t0), "kind": kind, "status": r.status_code, "expected": exp, "s": round(time.time() - start, 2)}
            if kind == "normal" and r.status_code == 200:
                j = r.json(); rec["hit"] = j["usage"]["hit_ratio"]; ans = parse_answer(j["answer"])
                rec["correct"] = (M.is_refusal(ans) if e.kind == "unanswerable" else M.answer_correct(ans, e.answers, e.all_of))
        except Exception as ex:
            rec = {"t": round(start - t0), "kind": kind, "status": type(ex).__name__, "expected": 200, "s": round(time.time() - start, 2)}
        results.append(rec)
        time.sleep(max(0, a.interval - (time.time() - start)))
stop.set(); samples.append(sample())

normal = [r for r in results if r["kind"] == "normal"]; ok = [r for r in normal if r["status"] == 200]
windows = {}
for r in ok: windows.setdefault(r["t"] // 300, []).append(r["s"])
slope = lambda ys: (st.linear_regression(range(len(ys)), ys).slope if len(ys) > 2 else 0)
summary = {"minutes": a.minutes, "requests": len(results), "normal": len(normal), "normal_ok": len(ok),
           "unexpected_status": [(r["kind"], r["status"], r["expected"]) for r in results if r["status"] != r["expected"]][:10],
           "latency_s_by_5min_window": {f"{k*5}-{k*5+5}min": {"n": len(v), "p50": round(st.median(v), 1), "max": round(max(v), 1)} for k, v in sorted(windows.items())},
           "mean_hit_ratio": round(st.fmean([r["hit"] for r in ok]), 3) if ok else None,
           "accuracy": f"{sum(r.get('correct', False) for r in ok)}/{len(ok)}",
           "rss_mb_first_last": [samples[0]["rss_mb"], samples[-1]["rss_mb"]], "rss_mb_max": max(s["rss_mb"] or 0 for s in samples),
           "rss_slope_mb_per_30s": round(slope([s["rss_mb"] for s in samples]), 3),
           "threads_first_last": [samples[0]["threads"], samples[-1]["threads"]], "fds_first_last": [samples[0]["fds"], samples[-1]["fds"]]}
json.dump({"summary": summary, "samples": samples, "results": results}, open(a.out, "w"), indent=1)
print(json.dumps(summary, indent=1))
