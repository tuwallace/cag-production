"""Service hardening (phase 7): API keys, per-client rate limiting, bounded admission queue with timeouts, and an output URL guard.
All state is in memory, so limits are per process. Run more than one replica and each enforces its own."""
import math, os, re, secrets, threading, time
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urlparse

@dataclass
class Settings:
    api_keys: dict = field(default_factory=dict)     # api key -> client name
    auth_disabled: bool = False
    rate_per_min: float = 12.0                       # sustained requests per minute per client
    rate_burst: int = 4                              # bucket size
    max_inflight: int = 1                            # requests generating at once (= Ollama slots)
    max_queue: int = 2                               # requests allowed to wait for a slot
    queue_timeout_s: float = 180.0                   # >= (max_queue + 1) x worst-case answer time (~65 s for 32B at 300 tokens)
    request_timeout_s: float = 120.0                 # longest the model may take to answer
    health_interval_s: float = 10.0                  # how often the service pings the model backend while ready
    recover_interval_s: float = 3.0                  # how often it retries while the backend is down
    pii_corpus: str = "redact"                      # "redact" or "off": scrub the corpus before it is cached
    pii_output: bool = True                          # scrub every answer before it leaves the service
    url_allowlist: set | None = None                 # None = derive from the served corpus (weaker); empty set = no links allowed

    @classmethod
    def from_env(cls) -> "Settings":
        keys = {}
        for i, item in enumerate(filter(None, (os.getenv("CAG_API_KEYS") or "").split(","))):
            name, sep, key = item.strip().partition(":")
            keys[key if sep else name] = name if sep else f"client-{i + 1}"
        s = cls(api_keys=keys, auth_disabled=os.getenv("CAG_AUTH_DISABLED") == "1",
                rate_per_min=float(os.getenv("CAG_RATE_PER_MIN", "12")), rate_burst=int(os.getenv("CAG_RATE_BURST", "4")),
                max_inflight=int(os.getenv("CAG_MAX_INFLIGHT", "1")), max_queue=int(os.getenv("CAG_MAX_QUEUE", "2")),
                queue_timeout_s=float(os.getenv("CAG_QUEUE_TIMEOUT_S", "180")), request_timeout_s=float(os.getenv("CAG_REQUEST_TIMEOUT_S", "120")))
        s.health_interval_s = float(os.getenv("CAG_HEALTH_INTERVAL_S", "10")); s.recover_interval_s = float(os.getenv("CAG_RECOVER_INTERVAL_S", "3"))
        s.pii_corpus = os.getenv("CAG_PII_CORPUS", "redact"); s.pii_output = os.getenv("CAG_PII_OUTPUT", "1") != "0"
        raw = os.getenv("CAG_URL_ALLOWLIST")
        if raw is not None:
            s.url_allowlist = {h.strip().lower() for h in raw.split(",") if h.strip() and h.strip().lower() != "none"}
        s.validate()
        return s

    def validate(self):
        if not self.api_keys and not self.auth_disabled:
            raise RuntimeError("no API keys configured: set CAG_API_KEYS=name:key,... or CAG_AUTH_DISABLED=1 for local use")

def authenticate(settings: Settings, x_api_key: str | None, authorization: str | None) -> str | None:
    """Returns the client name, or None if the key is missing or wrong. Constant-time comparison against every configured key."""
    if settings.auth_disabled:
        return "anonymous"
    token = x_api_key or (authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None)
    if not token:
        return None
    found = None
    for key, name in settings.api_keys.items():
        if secrets.compare_digest(token.encode(), key.encode()):
            found = name
    return found

class RateLimiter:
    """Token bucket per client. allow() returns (ok, seconds_until_next_token)."""
    def __init__(self, per_min: float, burst: int, clock=time.monotonic, max_clients: int = 10_000):
        self.rate, self.burst, self.clock, self.max_clients = per_min / 60.0, float(burst), clock, max_clients
        self.buckets: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def allow(self, client: str) -> tuple[bool, float]:
        now = self.clock()
        with self.lock:
            tokens, last = self.buckets.get(client, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if len(self.buckets) >= self.max_clients and client not in self.buckets:
                self.buckets.pop(next(iter(self.buckets)))                      # bound memory: drop the oldest client
            if tokens >= 1.0:
                self.buckets[client] = (tokens - 1.0, now); return True, 0.0
            self.buckets[client] = (tokens, now)
            return False, (1.0 - tokens) / self.rate if self.rate > 0 else 60.0

class Overloaded(Exception):
    def __init__(self, reason: str, retry_after: int = 5):
        super().__init__(reason); self.reason, self.retry_after = reason, retry_after

class Admission:
    """At most max_inflight requests run; at most max_queue wait, each for at most queue_timeout_s; everything else is shed immediately.
    The queue is FIFO and slots are handed straight to the oldest waiter, so a newly arrived request cannot jump the queue (a plain
    semaphore lets late arrivals barge ahead and starves waiters until they time out). Size it so that queue_timeout_s is at least
    (max_queue + 1) x the worst-case answer time, or waiters will time out while the queue is still doing its job."""
    def __init__(self, max_inflight: int, max_queue: int, queue_timeout_s: float):
        self.max_inflight, self.max_queue, self.timeout = max_inflight, max_queue, queue_timeout_s
        self.inflight, self.queue, self.lock = 0, deque(), threading.Lock()
        self.ewma_s = None                       # smoothed service time, used for Retry-After
        self._local = threading.local()

    @property
    def waiting(self) -> int:
        return len(self.queue)

    def retry_after(self) -> int:
        return max(1, math.ceil((self.ewma_s or 10.0) * (len(self.queue) + 1)))

    def __enter__(self):
        with self.lock:
            if self.inflight < self.max_inflight and not self.queue:
                self.inflight += 1; self._local.t0 = time.monotonic(); return self
            if len(self.queue) >= self.max_queue:
                raise Overloaded("queue full", retry_after=self.retry_after())
            ev = threading.Event(); self.queue.append(ev)
        got = ev.wait(self.timeout)
        with self.lock:
            if not got:
                try:
                    self.queue.remove(ev)
                except ValueError:
                    got = True                   # a finishing request handed us the slot at the very moment we timed out: keep it
            if not got:
                raise Overloaded("waited too long in the queue", retry_after=self.retry_after())
        self._local.t0 = time.monotonic()
        return self

    def __exit__(self, *exc):
        took = time.monotonic() - getattr(self._local, "t0", time.monotonic())
        with self.lock:
            self.ewma_s = took if self.ewma_s is None else 0.7 * self.ewma_s + 0.3 * took
            if self.queue:
                self.queue.popleft().set()       # hand the slot to the oldest waiter; inflight stays the same
            else:
                self.inflight -= 1

_URL = re.compile(r"https?://[^\s)\]>\"'`,;]+", re.I)

def corpus_hosts(texts) -> set:
    return {urlparse(u).hostname.lower() for t in texts for u in _URL.findall(t) if urlparse(u).hostname}

def guard_urls(text: str, allowed: set) -> tuple[str, list]:
    """Replace every link whose host is not on the allowlist (exact match or subdomain of an allowed domain). Returns (text, removed urls)."""
    removed = []
    def check(m):
        url = m.group(0); host = (urlparse(url).hostname or "").lower()
        if any(host == a or host.endswith("." + a) for a in allowed):
            return url
        removed.append(url); return "[link removed]"
    return _URL.sub(check, text), removed
