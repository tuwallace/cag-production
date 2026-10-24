from fastapi.testclient import TestClient
import pytest
from cag import metrics as M
from cag.adapters.docs_qa import load_docs, resolve, build

def test_answer_correct_requires_all_and_any():
    assert M.answer_correct("Set OLLAMA_CONTEXT_LENGTH to 32k", ["32k", "32768"], ["OLLAMA_CONTEXT_LENGTH"])
    assert not M.answer_correct("Set OLLAMA_CONTEXT_LENGTH", ["32k"], ["OLLAMA_CONTEXT_LENGTH"])
    assert not M.answer_correct("32k", ["32k"], ["OLLAMA_CONTEXT_LENGTH"])

def test_refusal_detection():
    assert M.is_refusal("Not in the knowledge base.")
    assert M.is_refusal("The documents do not mention this.")
    assert not M.is_refusal("Ollama binds to 127.0.0.1.")

def test_gold_specs_all_resolve_and_unanswerable_have_no_gold():
    ds = build(hybrid=False)                      # raises if any gold spec matches no chunk
    for e in ds.examples:
        assert bool(e.gold_ids) == (e.kind != "unanswerable")

def test_unknown_gold_spec_fails_loudly():
    with pytest.raises(ValueError): resolve("faq#No such heading", load_docs())

from cag.systems import parse_answer, parse_quotes, instructions

def test_parse_answer_scores_only_answer_part():
    t = 'Quotes:\n> "Set OLLAMA_HOST to change it" [faq-09]\nAnswer: Use OLLAMA_HOST.\nSources: [faq-09]'
    assert parse_answer(t) == "Use OLLAMA_HOST."
    assert parse_answer("Not in the knowledge base.") == "Not in the knowledge base."
    assert parse_quotes(t) == [("Set OLLAMA_HOST to change it", "faq-09")]

def test_quote_style_prompt_has_format_and_refusal():
    p = instructions("faq-01", "quote")
    assert "Quotes:" in p and "Sources:" in p and "Not in the knowledge base." in p

from cag.systems import verify_quotes
from cag.llm import Usage
from cag.evaluate import _usage_of

DOCS = {"faq-09": "Ollama binds 127.0.0.1 port 11434 by default. Change it with OLLAMA_HOST."}

def fmt(quote, doc="faq-09"):
    return f'Quotes:\n> "{quote}" [{doc}]\nAnswer: x\nSources: [{doc}]'

def test_verify_accepts_verbatim_and_ignores_case_punct():
    assert verify_quotes(fmt("Ollama binds 127.0.0.1 port 11434 by default"), DOCS) == (True, "grounded")
    assert verify_quotes(fmt("ollama BINDS 127.0.0.1, port 11434"), DOCS)[0]

def test_verify_rejects_fabricated_wrong_doc_missing_doc_and_no_quotes():
    assert verify_quotes(fmt("Ollama supports mutual TLS out of the box"), DOCS) == (False, "ungrounded:faq-09")
    assert verify_quotes(fmt("Change it with OLLAMA_HOST", "faq-99"), DOCS)[1] == "ungrounded:faq-99"
    assert verify_quotes("Answer: yes\nSources: [faq-09]", DOCS) == (False, "no_quotes")

def test_verify_passes_refusal_and_handles_ellipsis():
    assert verify_quotes("Not in the knowledge base.", DOCS) == (True, "refusal")
    assert verify_quotes(fmt("Ollama binds ... Change it with OLLAMA_HOST"), DOCS)[0]
    assert not verify_quotes(fmt("Ollama binds ... and invented tail"), DOCS)[0]

def test_usage_roundtrip():
    u = _usage_of({"uncached_in": 1, "cache_write": 2, "cache_read": 3, "out": 4, "prefill_s": 0.5})
    assert (u.input, u.cache_write, u.cache_read, u.output) == (1, 2, 3, 4)

from cag.systems import verify_soft

SOFT_DOCS = {"faq-09": "## How can I expose Ollama on my network?\nOllama binds 127.0.0.1 port 11434 by default. Change it with OLLAMA_HOST.",
             "faq-14": "## Where are models stored?\nOn macOS models live in ~/.ollama/models."}

def two(q1, d1, q2, d2):
    return f'Quotes:\n> "{q1}" [{d1}]\n> "{q2}" [{d2}]\nAnswer: x\nSources: [{d1}]'

