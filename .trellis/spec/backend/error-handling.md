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
