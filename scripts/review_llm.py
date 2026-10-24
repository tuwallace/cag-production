"""Second reviewer for the golden questions: a local model from a different family than the systems under test (they are Qwen).
    CAG_OLLAMA_HOST=http://127.0.0.1:11435 PYTHONPATH=src uv run python scripts/review_llm.py --model llama3.1:8b-instruct-q8_0 --out reports/review-llama31-8b.json
Check A (all 90 questions, whole corpus in context, cached): does the corpus contain enough to answer the question? The reviewer must copy a sentence
as evidence; we verify it word for word, so a claim without real evidence is flagged as the reviewer's own error. Labels give a calibration:
how often does this reviewer agree with questions we KNOW are answerable?
Check B (answerable questions only, gold chunks only): can the question be answered from just the gold chunks, is it ambiguous, and does the reviewer's
own answer match the reference keywords?
The reviewer is another model, not an independent human: treat every flag as a lead to adjudicate, not as a verdict."""
import argparse, json, time
from dotenv import load_dotenv
from cag.adapters.docs_qa import build, load_docs
from cag.corpus import build_corpus
from cag.llm import OllamaLLM
from cag.metrics import answer_correct, normalize

SCHEMA_A = {"type": "object", "required": ["answerable", "doc_id", "evidence", "confidence"], "properties": {
    "answerable": {"type": "boolean"}, "doc_id": {"type": "string"}, "evidence": {"type": "string"}, "confidence": {"type": "integer"}}}
SCHEMA_B = {"type": "object", "required": ["answerable_from_text", "answer", "ambiguous", "issue"], "properties": {
    "answerable_from_text": {"type": "string", "enum": ["yes", "partial", "no"]}, "answer": {"type": "string"}, "ambiguous": {"type": "boolean"}, "issue": {"type": "string"}}}
PROMPT_A = ("You are reviewing a documentation question set. The documents below are the ONLY source of truth. For each question the user sends, decide whether the "
            "documents contain enough information to answer it. Be strict: a related topic or a general inference does not count; the answer itself must be stated. "
            "Reply with JSON only: answerable (true/false); doc_id (the id of the document that contains the answer, or empty); evidence (one sentence copied word for word "
            "from that document, or empty); confidence (1-5).\n\nDocuments:\n\n")
PROMPT_B = ("You are a careful reader. Use ONLY the text below. Decide whether the user's question can be answered from this text: yes, partial or no. Give a short answer taken from "
            "the text, say whether the question is ambiguous or double-barrelled, and describe any issue with the question in one sentence (empty if none). Reply with JSON only.\n\nText:\n\n")

def ask(llm, system, question, schema):
    kw = dict(model=llm.model, keep_alive=llm.keep_alive, format=schema, options={"num_ctx": llm.num_ctx, "num_predict": 300, "temperature": 0},
              messages=[{"role": "system", "content": system}, {"role": "user", "content": question}])
    for think in ({"think": False}, {}):
        try:
            r = llm.client.chat(**kw, **think); break
        except Exception as e:
            if think == {}: raise
    try: return json.loads(r["message"]["content"])
    except Exception: return {"_unparsed": r["message"]["content"][:200]}

def main():
    load_dotenv()
    ap = argparse.ArgumentParser(); ap.add_argument("--model", required=True); ap.add_argument("--window", type=int, default=40960); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    docs = load_docs(); by = {d.id: d for d in docs}; corpus = build_corpus(docs); exs = build(hybrid=False, split="all").examples
    llm = OllamaLLM(a.model, num_ctx=a.window, max_tokens=300)
    sysA = PROMPT_A + corpus.text
    t = time.time(); ask(llm, sysA, "Warm-up question: where are models stored?", SCHEMA_A); print(f"corpus prefilled in {time.time() - t:.0f}s", flush=True)
    A, B = [], []
    for e in exs:
        r = ask(llm, sysA, e.question, SCHEMA_A)
        doc = by.get(r.get("doc_id", ""))
        verified = bool(r.get("evidence")) and (normalize(r["evidence"]) in normalize(doc.text) if doc else any(normalize(r["evidence"]) in normalize(d.text) for d in docs))
        A.append({"question": e.question, "label": "unanswerable" if e.kind == "unanswerable" else "answerable", "reviewer": r, "evidence_verified": verified,
                  "in_gold_chunk": bool(doc and doc.id in e.gold_ids)})
    print("check A done", flush=True)
    for e in exs:
        if e.kind == "unanswerable": continue
        text = "\n\n".join(f"[{i}]\n{by[i].text}" for i in sorted(e.gold_ids))
        r = ask(llm, PROMPT_B + text, e.question, SCHEMA_B)
        agrees = answer_correct(r.get("answer", ""), e.answers, e.all_of) if "answer" in r else None
        B.append({"question": e.question, "reviewer": r, "answer_matches_reference": agrees, "references": {"any": e.answers, "all": e.all_of}})
    json.dump({"model": a.model, "A": A, "B": B}, open(a.out, "w"), indent=1)
    # summary
    ans = [x for x in A if x["label"] == "answerable"]; un = [x for x in A if x["label"] == "unanswerable"]
    yes = lambda x: x["reviewer"].get("answerable") is True
    print(f"\nCheck A calibration: answerable labelled & reviewer says answerable {sum(map(yes, ans))}/{len(ans)} (with verified evidence {sum(yes(x) and x['evidence_verified'] for x in ans)}); "
          f"unanswerable labelled & reviewer says NOT answerable {sum(not yes(x) for x in un)}/{len(un)}")
    print("\nFlag 1: labelled UNANSWERABLE, reviewer says answerable:")
    for x in un:
        if yes(x): print(f"  [{'evidence verified' if x['evidence_verified'] else 'evidence NOT verbatim'}] {x['question']}\n      -> {x['reviewer'].get('doc_id')}: {x['reviewer'].get('evidence', '')[:160]}")
    print("\nFlag 2: labelled ANSWERABLE, reviewer says not answerable:")
    for x in ans:
        if not yes(x): print(f"  {x['question']}\n      -> {x['reviewer']}")
    print("\nCheck B: answerable from gold chunks alone?")
    from collections import Counter
    print("  ", dict(Counter(x["reviewer"].get("answerable_from_text", "?") for x in B)), " ambiguous:", sum(bool(x["reviewer"].get("ambiguous")) for x in B),
          " reviewer answer matches reference:", sum(bool(x["answer_matches_reference"]) for x in B), "/", len(B))
    for x in B:
        r = x["reviewer"]
        if r.get("answerable_from_text") != "yes" or r.get("ambiguous") or not x["answer_matches_reference"] or r.get("issue"):
            print(f"  - {x['question']}\n      verdict={r.get('answerable_from_text')} ambiguous={r.get('ambiguous')} matches_ref={x['answer_matches_reference']} issue={r.get('issue', '')[:140]}\n      reviewer answer: {str(r.get('answer', ''))[:140]}")

if __name__ == "__main__":
    main()