def test_soft_keeps_answer_when_one_quote_is_bad_and_repairs_citation():
    t = two("invented sentence about TLS", "faq-09", "Change it with OLLAMA_HOST", "faq-14")     # 2nd quote real but wrong id
    ok, reason, cited = verify_soft(t, SOFT_DOCS, "How do I change the Ollama host?")
    assert ok and cited == {"faq-09"}

def test_soft_rejects_when_no_quote_is_grounded():
    assert verify_soft(two("made up", "faq-09", "also made up", "faq-14"), SOFT_DOCS, "q")[:2] == (False, "no_grounded_quote")

def test_relevance_rejects_real_but_off_topic_quote():
    t = 'Quotes:\n> "On macOS models live in ~/.ollama/models" [faq-14]\nAnswer: x\nSources: [faq-14]'
    assert verify_soft(t, SOFT_DOCS, "How do I configure mutual TLS authentication for clients?", 0.25)[0] is False
    assert verify_soft(t, SOFT_DOCS, "Where are Ollama models stored on macOS?", 0.25)[0] is True

from cag.systems import parse_quotes

def test_lenient_parser_accepts_unquoted_blockquote_lines():
    t = "Quotes:\n> `100% CPU` means the model was loaded entirely in system memory [faq-04]\nAnswer: x"
    assert parse_quotes(t) == []
    got = parse_quotes(t, lenient=True)
    assert len(got) == 1 and got[0][1] == "faq-04" and "means the model was loaded" in got[0][0]

from cag.attribution import Attributor
from cag.corpus import Doc

ADOCS = [Doc("faq-09", "faq: expose", "Ollama binds 127.0.0.1 port 11434 by default. Change it with OLLAMA_HOST."),
         Doc("faq-14", "faq: models", "Models are stored in ~/.ollama/models on macOS. Set OLLAMA_MODELS to move them."),
         Doc("gpu-00", "gpu: nvidia", "CUDA_VISIBLE_DEVICES limits Ollama to a subset of NVIDIA GPUs.")]

def test_attribution_finds_supporting_chunk_ignoring_model_ids():
    at = Attributor(ADOCS).attribute("Answer: Set OLLAMA_MODELS to move the model directory.\nSources: [gpu-00]")   # wrong id written by model
    assert at.ids[0] == "faq-14" and at.support > 0.5

def test_attribution_refusal_and_unsupported_answer():
    assert Attributor(ADOCS).attribute("Not in the knowledge base.").ids == []
    low = Attributor(ADOCS).attribute("Mutual TLS authentication requires certificates configured in Kubernetes.")
    assert low.support < 0.5

def test_service_returns_system_side_sources():
    from cag.service import create_app
    from cag.hardening import Settings
    from cag.corpus import build_corpus
    from cag.systems import CAG
    corpus = build_corpus(ADOCS)
    class Llm:
        model = "fake"
        def complete(self, system, question):
            from cag.llm import Completion, Usage
            return Completion("Set OLLAMA_MODELS to move them [gpu-00]", Usage(input=5, cache_read=10), 0.01)
    with TestClient(create_app(CAG(corpus, Llm(), attributor=Attributor(ADOCS)), Settings(auth_disabled=True, rate_per_min=60000, rate_burst=1000))) as c:
        r = c.post("/ask", json={"question": "Where are models stored?"}).json()
        assert r["sources"][0] == "faq-14" and r["cited"] == ["gpu-00"]

def _ollama_up():
    try:
        import ollama; ollama.Client().list(); return True
    except Exception:
        return False

@pytest.mark.skipif(not _ollama_up(), reason="needs a local Ollama with nomic-embed-text")
def test_semantic_attributor_finds_reworded_source():
    from cag.attribution import SemanticAttributor
    at = SemanticAttributor(ADOCS, "hybrid").attribute("The setting that decides where downloaded models are kept on disk is OLLAMA_MODELS.")
    assert at.ids[0] == "faq-14" and at.sem > 0.5

def test_new_split_loads_and_is_mostly_unanswerable():
    ds = build(hybrid=False, split="new")
    assert len(ds.examples) == 50
    assert sum(e.kind == "unanswerable" for e in ds.examples) == 40
    assert all(not e.gold_ids for e in ds.examples if e.kind == "unanswerable")
    dev_q = {e.question for e in build(hybrid=False, split="dev").examples}
    assert not dev_q & {e.question for e in ds.examples}          # no leakage between splits
