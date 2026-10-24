"""Local LLM via Ollama. Ollama keeps the KV cache of the previous prompt in a slot and reuses it when the
next prompt starts with the same tokens, so CAG = keep the model loaded + keep the system prefix byte-identical.
Ollama does not report cache hits, and `prompt_eval_count` includes reused tokens (measured: 14,864 tokens on both a
65.7 s cold call and a 0.22 s warm call). The signal is `prompt_eval_duration`, so reuse is inferred from prefill speed."""
import json, os, pathlib, time
from dataclasses import dataclass

@dataclass
class Usage:
    input: int = 0          # prompt tokens NOT served from cache (inferred)
    cache_write: int = 0    # prompt tokens prefilled on the first (cold) call of a given prefix
    cache_read: int = 0     # prompt tokens inferred as reused from the KV cache
    output: int = 0
    prefill_s: float = 0.0  # time spent on prompt evaluation (Ollama's prompt_eval_duration)

    @property
    def hit_ratio(self) -> float:
        total = self.input + self.cache_read
        return self.cache_read / total if total else 0.0

@dataclass
class Completion:
    text: str
    usage: Usage
    latency_s: float

RATE_FILE = pathlib.Path(__file__).resolve().parents[2] / "reports" / ".prefill_rate.json"

class ContextOverflow(RuntimeError):
    pass

class OllamaLLM:
    def __init__(self, model: str | None = None, num_ctx: int | None = None, max_tokens: int = 300,
                 keep_alive: str | None = None, host: str | None = None, timeout: float | None = None):
        import ollama
        self._host = host or os.getenv("CAG_OLLAMA_HOST") or os.getenv("OLLAMA_HOST")
        self.client = ollama.Client(host=self._host, timeout=timeout)   # timeout: per-phase httpx limit; for a non-streaming chat the read phase is the whole generation
        self.model = model or os.getenv("CAG_MODEL", "qwen3:8b")
        self.num_ctx = num_ctx or int(os.getenv("CAG_NUM_CTX", "32768"))   # must stay constant: changing it reloads the model and drops the cache
        self.max_tokens = max_tokens
        self.keep_alive = keep_alive or os.getenv("CAG_KEEP_ALIVE", "60m")
        self._rate_key = f"{self.model}:{self.num_ctx}"
        self._rate = self._load_rate()                                     # cold prefill seconds per token (running max, persisted)

    def _load_rate(self) -> float:
        try: return float(json.loads(RATE_FILE.read_text()).get(self._rate_key, 0.0))
        except Exception: return 0.0

    def _save_rate(self) -> None:
        try:
            d = json.loads(RATE_FILE.read_text()) if RATE_FILE.exists() else {}
            d[self._rate_key] = self._rate; RATE_FILE.write_text(json.dumps(d))
        except Exception: pass

    def ping(self, timeout: float = 2.0) -> bool:
        """Cheap liveness check of the Ollama server (lists models); False on any error."""
        import ollama
        try:
            ollama.Client(host=self._host, timeout=timeout).list(); return True
        except Exception:
            return False

    def set_timeout(self, seconds: float | None) -> None:
        """Used by the service after the (long) warm-up so that only real requests are time limited."""
        import ollama
        self.client = ollama.Client(host=self._host, timeout=seconds)

    def complete(self, system: str, question: str) -> Completion:
        t0 = time.perf_counter()
        r = self.client.chat(
            model=self.model, think=False, keep_alive=self.keep_alive,
            options={"num_ctx": self.num_ctx, "num_predict": self.max_tokens, "temperature": 0},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": question}])
        latency = time.perf_counter() - t0
        prompt_tokens = r.get("prompt_eval_count") or 0
        prefill_s = (r.get("prompt_eval_duration") or 0) / 1e9
        u = Usage(output=r.get("eval_count") or 0, prefill_s=prefill_s)
        if prompt_tokens >= 2000 and prefill_s > 0:                        # long prompts only: short ones are dominated by overhead
            if prefill_s / prompt_tokens > self._rate:
                self._rate = prefill_s / prompt_tokens                     # slowest seen per-token prefill = cold speed
                self._save_rate()
        full_s = self._rate * prompt_tokens
        reused = min(1.0, max(0.0, 1 - prefill_s / full_s)) if full_s and prompt_tokens >= 2000 else 0.0
        if reused > 0.5:                                                   # <50% saved = treat as a miss (noise)
            u.cache_read = round(prompt_tokens * reused)
        elif prompt_tokens >= 2000:
            if prompt_tokens >= 0.95 * self.num_ctx:                       # Ollama silently truncates; refuse instead
                raise ContextOverflow(f"prompt filled {prompt_tokens}/{self.num_ctx} tokens; shrink the corpus or raise num_ctx")
            u.cache_write = prompt_tokens
        u.input = prompt_tokens - u.cache_read
        return Completion(r["message"]["content"], u, latency)
