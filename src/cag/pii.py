"""Pattern-based PII and secret redaction. Used twice: on the corpus before it is cached (everything cached is visible to every caller)
and on every answer before it leaves the service. Regexes only: they catch structured identifiers (email, phone, SSN, card numbers, common
secret formats) and cannot recognise names, addresses or free-text secrets. That needs an NER model and is not covered here."""
import re
from .corpus import Doc

def _luhn(digits: str) -> bool:
    s, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        s += d; alt = not alt
    return s % 10 == 0

PATTERNS = {   # order matters: secrets first so a key is not half-eaten by a number pattern
    "SECRET": re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----"
        r"|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b|\bsk-[A-Za-z0-9_-]{20,}\b|\bAIza[0-9A-Za-z_-]{35}\b"
        r"|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", re.S),
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"),
    "SSN": re.compile(r"(?<![\d-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\d-])"),
    "CARD": re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])"),                  # validated with Luhn below
    "PHONE": re.compile(r"(?<![\d.])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\d-])"),   # separators required: bare digit runs are ports and ids
}

def redact(text: str, kinds=None) -> tuple[str, dict]:
    """Returns (redacted text, {kind: count}). Placeholders look like [EMAIL]."""
    found: dict = {}
    for kind, pat in PATTERNS.items():
        if kinds and kind not in kinds:
            continue
        def sub(m, kind=kind):
            if kind == "CARD" and not _luhn(re.sub(r"\D", "", m.group(0))):
                return m.group(0)
            found[kind] = found.get(kind, 0) + 1
            return f"[{kind}]"
        text = pat.sub(sub, text)
    return text, found

def redact_docs(docs: list[Doc]) -> tuple[list[Doc], dict]:
    """Redact every chunk (title and text). Returns the new docs and total counts by kind."""
    out, total = [], {}
    for d in docs:
        t, f1 = redact(d.text); ti, f2 = redact(d.title)
        for k, v in (*f1.items(), *f2.items()):
            total[k] = total.get(k, 0) + v
        out.append(Doc(d.id, ti, t))
    return out, total
