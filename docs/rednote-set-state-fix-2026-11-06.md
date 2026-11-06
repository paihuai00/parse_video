# Bounded rednote Set serialization compatibility

## Evidence and scope

The VPS report identifies `originalCommentIds: new Set([...])` inside an otherwise
JSON-like `window.__INITIAL_STATE__` assignment on a 200 rednote desktop page.
The original page was not provided or retained locally. All added fixture data
is explicitly synthetic and does not claim to reproduce the full VPS page.

Before changes, a synthetic assignment with a Set array, nested objects/arrays
and escaped string delimiters was extracted completely by `extract_initial_state`.
Decoding then failed with `PARSE_FAILED`, `initial state is not valid JSON`, caused
by `JSONDecodeError`. Extraction was not the primary cause.

## Implementation plan and contract

1. Keep balanced, string/escape-aware extraction and all existing resource bounds.
2. Extend the value scanner to recognize only exact `new Set(array)` syntax in
   value position outside double-quoted strings. Permit ASCII JSON whitespace
   between tokens; require precisely one array argument and its closing `)`.
3. Represent that data as a JSON array, preserving order, values and duplicates;
   do not construct a Python/JavaScript Set or execute constructor semantics.
   Nested supported Set values follow the same rule and existing array depth bound.
4. Keep value-token `undefined` conversion and all quoted keys/values unchanged.
   Let the JSON decoder validate the normalized document. Reject other constructors,
   calls, accessors, comments, spread, malformed wrappers and arbitrary expressions.
5. Cover extraction, successful decoding, string protection, malformed syntax,
   exact size/depth/node boundaries, and both API routes on a synthetic regional
   desktop chain, including an existing Live Photo MP4 pair.
6. Run all required offline checks and optionally probe the three authorized live
   inputs in an independent process. Local live success alone is not evidence that
   the reported rednote serialization has been exercised.

The initial Set syntax repair changes no URL/client strategy, fallback condition,
media selection, dependency or public schema. A later user-reported regression
exposed a separate zero-byte detail-response case, documented with its bounded
acquisition and complete mobile Live Photo repair in
`empty-detail-response-fix-2026-11-06.md`. No JavaScript evaluation is used.

## Validation

- Implemented only the state value normalization extension. The size boundary
  now rejects a source span one character beyond the configured cap; the previous
  comparison allowed that extra character. Depth/node limits are unchanged.
- Before implementation: the synthetic extraction test passed, while the fixture
  decoding test and four regional API variants failed as expected (JSON decoding
  failure / HTTP 502). After implementation they pass using `chrome136` without
  mobile retries, for both static and paired Live Photo results.
- Added 50 offline cases: extraction plus decoding, supported/nested Set arrays,
  value `undefined`, preservation of strings/escapes/keys, malformed and unknown
  syntax, ASCII constructor whitespace, source size/depth/node boundaries, and
  success/failure envelopes through both API routes. No captured page is claimed.
- Full offline suite: 286 passed. Ruff format/check passed (46 files), Mypy passed
  (26 source files), compilation, OpenAPI JSON syntax and diff whitespace checks
  passed under Python 3.12.16 with curl_cffi 0.13.0.
- Real requests were made through a new independent FastAPI/ASGI application
  using the modified source, default settings and production parser/client. No
  existing service was restarted. Each request used `refresh=true`, and all were
  cache misses; no input IDs/tokens or signed output URLs were persisted.

  | Authorized sample role | UTC (2026-11-06) | HTTP | Images / Live Photos / videos | Acquisition |
  | --- | --- | --- | --- | --- |
  | Reported failure | 08:43:44 | 200 | 1 / 0 / 0 | chrome136, short 302 → xiaohongshu detail 200 |
  | Static regression | 08:43:44 | 200 | 1 / 0 / 0 | existing safe status redirect → safari184_ios mobile detail 200 |
  | Live Photo regression | 08:43:45 | 200 | 1 / 1 / 0 | chrome136, short 302 → xiaohongshu detail 200 |

  These real local probes did not reach rednote and do not establish VPS recovery.
  The synthetic regression is the deterministic evidence for Set syntax support.
- Initial implementation performed no Git writes, deployment, configuration
  changes, service restart or new Trellis task. The pre-existing
  `.trellis/config.yaml` edit remains untouched.

### Authorized local HTTP service restart and acceptance

At the user's subsequent request, restarted only the existing development Uvicorn
service to load this change, retaining its interpreter, working directory, default
`chrome136` settings, loopback binding and single worker. New PID 36469, listening
on `127.0.0.1:8000`; health returned 200. No VPS or Git write operations.

Actual HTTP requests to the legacy route on 2026-11-06, all with `refresh=true`:

| Sample role | UTC | HTTP | Images / Live Photos / videos | Cache | Request ID |
| --- | --- | --- | --- | --- | --- |
| Reported failure | 08:49:31 | 200 | 1 / 0 / 0 | miss | 863b9483-6bc2-43e4-8263-747c99252d5a |
| Static regression | 08:49:31 | 200 | 1 / 0 / 0 | miss | 2f160ae3-2411-42de-8d7e-8077ddf667a4 |
| Live Photo regression | 08:49:32 | 200 | 1 / 1 / 0 | miss | e3d69fd0-dcb1-4f35-b19c-56514ffa56b5 |

All three request IDs matched successful application log events. The service
remains running for the user's manual acceptance before any Git submission or
VPS rollout. Local live availability still does not replace the synthetic Set
regression or real VPS acceptance.

## VPS verification after separately authorized deployment

1. Compare running-container source hashes to the delivered source for
   `app/parser/state_reader.py`; record actual image ID and Python/curl_cffi versions.
   An unchanged image tag or repository HEAD alone does not prove running content.
   Validated local file SHA-256:
   `e2bfd1d1980f55ae980b47c0fe3c2ef6ab52909882641b78711b6aa336d4d1c7`.
2. Run the explicitly synthetic in-container regression (does not access upstream):

   ```sh
   docker compose exec -T api python - <<'PY'
   from app.parser.state_reader import decode_initial_state
   sample = 'window.__INITIAL_STATE__={"originalCommentIds":new Set(["synthetic"]),"v":undefined,"text":"new Set([])"}'
   assert decode_initial_state(sample) == {
       "originalCommentIds": ["synthetic"], "v": None, "text": "new Set([])"
   }
   print("synthetic Set decoding: ok")
   PY
   ```

3. Replay each user-authorized failure/static/Live Photo sample with `refresh=true`
   through loopback, then public `POST /api/v1/xiaohongshu/parse`, using the existing
   production credential privately. Record UTC, HTTP status, request ID, error code,
   cache hit and media counts, not full responses or signed media URLs.
4. For the failure sample, trace only strategy, exact host, path category and status.
   If the response again comes from rednote with Set syntax, verify decode, target
   selection and normalization succeed using `chrome136` without a new fallback.
   Preserve normal static results and paired Live Photo motion; do not equate
   health 200 or local success on a different page variant with VPS acceptance.
5. If another failure remains, report its precise stage and safe diagnostic. Do not
   broaden this grammar, switch global strategy, or deploy follow-up changes silently.
