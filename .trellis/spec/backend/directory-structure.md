# Directory Structure

## Layout

```text
app/
  main.py                 # app factory and HTTP request boundary
  config.py               # validated environment configuration
  errors.py               # stable domain error taxonomy
  models.py               # internal immutable records and public schemas
  api/                    # routes, authentication, error translation
  parser/                 # URL/DNS policy, transport, state reader, media normalization
  services/               # cache, rate limit, admission, request coalescing
tests/                    # deterministic offline behavior and contract tests
scripts/probe.py          # explicit deployed-service real-network probe
deploy/                   # additive deployment examples
```

## Module Ownership

- Routes validate HTTP input and build caller-specific response metadata. They do not inspect upstream dictionaries.
- `ParseService` composes limits, cache, in-flight work, the client, and parser functions.
- `parser/url_rules.py` owns upstream page URL and DNS rules.
- `parser/media.py` owns CDN URL and media selection rules.
- Media URLs are accepted only from the exact CDN hosts backed by sanitized evidence and
  regression tests. A new `xhscdn.com` subdomain is not implicitly trusted.
- A video candidate needs positive MP4 evidence from its format, MIME type, or path; an
  otherwise ambiguous stream is not labeled as MP4.
- Internal parsed results are frozen dataclasses. Pydantic models are used at the HTTP boundary.
- Shared limits come from `Settings`; stable public messages and codes come from `errors.py`.
- Coalesced callers share the same four-place waiter budget as distinct queued parses. DNS,
  redirects, transport, and parsing all consume the original total deadline.

Use snake_case module names and keep new behavior in the narrowest owning layer.
