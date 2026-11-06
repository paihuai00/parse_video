# Error Handling

Expected failures use `AppError` from `app/errors.py`. It carries a stable code, HTTP status, retryability, an internal diagnostic, and an optional `Retry-After` value. Public messages come from the central `MESSAGES` mapping.

Parser and service modules raise domain errors and do not construct HTTP responses. `app/api/error_handlers.py` converts domain, Pydantic, framework 404/405, and unexpected errors into the `ParseError` envelope.

## Required Patterns

- Preserve distinct login, access challenge, upstream rate limit, missing-note, timeout, parse, and missing-media outcomes.
- Use `NOTE_NOT_FOUND` only with explicit upstream evidence.
- Let caller cancellation propagate through cleanup.
- Unexpected exceptions return `INTERNAL_ERROR`; responses never include diagnostics or tracebacks.

## Forbidden Patterns

- Returning FastAPI's default validation, 404, or 405 body.
- Returning upstream HTML, signed URLs, cookies, request headers, or stack traces.
- Treating an upstream login page as this service's `UNAUTHORIZED` response.

## Xiaohongshu Status Redirects

Validate the status destination's authority using the same URL primitives before classifying a redirect from an already validated note. Exact same-origin `/login` is an upstream login outcome; exact `/404` is a conservative upstream status, not proof that a note is missing. A narrow internal typed status error permits the bounded anonymous mobile strategy while preserving the public envelope. Do not trigger fallback by matching arbitrary diagnostic strings or broad public `INVALID_URL`/`PARSE_FAILED` codes. Invalid authority, arbitrary paths or unsafe DNS remain rejected and must not be retried by another strategy.

An independently observed HTTP 200 with exactly zero body bytes on a validated
detail is a typed acquisition failure, not malformed JSON. It may consume the
same single mobile fallback using the full validated detail URL and bound note
identity. Both strategies share the original two attempts, deadline and redirect
budget. A mobile/repeated empty detail is retryable `UPSTREAM_BAD_RESPONSE`.
Nonempty missing-state/invalid-JSON pages remain `PARSE_FAILED` without fallback;
short-link emptiness cannot select another strategy. Mobile image motion is only
returned when both a legal detail still and a positively identified paired MP4
exist; incomplete or unsupported motion cannot become static-only success.
