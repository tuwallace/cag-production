"""Segment 9 on-screen demo: killing Ollama in the middle of a request. REPLAY of a real run (scripts/chaos_test.py, 2026-10-23, qwen3:8b service):
the captured result is in demo/data/chaos-8b.json.   python docs/video/demo/seg9_outage.py"""
import json, pathlib
d = json.load(open(pathlib.Path(__file__).parent / "data" / "chaos-8b.json")); s1, s2, s3 = d["S1"], d["S2"], d["S3"]
print("\n  REPLAY of a captured run: Ollama is killed (SIGKILL) while the service is answering\n")
print(f"  request in flight when Ollama died      -> HTTP {s1['inflight_request'][0]} after {s1['seconds_from_kill_to_response']} s (not a hang)")
w = s1["while_down"][0]
print(f"  while it is down, every second:           /healthz {w['healthz']} (alive)   /readyz {w['readyz']} (not ready)   /ask {w['ask'][0]} in {w['ask'][1]} s")
print(f"  1 running + 2 queued, then killed        -> {', '.join(str(v[0]) for v in s2['responses'].values())}, all back {s2['seconds_from_kill_until_all_returned']} s after the kill")
print(f"  killed while idle (nobody asking)        -> /readyz flips to 503 after {s3['seconds_until_readyz_flips']} s")
print(f"  Ollama restarted: the service re-reads the docs by itself -> ready after {s1['seconds_to_ready_after_restart']:.0f} s, no restart of the service")
f = s1["first_ask_after_recovery"]; print(f"  first answer afterwards                  -> HTTP {f['status']}, {f['cache_hit_ratio']:.1%} of the prompt from the cache, {f['s']:.1f} s\n")
