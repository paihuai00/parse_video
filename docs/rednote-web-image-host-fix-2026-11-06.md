# Exact rednote desktop image host compatibility

## Baseline and evidence boundaries

Baseline: `fd9d9d3691def33d88abf6f9e6eb8b9c9cc6a705`.
The only pre-existing working-tree change was `.trellis/config.yaml`; it is
preserved. No new Trellis task, Git write, deployment, service restart or production
configuration change is performed by this repair.

### VPS-confirmed static-image failure (user-supplied evidence)

The user's VPS diagnostic at 2026-11-06 09:37:37 UTC established:

- A nonempty `www.rednote.com` desktop detail decoded successfully and selected
  the requested note with `mobile=False`.
- The single static image's `urlDefault`, `urlPre`, `WB_DFT` and `WB_PRV` candidates
  used exact `sns-web-i10.rednotecdn.com` with original HTTP scheme.
- Every candidate was rejected by the baseline media host policy, ending with
  `MEDIA_NOT_FOUND`, `body images are missing`. This is an image-host omission,
  not the preceding Set-serialization or zero-byte-response failures.

This report was not independently reproduced from a local rednote response. No
real HTML, note ID, share token, media path or signed URL is persisted here.

### VPS Live Photo evidence is separate

The VPS Live Photo sample decoded and selected its target but failed with
`declared Live Photo still image is missing`. Its actual still-image and paired
MP4 hosts have not been inspected in the supplied report. It is **not established**
that this sample uses the new host or that this repair resolves that failure.

## Minimal repair

1. Add only exact `sns-web-i10.rednotecdn.com` to `IMAGE_ONLY_HOSTS`.
2. Add keyword-only `kind="image"`/`"video"` context to the existing URL normalizer.
   Default image normalization accepts the new host; video master and backup
   selection explicitly uses `kind="video"` and rejects this image-only addition.
   Keep all existing shared media hosts and the `sns-i[0-9]+` pattern unchanged.
3. Preserve HTTP-to-HTTPS normalization, query values, credentials/port/scheme
   checks, image candidate priority, MP4 evidence and paired motion ownership.
   Client acquisition, state grammar, identities, DNS/TLS/IP binding, defaults,
   fallback conditions, attempts, redirects and Deadline are unchanged.

No dependency, public API schema or production configuration change is required.

## Deterministic synthetic coverage

`tests/fixtures/synthetic_rednote_web_image_note.html` is explicitly synthetic,
not a captured VPS page. It combines `new Set([...])`, value `undefined`, an
unrelated first note and a separately keyed target note with the reported exact
image host. All paths, identifiers and query strings in this fixture are synthetic.

- Before repair: eight selected parser/API cases failed as expected with
  missing-media errors, including `urlDefault`, `WB_DFT`, both API routes and a
  hypothetical Live Photo pair using the new still host.
- After repair: target selection returns one image and no top-level videos;
  `urlDefault` wins when present, while `WB_DFT` works when it is absent. Both HTTP
  paths become HTTPS and retain the synthetic query, without a mobile retry.
- Unsafe suffixes/lookalikes, unobserved `sns-web-i` numbers, Unicode lookalikes,
  userinfo, abnormal ports and unsupported schemes remain rejected.
- The new image host cannot supply a normal-video or Live Photo MP4, even with
  explicit MP4 metadata, as either master or backup. An existing supported video
  backup still works; mobile preview-only protection remains intact.
- Synthetic complete Live Photo pairing succeeds with a new-host still and an
  already allowed video host. This is compatibility coverage, **not evidence of
  the real VPS Live Photo sample's static or video host**.

Targeted media/pipeline suite: **120 passed**. Full offline suite: **338 passed**
(29 additional cases). Ruff format/check: 46 files passed. Mypy: 26 source files
passed. Compilation, OpenAPI JSON syntax and diff whitespace checks passed under
Python 3.12.16 with curl_cffi 0.13.0.

## Local real-request coverage

One request per authorized sample was made through a new independent local
FastAPI/ASGI app using the changed source and the existing local authentication,
the legacy API path and `refresh=true`. The existing listening service was not
restarted or used to claim that it had loaded the patch. Only safe request metadata
and counts were emitted; upstream bodies and media addresses stayed in memory.

| Sample role | UTC (2026-11-06) | HTTP | Request ID | Cache | Images / Live Photos / videos | rednote |
| --- | --- | --- | --- | --- | --- | --- |
| Reported regional static failure | 09:46:55 | 200 | 284379de-3f67-4013-9a97-fb3de293c7a7 | miss | 1 / 0 / 0 | Not covered |
| Static regression | 09:46:55 | 200 | cf9e31c3-19df-4bc3-8077-8ab0525fe5ed | miss | 1 / 0 / 0 | Not covered |
| Live Photo regression | 09:46:56 | 200 | 6f85ca84-85c4-43ba-a463-09c40fd43da2 | miss | 1 / 1 / 0 | Not covered |

