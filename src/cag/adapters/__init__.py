from dataclasses import dataclass, field
from ..corpus import Doc

@dataclass
class Example:
    question: str
    gold_ids: set                       # doc ids that support the answer
    answers: list = field(default_factory=list)   # reference answers: ANY one appearing counts (empty = citation-only scoring)
    all_of: list = field(default_factory=list)    # ALL of these must appear (multi-document synthesis)
    kind: str = "single"                          # single | multi | conflict | unanswerable

@dataclass
class Dataset:
    name: str
    docs: list[Doc]
    examples: list[Example]
    retriever: object                   # has .retrieve(question, k) -> list[Doc]
