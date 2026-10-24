import json, logging
import pytest
from fastapi.testclient import TestClient
from cag.corpus import Doc, build_corpus
from cag.hardening import Settings
from cag.llm import Completion, Usage
from cag.pii import redact, redact_docs
from cag.service import create_app, prepare_docs
from cag.systems import CAG

POSITIVE = {
    "EMAIL": ["jane.doe@example.org", "ops+alerts@mail.corp.example.co.uk", "A_B-C@sub.domain.io"],
    "PHONE": ["(415) 555-0132", "415-555-0132", "415.555.0132", "+1 415 555 0132", "+44 20 7946 0958".replace("20 7946 0958", "207-946-0958")],
    "SSN": ["123-45-6789", "078-05-1120"],
    "CARD": ["4111 1111 1111 1111", "5500-0000-0000-0004", "378282246310005", "4012888888881881"],
    "SECRET": ["AKIAIOSFODNN7EXAMPLE", "ghp_" + "a" * 36, "xoxb-1234567890-abcdefghij", "sk-" + "A1b2C3d4" * 3,
               "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r",
               "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----"],
}
NEGATIVE = ["Ollama binds 127.0.0.1 port 11434 by default.", "sha256-00e1317cbf74d901080d7100f57580ba8dd8de57203072dc6f668324ba545f29",
            "version 0.5.7 released 2026-10-23", "ollama run llama3.2 --keepalive 5m", "OLLAMA_HOST=0.0.0.0:11434", "context 131072 tokens, 4k, 32k",
            "4111 1111 1111 1112 (fails the Luhn check)", "123-45-678", "000-12-3456", "666-12-3456", "see https://ollama.com/download", "C:\\Users\\%username%\\.ollama\\models",
            "RTX 5090 24 GB, compute capability 12.0", "ID 1234567890123456789012"]

@pytest.mark.parametrize("kind", POSITIVE)
def test_detects_each_kind(kind):
    for sample in POSITIVE[kind]:
        out, found = redact(f"before {sample} after")
        assert found.get(kind) == 1 and f"[{kind}]" in out, (kind, sample, out)
        assert sample not in out

@pytest.mark.parametrize("text", NEGATIVE)
def test_leaves_technical_text_alone(text):
    assert redact(text) == (text, {})

def test_counts_and_mixed_text():
    out, found = redact("Mail a@b.com or c@d.org, call 415-555-0132, SSN 123-45-6789.")
    assert found == {"EMAIL": 2, "PHONE": 1, "SSN": 1} and out.count("[EMAIL]") == 2

def test_precision_recall_on_labelled_set():
    tp = sum(redact(s)[1].get(k, 0) == 1 for k, v in POSITIVE.items() for s in v); n_pos = sum(len(v) for v in POSITIVE.values())
    fp = sum(bool(redact(s)[1]) for s in NEGATIVE)
    assert tp == n_pos and fp == 0

def test_redact_docs_scrubs_title_and_text_and_counts():
    docs = [Doc("a-00", "Contact bob@example.com", "Call 415-555-0132"), Doc("a-01", "clean", "nothing here")]
    out, found = redact_docs(docs)
    assert out[0].title == "Contact [EMAIL]" and out[0].text == "Call [PHONE]" and out[1] == docs[1] and found == {"EMAIL": 1, "PHONE": 1}

def test_prepare_docs_respects_setting_and_logs_counts_not_values(caplog):
    docs = [Doc("a-00", "t", "mail bob@example.com")]
    with caplog.at_level(logging.INFO, logger="cag.service"):
        out = prepare_docs(docs, Settings(auth_disabled=True))
    assert out[0].text == "mail [EMAIL]" and "bob@example.com" not in caplog.text and "EMAIL" in caplog.text
    assert prepare_docs(docs, Settings(auth_disabled=True, pii_corpus="off")) == docs

class Llm:
    model = "fake"
    def __init__(self, text): self.text = text
    def complete(self, system, question):
        if question.startswith("Reply with the single word"): return Completion("ready", Usage(input=1), 0.01)
        return Completion(self.text, Usage(input=5, cache_read=50), 0.01)

def client(text, **kw):
    cfg = Settings(auth_disabled=True, rate_per_min=60000, rate_burst=1000, **kw)
    c = TestClient(create_app(CAG(build_corpus([Doc("a-00", "t", "x")]), Llm(text)), cfg)); c.__enter__()
    import time
    for _ in range(100):
        if c.get("/readyz").status_code == 200: break
        time.sleep(0.05)
    return c

def test_answers_are_redacted_and_report_counts():
    c = client("Contact jane@example.org or 415-555-0132. Key AKIAIOSFODNN7EXAMPLE.")
    r = c.post("/ask", json={"question": "who?"}).json()
    assert "jane@example.org" not in r["answer"] and "415-555-0132" not in r["answer"] and "AKIA" not in r["answer"]
    assert r["guards"]["pii_redacted"] == {"SECRET": 1, "EMAIL": 1, "PHONE": 1}

def test_output_redaction_can_be_disabled_explicitly():
    c = client("mail jane@example.org", pii_output=False)
    assert "jane@example.org" in c.post("/ask", json={"question": "who?"}).json()["answer"]

def test_request_log_never_contains_the_question_or_the_answer(caplog):
    c = client("secret answer jane@example.org")
    with caplog.at_level(logging.INFO, logger="cag.service"):
        c.post("/ask", json={"question": "my SSN is 123-45-6789 what now"})
    assert "123-45-6789" not in caplog.text and "jane@example.org" not in caplog.text and "what now" not in caplog.text and '"event": "ask"' in caplog.text
