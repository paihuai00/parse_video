# Logging Guidelines

Application logs go to standard output. The request middleware emits one compact JSON event with request ID, method, path, status, and duration. The path never includes its query string; media paths are replaced with `/api/v1/media/:resource` to hide capability IDs.

Expected domain errors are represented by their HTTP result. Unexpected errors log only request ID and exception type.

## Never Log

- `X-API-Key`, cookies, account credentials, or browser state
- complete share URLs or query values such as `xsec_token`
- media URLs, signatures, upstream page bodies, or response bodies
- local exception messages that may contain request values

Use the request ID to correlate application and proxy logs. `/healthz` never contacts upstream.

Media completion events describe actual sent bytes/outcome and cleanup separately from header-ready request timing. Nginx access logs must omit URI/query; its normal media error log is disabled because upstream failures can print credential URLs. Keep safe request-ID telemetry; inspect outer ingress logs before release.
