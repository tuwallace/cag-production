"""Build eval/docs_qa_new.jsonl: 10 new answerable questions plus unanswerable candidates that survive a grep against the corpus.
Candidates whose key terms appear anywhere in data/ollama-docs are dropped (reported), so every kept question is absent from the corpus."""
import json, re, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
corpus = "\n".join(p.read_text() for p in sorted((ROOT / "data" / "ollama-docs").glob("*.md*"))).lower()

ANS = [
 ("Which command unloads a running model from memory?", ["cli#Stop a running model", "faq#How do I keep a model loaded"], ["ollama stop"], None, "single"),
 ("What does the REQUIRES instruction in a Modelfile specify?", ["modelfile#Instructions"], ["minimum version"], None, "single"),
 ("Which variable caps how many models can be loaded at once, and what is its default?", ["faq#How does Ollama handle concurrent"], ["3"], ["OLLAMA_MAX_LOADED_MODELS"], "single"),
 ("Where is the Ollama public key stored on Linux?", ["faq#Where can I find my Ollama Public Key"], ["/usr/share/ollama/.ollama/id_ed25519.pub"], None, "single"),
 ("How do I stop Ollama from launching at login on macOS?", ["faq#How can I stop Ollama"], ["Login Items"], None, "single"),
 ("Which proxy variable should I use for model pulls and which one should I avoid?", ["faq#How do I use Ollama behind a proxy"], None, ["HTTPS_PROXY", "HTTP_PROXY"], "single"),
 ("What docker command runs Ollama with AMD GPU support?", ["docker#AMD GPU"], ["ollama/ollama:rocm", "rocm"], None, "single"),
 ("Which API does Ollama use for GPU acceleration on Apple devices?", ["gpu#Metal"], ["Metal"], None, "single"),
 ("What are the minimum Windows version and NVIDIA driver version for Ollama on Windows?", ["windows#System Requirements"], None, ["22H2", "551.61"], "multi"),
 ("How do I change the context length from the Ollama app and from the command line?", ["context-length#Setting", "faq#How can I specify"], None, ["slider", "OLLAMA_CONTEXT_LENGTH"], "multi"),
]
UNANS = [
 ("Does Ollama support Apple Neural Engine acceleration?", [r"neural engine"]),
 ("How do I enable built-in rate limiting for the Ollama API?", [r"rate.?limit", r"throttl"]),
 ("How many models can be pulled in parallel?", [r"parallel (pull|download)", r"pulled in parallel", r"concurrent pull"]),
 ("How do I make Ollama write its logs as JSON?", [r"json format", r"log format", r"structured log", r"json log"]),
 ("What is the default value of OLLAMA_GPU_OVERHEAD?", [r"gpu_overhead", r"overhead"]),
 ("How do I set a password on the Ollama API?", [r"password", r"passphrase", r"basic auth"]),
 ("How do I make the Ollama server itself terminate TLS?", [r"\btls\b", r"\bssl\b"]),
 ("How do I export a model back to a GGUF file?", [r"\bexport"]),
 ("How do I limit the number of CPU threads Ollama uses?", [r"num_thread", r"\bthreads\b"]),
 ("What is the default value of the num_gpu parameter?", [r"num_gpu"]),
 ("How do I opt out of Ollama telemetry?", [r"telemetry", r"analytics"]),
 ("How do I schedule a model to unload at a specific time of day?", [r"schedul", r"\bcron\b"]),
 ("Where does Ollama keep its SQLite database?", [r"sqlite", r"database"]),
 ("How do I restore a model I deleted by mistake?", [r"restore", r"undelete", r"recover"]),
 ("Which Python versions does the Ollama Python library support?", [r"python"]),
 ("How do I install Ollama on FreeBSD?", [r"freebsd"]),
 ("Is there an official Homebrew formula for Ollama?", [r"brew"]),
 ("How do I route Ollama model pulls through a SOCKS5 proxy?", [r"socks"]),
 ("How do I expose Prometheus metrics from Ollama?", [r"prometheus", r"\bmetrics\b"]),
 ("Which tokenizer does llama3.2 use?", [r"tokenizer"]),
 ("Does Ollama support LoRA adapters?", [r"\blora\b", r"adapter"]),
 ("How do I enable multi-user authentication for an Ollama web UI?", [r"web ?ui", r"multi-user"]),
 ("How do I enable gRPC in Ollama?", [r"grpc"]),
 ("How do I deploy Ollama with Docker Compose?", [r"compose"]),
 ("How do I run Ollama on Kubernetes?", [r"kubernetes", r"\bk8s\b"]),
 ("Does Ollama support structured JSON schema outputs?", [r"json schema", r"structured output"]),
 ("What embedding dimension does nomic-embed-text produce?", [r"dimension"]),
 ("How do I set how many layers are offloaded to the GPU?", [r"\blayers\b"]),
 ("How do I back up my models to S3?", [r"\bs3\b", r"backup"]),
 ("Does the Windows installer support a silent install flag?", [r"silent", r"/verysilent"]),
 ("How do I verify the checksum of a downloaded model?", [r"checksum"]),
 ("What is the maximum number of GPUs Ollama can use at once?", [r"maximum number of gpus", r"max gpus"]),
 ("How do I enable gzip compression for API responses?", [r"gzip", r"compress"]),
 ("How do I configure a custom model registry mirror?", [r"mirror", r"registry"]),
 ("How do I change where the macOS server log file is written?", [r"change.{0,30}log", r"log.{0,30}location"]),
 ("What GPUs does Ollama support on Intel Macs?", [r"intel mac"]),
 ("Does Ollama support multi-node distributed inference?", [r"distributed", r"multi-node", r"tensor parallel"]),
 ("How do I enable text-to-speech output?", [r"text-to-speech", r"\btts\b"]),
 ("How do I use Ollama from a Jupyter notebook?", [r"jupyter"]),
 ("What is the default value of the mirostat parameter?", [r"mirostat"]),
 ("How do I set presence_penalty or frequency_penalty?", [r"presence_penalty", r"frequency_penalty"]),
 ("How do I use Ollama with GitHub Copilot?", [r"copilot"]),
 ("Does Ollama support the ONNX model format?", [r"onnx"]),
 ("How do I convert a PyTorch checkpoint with the ollama convert command?", [r"\bconvert"]),
 ("Which license does the Ollama software itself use?", [r"mit license", r"apache"]),
 ("How do I use Ollama with the OpenAI Python client?", [r"openai"]),
 ("How do I make Ollama send a webhook when a model finishes loading?", [r"webhook"]),
 ("How do I provision Ollama with Terraform?", [r"terraform"]),
 ("How do I enable GPU acceleration on a Raspberry Pi?", [r"raspberry"]),
]
kept, dropped = [], []
for q, pats in UNANS:
    hit = [p for p in pats if re.search(p, corpus)]
    (dropped if hit else kept).append((q, hit))
rows = [{"q": q, "type": t, "gold": g, **({"any": a} if a else {}), **({"all": al} if al else {})} for q, g, a, al, t in ANS]
rows += [{"q": q, "type": "unanswerable", "gold": []} for q, _ in kept[:40]]
(ROOT / "eval" / "docs_qa_new.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
print(f"answerable {len(ANS)}, unanswerable kept {min(len(kept), 40)} of {len(kept)} that passed the grep; {len(dropped)} dropped:")
for q, h in dropped: print("  dropped:", q, "<-", h)
