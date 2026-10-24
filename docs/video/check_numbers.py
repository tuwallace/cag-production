"""Check the video script against the repository: every number in Appendix A of script.md is re-computed from committed data (or found in the
document that records it), and the segment times are compared with the word counts of the narration.
    PYTHONPATH=src python docs/video/check_numbers.py        (exit code 1 if anything does not match)"""
import json, pathlib, re, sys
HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path.insert(0, str(ROOT / "src"))
from cag import gate as G
from cag.adapters.docs_qa import build, load_docs
from cag.corpus import build_corpus
from cag.metrics import pct

script = (HERE / "script.md").read_text()
A = json.loads(re.search(r"## Appendix A.*?```json\n(.*?)```", script, re.S).group(1))
bad = []
def check(name, expected, actual, tol=0.0):
    ok = abs(expected - actual) <= tol + 1e-9 if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) else expected == actual
    print(f"  {'ok ' if ok else 'BAD'} {name:<52} script={expected!s:<12} repo={actual!s}")
    if not ok: bad.append(name)
def in_doc(name, doc, pattern):
    text = (ROOT / "docs" / doc).read_text(); ok = re.search(pattern, text) is not None
    print(f"  {'ok ' if ok else 'BAD'} {name:<52} found in docs/{doc}" if ok else f"  BAD {name:<52} NOT found in docs/{doc}: {pattern}")
    if not ok: bad.append(name)
def rows(name, system): return [r for r in map(json.loads, open(ROOT / "eval" / "baselines" / name)) if r["system"] == system]

print("corpus and questions")
docs = load_docs(); c = build_corpus(docs)
check("sections", A["corpus"]["sections"], len(docs)); check("files", A["corpus"]["files"], len({d.id.rsplit('-', 1)[0] for d in docs}))
cap = (HERE / "demo" / "captured" / "seg4_cache.txt").read_text(); first = re.search(r"first call.*?([\d,]{6,})", cap)
check("prompt tokens, qwen3 (thousands, from the live capture)", A["corpus"]["prompt_tokens_thousands_qwen3"], round(int(first.group(1).replace(",", "")) / 1000))
ex = {sp: build(hybrid=False, split=sp).examples for sp in ("dev", "new", "all")}
q = A["questions"]
check("total", q["total"], len(ex["all"])); check("dev", q["dev"], len(ex["dev"])); check("held_out", q["held_out"], len(ex["new"]))
check("unanswerable", q["unanswerable"], sum(e.kind == "unanswerable" for e in ex["all"])); check("answerable", q["answerable"], sum(e.kind != "unanswerable" for e in ex["all"]))
check("held_out_unanswerable", q["held_out_unanswerable"], sum(e.kind == "unanswerable" for e in ex["new"]))

print("held-out results (eval/baselines)")
for key, (file, system) in {"8b_cag": ("8b-quote-new.answers.jsonl", "cag"), "8b_rag": ("8b-quote-new.answers.jsonl", "rag"),
                            "32b_cag": ("32b-quote-new.answers.jsonl", "cag"), "32b_rag": ("32b-quote-new.answers.jsonl", "rag")}.items():
    rs = rows(file, system); un = [r for r in rs if r["kind"] == "unanswerable"]; e = A["held_out"][key]
    check(f"{key} correct", e["correct"], round(sum(r["correct"] == 1.0 for r in rs) / len(rs), 2))
    check(f"{key} unanswerable refused", e["unanswerable_refused"], sum(r["correct"] == 1.0 for r in un))
    check(f"{key} median seconds", e["p50_s"], round(pct([r["latency_s"] for r in rs], .5), 1))
dev8 = [r for r in rows("8b-quote-dev.answers.jsonl", "cag") if r["kind"] == "unanswerable"]; new8 = [r for r in rows("8b-quote-new.answers.jsonl", "cag") if r["kind"] == "unanswerable"]
check("small model refused, first 40", A["small_model_unanswerable_refused"]["first_40"], f"{sum(r['correct'] == 1.0 for r in dev8)} of {len(dev8)}")
check("small model refused, new 50", A["small_model_unanswerable_refused"]["new_50"], f"{sum(r['correct'] == 1.0 for r in new8)} of {len(new8)}")

print("cache and quotes")
base = rows("32b-quote-dev.answers.jsonl", "cag") + rows("32b-quote-new.answers.jsonl", "cag")
check("cache hit ratio (32B baseline)", A["cache"]["hit_ratio"], round(G.proportions(base)["cache_hit_ratio"][0] / G.proportions(base)["cache_hit_ratio"][1], 3))
chaos = json.load(open(HERE / "demo" / "data" / "chaos-8b.json"))
cold_live = float(re.search(r"first call.*?\s([\d.]+) s\s+[\d.]+ s", cap).group(1))
check("cold start 8B: outage recovery / live capture (s)", A["cache"]["cold_8b_s_range"], [round(chaos["S1"]["seconds_to_ready_after_restart"]), round(cold_live)])
in_doc("cold start 32B 508 s", "09-docs-qa-results.md", r"\*\*508 s\*\*"); in_doc("eviction 65.7 s", "08-prototype.md", r"\*\*65\.7 s\*\*")
d8 = rows("8b-quote-dev.answers.jsonl", "cag")
check("citations after quote prompt (first 40)", A["quotes"]["citations_after"], round(sum(r["cite_hit"] for r in d8) / len(d8), 2))
check("refused after quote prompt (first 40)", A["quotes"]["refused_after"], round(sum(r["correct"] == 1.0 for r in dev8) / len(dev8), 2))
in_doc("citations before/after 0.05 -> 0.65", "09-docs-qa-results.md", r"0\.05 to 0\.65"); in_doc("refused before 0.82 -> 0.27", "09-docs-qa-results.md", r"0\.82 -> 0\.27")
in_doc("system-side hit range 0.93-1.00", "09-docs-qa-results.md", r"0\.93-1\.00")

