"""Write a human review sheet for the golden questions: reports/review-sheet.md (generated, not tracked).
    PYTHONPATH=src uv run python scripts/make_review_sheet.py
For each question: type, gold chunks, the reference answer keywords with the line of the docs that contains each one, and (for unanswerable questions)
the nearest chunk, so a reviewer can answer 'is this question fair and is the reference right?' in a few seconds."""
import re
from cag.adapters.docs_qa import build, load_docs
from cag.attribution import Attributor
from cag.metrics import normalize

docs = load_docs(); by = {d.id: d for d in docs}; att = Attributor(docs)
out = ["# Golden question review sheet (generated)", "",
       "Files: `eval/docs_qa.jsonl` (dev, ids D01-D40) and `eval/docs_qa_new.jsonl` (held-out, ids N01-N50). Corpus: `data/ollama-docs/` split into 118 chunks.",
       "For each item mark **OK** or **FIX** and say why. Answerable: is the question clear, do the gold chunks answer it, is the reference keyword right (not too strict, not too loose)?",
       "Unanswerable: does ANY chunk answer it? (Nearest chunk is shown; search the docs if in doubt.)", ""]
def lines_with(text, needle):
    n = normalize(needle)
    return [l.strip() for l in text.splitlines() if n and n in normalize(l)][:2]
for split, tag in (("dev", "D"), ("new", "N")):
    out.append(f"## {'Dev' if split == 'dev' else 'Held-out'} questions\n")
    for i, e in enumerate(build(hybrid=False, split=split).examples, 1):
        out.append(f"### {tag}{i:02d} [{e.kind}] {e.question}")
        if e.kind == "unanswerable":
            top = att.attribute(e.question)
            out.append(f"- expected behaviour: the system should answer *Not in the knowledge base*")
            out.append(f"- nearest chunk: `{top.ids[0] if top.ids else '-'}` ({by[top.ids[0]].title if top.ids else ''})")
        else:
            out.append("- gold chunks: " + ", ".join(f"`{g}` ({by[g].title})" for g in sorted(e.gold_ids)))
            if e.answers: out.append(f"- reference (ANY of): {e.answers}")
            if e.all_of: out.append(f"- reference (ALL of): {e.all_of}")
            gold_text = "\n".join(by[g].text for g in sorted(e.gold_ids))
            for kw in (*e.answers, *e.all_of):
                ev = lines_with(gold_text, kw)
                out.append(f"  - `{kw}` appears in: " + (" / ".join(f"“{x[:140]}”" for x in ev) if ev else "**NOT FOUND in gold chunks**"))
        out.append("- verdict: [ ] OK  [ ] FIX   notes:\n")
open("reports/review-sheet.md", "w").write("\n".join(out)); print(f"wrote reports/review-sheet.md ({len(out)} lines)")
