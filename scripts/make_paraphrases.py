"""Create paraphrased versions of known-good answers to stress-test attribution.
    PYTHONPATH=src uv run python scripts/make_paraphrases.py reports/<cite-run>.answers.jsonl [...] > eval/paraphrases.jsonl
    PYTHONPATH=src uv run python scripts/make_paraphrases.py --bad reports/<run>.answers.jsonl [...] > eval/paraphrases_bad.jsonl
Takes the first CORRECT, non-refused answer per answerable question; with --bad, every distinct NON-REFUSED answer to an UNANSWERABLE
question instead (fabricated answers: the negatives for a groundedness gate). P1 = reword, keep technical terms. P2 = plain language, no exact commands or names.
Paraphrases come from a local LLM and may drift from the source answer; spot-check before trusting a result."""
import json, os, sys, ollama
from cag.systems import parse_answer
from cag import metrics as M

MODEL = os.getenv("PARA_MODEL", "qwen3:8b")
P1 = ("Rewrite the answer below in different words. Keep exactly the same meaning and every technical detail. Do not add facts. "
      "Output only the rewritten answer.\n\nAnswer:\n{a}")
P2 = ("Rewrite the answer below in plain everyday language with different vocabulary. Do NOT use any exact commands, flags, file paths, "
      "environment variable names or product-specific terms; describe what they do instead (for example: 'the setting that controls...'). "
      "Keep the same meaning and do not add facts. Output only the rewritten answer.\n\nAnswer:\n{a}")
client = ollama.Client(host=os.getenv("OLLAMA_HOST"))
BAD = "--bad" in sys.argv
seen = set()
for path in [a for a in sys.argv[1:] if not a.startswith("--")]:
    for line in open(path):
        r = json.loads(line)
        if r["system"] not in ("cag", "rag"):
            continue
        ans = parse_answer(r["answer"])
        if M.is_refusal(ans):
            continue
        if BAD:
            if r["kind"] != "unanswerable" or (r["question"], ans) in seen:
                continue
            seen.add((r["question"], ans))
        else:
            if r["kind"] == "unanswerable" or r.get("correct") != 1.0 or r["question"] in seen:
                continue
            seen.add(r["question"])
        for level, tmpl in (("P1", P1), ("P2", P2)):
            out = client.chat(model=MODEL, think=False, options={"temperature": 0, "num_predict": 300},
                              messages=[{"role": "user", "content": tmpl.format(a=ans)}])["message"]["content"].strip()
            print(json.dumps({"question": r["question"], "gold": r["gold"], "level": level, "source": ans, "paraphrase": out, "label": "bad" if BAD else "good"}))
