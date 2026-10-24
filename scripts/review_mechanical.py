"""Mechanical review of the golden questions (no model). Catches errors a second reader would: reference answers that the gold chunks do not
contain, gold specs that are broad, duplicate questions, and 'unanswerable' questions whose words all appear in the corpus.
    PYTHONPATH=src uv run python scripts/review_mechanical.py"""
import re
from cag.adapters.docs_qa import build, load_docs
from cag.attribution import Attributor
from cag.metrics import normalize
from cag.systems import _terms
from cag.shadow import jaccard

docs = load_docs(); by_id = {d.id: d for d in docs}
exs = build(hybrid=False, split="all").examples
corpus_norm = normalize(" ".join(d.text for d in docs)); vocab = set(corpus_norm.split())
att = Attributor(docs)
problems = []

print("== answerable questions: are the reference answers supported by the gold chunks?")
for e in exs:
    if e.kind == "unanswerable": continue
    gold_text = normalize(" ".join(by_id[i].text for i in e.gold_ids))
    miss_all = [a for a in e.all_of if normalize(a) not in gold_text]
    any_hit = [a for a in e.answers if normalize(a) in gold_text]
    if miss_all or (e.answers and not any_hit):
        problems.append(("reference not in gold chunks", e.question, {"missing all_of": miss_all, "any-of present": any_hit, "gold": sorted(e.gold_ids)}))
    in_other = [a for a in e.answers if normalize(a) in corpus_norm and normalize(a) not in gold_text]
    if len(e.gold_ids) > 4: problems.append(("broad gold spec (>4 chunks)", e.question, sorted(e.gold_ids)))
    # keyword answers so short they would match almost anything
    short = [a for a in (*e.answers, *e.all_of) if len(normalize(a)) <= 2]
    if short: problems.append(("very short reference string (matches by accident)", e.question, short))

print("== unanswerable questions: how many of their content words appear in the corpus?")
rows = []
for e in exs:
    if e.kind != "unanswerable": continue
    terms = _terms(e.question); absent = sorted(t for t in terms if t not in vocab and normalize(t) not in vocab)
    top = att.attribute(e.question)
    rows.append((len(absent) / max(1, len(terms)), e.question, absent, top.ids[:1]))
rows.sort()
for frac, q, absent, top in rows[:12]:
    print(f"  absent-term share {frac:.2f}  top chunk {top}  absent {absent}  | {q}")
adjacent = [r for r in rows if r[0] == 0]
print(f"  {len(adjacent)} of {len(rows)} unanswerable questions have NO word missing from the corpus (topic-adjacent: these need a human or LLM read)")
for frac, q, absent, top in adjacent: problems.append(("unanswerable but every word occurs in the corpus", q, top))

print("== duplicates and near-duplicates")
for i in range(len(exs)):
    for j in range(i + 1, len(exs)):
        s = jaccard(_terms(exs[i].question), _terms(exs[j].question))
        if s >= 0.7: problems.append(("near-duplicate questions", exs[i].question, f"{exs[j].question} (jaccard {s:.2f})"))
dups = len(exs) - len({e.question.lower() for e in exs}); print("  exact duplicates:", dups)

print(f"\n== {len(problems)} item(s) flagged for adjudication")
for kind, q, detail in problems: print(f"- [{kind}] {q}\n    {detail}")