All three local requests bypassed rednote, so none validates the real regional
image branch. The synthetic tests provide deterministic coverage of that branch.
No additional real sample or repeated request was used.

## Source SHA-256

```text
app/parser/client.py
84cfcfc6866bb1a99d329cc3cdc9b549226b61ad875d0c42b50199fe109d722d

app/parser/media.py
b833010a0ceac66328165e590dfb2b3b8853292369286261f343034e8fcc1320

app/parser/state_reader.py
e2bfd1d1980f55ae980b47c0fe3c2ef6ab52909882641b78711b6aa336d4d1c7
```

Only `media.py` changes among these files; client and state-reader hashes match
the baseline. The existing service must load the delivered source to use the fix.

## VPS acceptance after separately authorized rebuild

1. Preserve the current image ID/rollback image and configuration. Once source
   synchronization and deployment are authorized, build from the reviewed source:

   ```sh
   docker compose config --quiet
   docker compose build api
   docker compose up -d --no-deps --force-recreate api
   docker compose ps
   ```

   Check the actual running image and imported file paths; compare the three
   hashes above inside that container. Do not trust just a reused image tag or
   repository HEAD. No build/deployment command was run during this local repair.

2. Run an explicitly synthetic, offline in-container check (the image has `app`,
   not the repository's tests/fixtures):

   ```sh
   docker compose exec -T api python - <<'PY'
   import json
   from app.parser.media import normalize_media_url, normalize_note
   from app.parser.state_reader import decode_initial_state, select_note_layout

   note_id = "a" * 24
   image_url = "http://sns-web-i10.rednotecdn.com/synthetic.jpg"
   note = {"type": "normal", "imageList": [{"urlDefault": image_url}]}
   source = (
       'window.__INITIAL_STATE__={"ids":new Set(["synthetic"]),"cursor":undefined,'
       '"note":{"noteDetailMap":{"' + note_id + '":{"note":'
       + json.dumps(note) + '}}}}'
   )
   state = decode_initial_state(source)
   selected = select_note_layout(state, note_id)
   result = normalize_note(note_id, selected.payload)
   assert state["ids"] == ["synthetic"] and state["cursor"] is None
   assert not selected.mobile and len(result.images) == 1 and not result.videos
   assert result.images[0].url == image_url.replace("http:", "https:", 1)
   assert normalize_media_url(image_url, kind="video") is None
   print("synthetic regional image compatibility: ok")
   PY
   ```

3. Replay the same three user-authorized inputs once each with `refresh=true`,
   first through loopback and then the existing Nginx/public entry on the correct
   `POST /api/v1/xiaohongshu/parse` path, using the existing production key privately.
   Record UTC, HTTP status, request ID, cache state and media counts. For the static
   failure sample, require one ordered image and no top-level videos.

4. In a bounded independent diagnostic, verify that an actual rednote desktop
   response decodes and selects the requested note, and that `urlDefault`/`WB_DFT`
   candidates on the exact new host are accepted and normalized to HTTPS. A result
   obtained from a different host/strategy is not regional acceptance. Keep default
   chrome136; no generic parse-error fallback or grammar expansion is needed.

5. **Pending image readability:** this repair did not fetch an actual image from
   the new host. On VPS, acquire an authorized candidate only in memory, validate
   all DNS answers as public, pin vetted IPs, verify TLS and disable redirects and
   environment proxies. Read at most bytes 0–1023 with an enforced body cap, even
   if Range is ignored; check status, content type and a matching image header.
   Never save/download the full media or print its signed URL. If the safe toolchain
   cannot enforce these bounds, leave this check pending rather than use an
   unconstrained request. HTTP-to-HTTPS normalization alone proves no readability.

6. **Pending real Live Photo pairing:** first inspect its actual static candidates
   and paired MP4 host/shape without exposing addresses or signatures. Do not infer
   these from the static sample. Require the full still and supported MP4 at
   `images[].live_video`, with no static-only downgrade and no top-level video.
   An unknown still/video host or missing pair must remain an explicit failure.

7. Separate any remaining acquisition, Set decoding, identity/selection, media URL
   acceptance and file-readability failures. Report evidence and preserve rollback
   capability; do not automatically broaden hosts, change production settings or
   commit/push/deploy another repair.
