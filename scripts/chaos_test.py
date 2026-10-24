"""Kill-Ollama failure test against the running service (service on :8000, dedicated Ollama on :11435).
    PYTHONPATH=src uv run python scripts/chaos_test.py --service-pid <pid> --key KEY --out reports/chaos.json
S1 kill Ollama (SIGKILL, runner children too) 3 s into one long answer; watch /healthz, /readyz, /ask while it is down; restart Ollama; time the recovery.
S2 kill Ollama with one request running and two queued; every request must return promptly and no threads may leak.
S3 kill Ollama while idle; time until readiness flips (health monitor); restart; time to recover."""
import argparse, json, os, signal, subprocess, time, threading
import httpx

ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:8000"); ap.add_argument("--service-pid", type=int, required=True)
ap.add_argument("--key", required=True); ap.add_argument("--out", default="reports/chaos.json"); ap.add_argument("--log", default="/dev/null")
a = ap.parse_args()
H = {"X-API-Key": a.key}
LONG = "Explain how Ollama handles concurrent requests and which settings control it."
out = {}

def sh(cmd): return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
def ollama_pid(): return (sh(["lsof", "-ti", "tcp:11435", "-sTCP:LISTEN"]).split() or [None])[0]
def threads(): return max(0, len(sh(["ps", "-M", "-p", str(a.service_pid)]).splitlines()) - 1)

def kill_ollama():
    pid = ollama_pid()
    kids = sh(["pgrep", "-P", pid]).split() if pid else []
    for p in kids + ([pid] if pid else []):
        try: os.kill(int(p), signal.SIGKILL)
        except ProcessLookupError: pass
    return bool(pid)

def start_ollama():
    env = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11435", "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_FLASH_ATTENTION": "1"}
    subprocess.Popen(["ollama", "serve"], env=env, stdout=open(a.log, "ab"), stderr=subprocess.STDOUT, start_new_session=True)

def status(path, method="GET", timeout=10):
    t = time.time()
    try:
        r = httpx.request(method, a.base + path, headers=H, json={"question": "Where are models stored on macOS?"} if method == "POST" else None, timeout=timeout)
        return r.status_code, round(time.time() - t, 2)
    except Exception as e:
        return type(e).__name__, round(time.time() - t, 2)

def wait_ready(limit=900):
    t = time.time()
    while time.time() - t < limit:
        if status("/readyz")[0] == 200: return round(time.time() - t, 1)
        time.sleep(2)
    return None

def wait_not_ready(limit=120):
    t = time.time()
    while time.time() - t < limit:
        if status("/readyz")[0] != 200: return round(time.time() - t, 1)
        time.sleep(0.5)
    return None

assert wait_ready(60) is not None, "service is not ready before the test"
base_threads = threads()

# S1: kill mid-request
box = {}
def long_req():
    t = time.time()
    try:
        r = httpx.post(a.base + "/ask", json={"question": LONG}, headers=H, timeout=300); box["r"] = (r.status_code, round(time.time() - t, 2))
    except Exception as e: box["r"] = (type(e).__name__, round(time.time() - t, 2))
th = threading.Thread(target=long_req); th.start(); time.sleep(3)
t_kill = time.time(); kill_ollama(); th.join(120)
out["S1"] = {"inflight_request": box.get("r"), "seconds_from_kill_to_response": round(time.time() - t_kill, 2)}
during = []
for _ in range(6):
    during.append({"healthz": status("/healthz")[0], "readyz": status("/readyz")[0], "ask": status("/ask", "POST")}); time.sleep(1)
out["S1"]["while_down"] = during
start_ollama(); t_restart = time.time()
out["S1"]["seconds_to_ready_after_restart"] = wait_ready()
out["S1"]["first_ask_after_recovery"] = None
if out["S1"]["seconds_to_ready_after_restart"] is not None:
    r = httpx.post(a.base + "/ask", json={"question": "Where are models stored on macOS?"}, headers=H, timeout=300)
    out["S1"]["first_ask_after_recovery"] = {"status": r.status_code, "cache_hit_ratio": r.json()["usage"]["hit_ratio"] if r.status_code == 200 else None, "s": r.json().get("latency_s") if r.status_code == 200 else None}
print("S1", json.dumps(out["S1"]), flush=True)

# S2: one running + two queued, kill
res, ts = {}, []
def req(i):
    t = time.time()
    try: r = httpx.post(a.base + "/ask", json={"question": LONG}, headers=H, timeout=300); res[i] = (r.status_code, round(time.time() - t, 2))
    except Exception as e: res[i] = (type(e).__name__, round(time.time() - t, 2))
for i in range(3):
    t = threading.Thread(target=req, args=(i,)); t.start(); ts.append(t); time.sleep(0.4)
time.sleep(2); t_kill = time.time(); kill_ollama()
for t in ts: t.join(120)
out["S2"] = {"responses": res, "seconds_from_kill_until_all_returned": round(time.time() - t_kill, 2), "threads_before": base_threads, "threads_after": threads(), "healthz": status("/healthz")[0]}
start_ollama(); out["S2"]["seconds_to_ready_after_restart"] = wait_ready()
print("S2", json.dumps(out["S2"]), flush=True)

# S3: kill while idle
time.sleep(5); kill_ollama(); t_kill = time.time()
out["S3"] = {"seconds_until_readyz_flips": wait_not_ready(), "healthz": status("/healthz")[0]}
start_ollama(); out["S3"]["seconds_to_ready_after_restart"] = wait_ready()
out["S3"]["threads_after"] = threads()
print("S3", json.dumps(out["S3"]), flush=True)
json.dump(out, open(a.out, "w"), indent=1)
