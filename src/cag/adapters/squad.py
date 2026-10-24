"""SQuAD subset, as in the CAG paper: take the first K articles, use each unique paragraph as a doc."""
import random
from ..corpus import Doc
from ..retrievers import BM25Retriever
from . import Dataset, Example

def build(articles: int = 3, n_questions: int = 50, seed: int = 0) -> Dataset:
    from datasets import load_dataset                # lazy: only needed for this adapter
    ds = load_dataset("rajpurkar/squad", split="train")
    titles = list(dict.fromkeys(ds["title"]))[:articles]
    keep = [r for r in ds if r["title"] in titles]
    return from_rows(keep, n_questions, seed)

def from_rows(rows: list[dict], n_questions: int, seed: int = 0) -> Dataset:
    """rows: dicts with title, context, question, answers{text:[..]}. Split out so tests need no download."""
    ctx_id: dict[str, str] = {}
    docs: list[Doc] = []
    for r in rows:
        if r["context"] not in ctx_id:
            ctx_id[r["context"]] = f"squad-{len(ctx_id):04d}"
            docs.append(Doc(ctx_id[r["context"]], r["title"], r["context"]))
    examples = [Example(r["question"], {ctx_id[r["context"]]}, list(r["answers"]["text"])) for r in rows]
    random.Random(seed).shuffle(examples)
    return Dataset(f"squad-{len(docs)}p", docs, examples[:n_questions], BM25Retriever(docs))