print("check flip (recorded)")
in_doc("first 40: semantic 0.87, word overlap 0.69", "09-docs-qa-results.md", r"0\.87 / 0\.85 / 0\.81.*0\.69 / 0\.62 / 0\.80")
in_doc("new 50: word overlap 0.90, semantic 0.66", "09-docs-qa-results.md", r"\*\*0\.90\*\*.*\*\*0\.66\*\*")

print("outage, security, load")
o = A["outage"]
check("in-flight request error seconds", o["inflight_error_s"], chaos["S1"]["seconds_from_kill_to_response"]); check("idle outage detected (s)", o["idle_detected_s"], chaos["S3"]["seconds_until_readyz_flips"])
check("recovered (s)", o["recovered_s"], round(chaos["S1"]["seconds_to_ready_after_restart"]))
pii = json.load(open(HERE / "demo" / "data" / "pii-test.json"))["table"]; keys = ("email", "phone", "card", "aws key", "ssn")
check("PII values leaked, raw corpus", A["security"]["pii_leaked_raw"], sum(pii["raw corpus"][k] > 0 for k in keys))
check("PII values leaked, with redaction", A["security"]["pii_leaked_redacted"], sum(pii["raw corpus + output redaction"][k] > 0 for k in keys))
in_doc("0 of 39 commands obeyed (both models)", "12-security-tests.md", r"\| P1 override obeyed \| 0/39 \| 0/39 \|"); in_doc("tracking link on 32B 1 of 39", "12-security-tests.md", r"\*\*1/39\*\*")
in_doc("false fact adopted 2 of 2 (both)", "12-security-tests.md", r"\| P3 false fact adopted \| \*\*2/2\*\* \| \*\*2/2\*\* \|")
in_doc("about 5 requests a minute", "12-security-tests.md", r"about 5 requests per minute"); in_doc("shed in about 10 ms", "12-security-tests.md", r"about 10 ms")

print("gate")
gate = json.loads((ROOT / "eval" / "gate.json").read_text())
check("overall_correct min", A["gate"]["overall_min"], gate["metrics"]["overall_correct"]["min"]); check("unanswerable_refused min", A["gate"]["unanswerable_min"], gate["metrics"]["unanswerable_refused"]["min"])
ok32 = all(c.ok or c.severity == "warn" for c in G.check(G.load_rows([str(ROOT / "eval/baselines/32b-quote-dev.answers.jsonl"), str(ROOT / "eval/baselines/32b-quote-new.answers.jsonl")], "cag"), gate))
ok8 = all(c.ok or c.severity == "warn" for c in G.check(G.load_rows([str(ROOT / "eval/baselines/8b-quote-dev.answers.jsonl"), str(ROOT / "eval/baselines/8b-quote-new.answers.jsonl")], "cag"), gate))
check("32B passes the gate", A["gate"]["checks_on_32b"], "pass" if ok32 else "fail"); check("8B fails the gate", A["gate"]["checks_on_8b"], "pass" if ok8 else "fail")

print("segment times (estimate at 133 words a minute + 1 s between segments)")
segs = re.findall(r"^## (\d+)\. .*?\n(.*?)(?=^## |\Z)", script.split("## Appendix A")[0], re.S | re.M)
plan = dict(re.findall(r"^\| (\d+) \| (\d+:\d\d) \|", script, re.M)); t = 0.0; total = 0
for n, body in segs:
    narr = " ".join(re.findall(r"^> (.*)$", body.split("**Narration:**")[1].split("**On-screen")[0].split("**Honesty")[0], re.M)); w = len(narr.split()); total += w
    claimed = plan[n]; cm = int(claimed.split(":")[0]) * 60 + int(claimed.split(":")[1]); off = abs(cm - t)
    print(f"  {'ok ' if off <= 12 else 'BAD'} segment {n:>2}: {w:>3} words, computed start {int(t // 60)}:{int(t % 60):02d}, plan says {claimed}")
    if off > 12: bad.append(f"time segment {n}")
    t += w / 133 * 60 + 1
print(f"  total {total} words, about {int(t // 60)}:{int(t % 60):02d}")
print("\n" + ("ALL NUMBERS MATCH" if not bad else f"MISMATCHES: {bad}")); sys.exit(1 if bad else 0)
