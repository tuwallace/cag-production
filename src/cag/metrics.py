import re, string, statistics, collections

def normalize(s: str) -> str:
    s = s.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())

def f1(pred: str, gold: str) -> float:
    p, g = normalize(pred).split(), normalize(gold).split()
    common = collections.Counter(p) & collections.Counter(g)
    n = sum(common.values())
    if not p or not g or n == 0:
        return float(p == g)
    pr, rc = n / len(p), n / len(g)
    return 2 * pr * rc / (pr + rc)

def best_f1(pred: str, golds: list[str]) -> float:
    return max((f1(pred, g) for g in golds), default=0.0)

def contains_answer(pred: str, golds: list[str]) -> bool:
    """SQuAD EM is harsh on chatty LLM output; 'contains' is the fairer headline number."""
    return any(normalize(g) in normalize(pred) for g in golds)

def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]

def mean(values) -> float:
    return statistics.fmean(values) if values else 0.0

_REFUSAL = re.compile(r"not in the knowledge base|(do|does) not (contain|mention|provide|include|say|specify)|no (information|mention)|not mentioned|cannot find|can't find|couldn't find", re.I)

def is_refusal(pred: str) -> bool:
    return bool(_REFUSAL.search(pred))

def answer_correct(pred: str, any_of: list[str], all_of: list[str]) -> bool:
    """ALL of all_of must appear AND (if given) at least one of any_of."""
    n = normalize(pred)
    return all(normalize(a) in n for a in all_of) and (not any_of or any(normalize(a) in n for a in any_of))
