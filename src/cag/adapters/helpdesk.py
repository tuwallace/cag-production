"""Helpdesk tickets from ../helpdesk-rag, scored on its golden set (citation-only: no reference answers).
Doc text matches helpdesk-rag's `ingest.build_docs`, so CAG and RAG see identical ticket content."""
import json, pandas as pd
from ..corpus import Doc
from ..retrievers import HELPDESK_ROOT, HelpdeskRagRetriever, BM25Retriever
from . import Dataset, Example

RAW = HELPDESK_ROOT / "data" / "raw" / "data"

def doc_id(i: int) -> str:
    return f"ticket-{int(i):05d}"

def load_docs() -> list[Doc]:
    t = pd.read_csv(RAW / "tickets.csv")
    c = pd.read_csv(RAW / "comments.csv")
    cat = pd.read_csv(RAW / "categories.csv").rename(columns={"id": "category_id", "name": "category"})
    t = t.merge(cat[["category_id", "category"]], on="category_id", how="left")
    c = c[c["visibility"] == "public"].sort_values("created_at")          # internal notes must never be cached
    thread = c.groupby("ticket_id")["body"].apply(lambda s: "; ".join(dict.fromkeys(s.astype(str))))
    t["hrs"] = (pd.to_datetime(t["resolved_at"]) - pd.to_datetime(t["created_at"])).dt.total_seconds() / 3600
    docs = []
    for _, r in t.iterrows():
        text = (f"{r['summary']} {r['description']}\nCategory: {r['category']}. Service: {r['affected_service']}. "
                f"Priority: {r['priority']}. Status: {r['status']}. Channel: {r['channel']}.")
        if pd.notna(r["hrs"]):
            text += f" Resolved in {r['hrs']:.1f}h."
        if thread.get(int(r["ticket_id"])):
            text += f"\nPublic updates: {thread[int(r['ticket_id'])]}"
        docs.append(Doc(doc_id(r["ticket_id"]), str(r["summary"]), text))
    return docs

def build(n_questions: int = 26, baseline: str = "helpdesk-rag", max_docs: int = 200) -> Dataset:
    """A local 8B model has a 32-40k window, so only the first `max_docs` tickets are cached. Gold ids are
    intersected with that subset and questions with no gold left are dropped, for BOTH systems."""
    docs = load_docs()[:max_docs]
    keep = {d.id for d in docs}
    golden = [json.loads(l) for l in (HELPDESK_ROOT / "eval" / "golden.jsonl").read_text().splitlines() if l.strip()]
    ex = [Example(g["question"], {doc_id(i) for i in g["relevant_ids"]} & keep) for g in golden if not g.get("needs_review")]
    ex = [e for e in ex if e.gold_ids]
    retriever = HelpdeskRagRetriever(docs) if baseline == "helpdesk-rag" else BM25Retriever(docs)
    return Dataset(f"helpdesk-{len(docs)}t", docs, ex[:n_questions], retriever)
