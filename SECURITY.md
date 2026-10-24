# Security policy

## Status of this project

This is a research prototype. It includes security controls for the CAG service (API keys, per-client rate limits, a bounded request queue, output URL and PII redaction, automatic recovery when the model backend dies) and a written record of what was tested, in [docs/12-security-tests.md](docs/12-security-tests.md). It has **not** been independently audited, and it is not meant to be exposed to the internet as it is.

Known limitations (documented, so not vulnerabilities to report on their own):
- No TLS: put the service behind a TLS-terminating proxy.
- Rate limits, queues and API keys are held per process; running several replicas gives each its own limits.
- Facts planted in the corpus are repeated as truth; the defence is controlling what enters the corpus.
- PII redaction is pattern-based: it does not catch names, addresses or free-text secrets.
- `CAG_AUTH_DISABLED=1` turns authentication off and is for local experiments only.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private vulnerability reporting (the repository's **Security** tab, then **Report a vulnerability**). If that option is not available, open an issue that only asks for a private way to contact the maintainer, without any details of the problem.

Helpful details: the version or commit, what you did, what you expected, what happened, and whether you needed credentials. Reports about the items listed above are welcome as hardening suggestions but will be treated as known limitations.

## Supported versions

Only the latest commit on `main`.

## Secrets

No real credentials belong in this repository. `.env` is ignored; `.env.example` holds placeholders only. Test fixtures use published fake values (for example AWS's documented example key and standard test card numbers). If you find a real secret, report it privately as above.
