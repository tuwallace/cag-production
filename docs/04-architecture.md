# 04. Architecture

## Components

```
            ┌────────────────────── offline / CI ──────────────────────┐
 raw docs → │ clean → normalize → assign doc IDs → order → assemble     │ → corpus-vX.txt
            │ token count check → content hash → eval gate              │   + manifest.json
            └───────────────────────────────────────────────────────────┘
                                         │ publish (immutable, hash-named)
                                         ▼
 client → [Gateway: auth, rate limit] → [CAG service] → [LLM + cache layer]
                                            │   ▲              │
                                            │   └ cache warmer ┘
                                            └→ metrics / traces / logs
```

## Prompt layout (the most important design decision)

```
[1] tools / schemas            ← static   ┐
[2] system instructions        ← static   │ cached prefix
[3] corpus (with doc IDs)      ← static   ┘ ← cache breakpoint here
[4] conversation history       ← grows
[5] current user question      ← changes every request (never cached)
```

Rule: everything above the breakpoint must be **byte-identical** across requests.
No timestamps, request IDs, user names or randomized ordering above it.

## Request flow

1. Gateway authenticates and validates the request.
2. Service builds `prefix + history + question`.
3. LLM server/API checks the prefix cache: hit -> prefill only the suffix; miss -> prefill everything and write the cache.
4. Response streams back with citations (doc IDs).
5. Service records cache-read vs cache-write tokens, latency, and answer metadata.

## Cache lifecycle

| Event | Action |
|---|---|
| Deploy / new corpus version | Publish new immutable version, warm it, then shift traffic (blue/green) |
| TTL approaching (API path) | Keepalive request, or use the 1-hour TTL for low-traffic corpora |
| Idle replica (self-host) | Re-warm on startup before readiness probe passes |
| Corpus update | Treat as a release: rebuild, eval, warm, cut over, keep the old version for rollback |
| Model change | Invalidates everything; re-warm and re-evaluate |

## Hybrid extension (optional)

If part of the knowledge is large or volatile: cache the stable core, and retrieve the volatile
portion with `../helpdesk-rag`-style retrieval, appending results **after** the breakpoint.
