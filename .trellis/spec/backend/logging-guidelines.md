# Logging Guidelines

Application logs go to standard output. The request middleware emits one compact JSON event with request ID, method, path, status, and duration. The path never includes its query string.

Expected domain errors are represented by their HTTP result. Unexpected errors log only request ID and exception type.

## Never Log

- `X-API-Key`, cookies, account credentials, or browser state
- complete share URLs or query values such as `xsec_token`
- media URLs, signatures, upstream page bodies, or response bodies
- local exception messages that may contain request values

Use the request ID to correlate application and proxy logs. `/healthz` never contacts upstream.
