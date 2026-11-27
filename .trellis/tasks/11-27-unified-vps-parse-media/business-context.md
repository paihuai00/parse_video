# Business context for unified parsing and media delivery

- Phase: start. Run: cf093096-69b4-4615-938e-c33ce44165ec. Project: /Users/didi/ai_project/parse_video.
- Baseline: main@3791b5ae11154f0862b0682f732600c721acd058; scoped product code has no initial staged/unstaged/untracked changes. Existing Trellis/config/journal changes are unrelated and must be preserved.
- Current API: unified /api/v1/parse and legacy XHS route. XHS uses self-acquisition; native Douyin supports ordinary video/static images and rejects motion-bearing images.
- Client baseline: Douyin uses bugpk /douyin -> /dyjx -> ifphp -> /short_videos; Bilibili uses /bilibili -> /short_videos; generic uses /short_videos. These clients move to VPS dispatch. Native Douyin is not a new fallback.
- Existing internal cache stores original media URLs. Publication must sign fresh VPS URLs per response and atomically cover image/video/motion/cover/avatar addresses without mutating that cache.
- Shared models support nested motion video. Unified provider identity may be absent; do not fabricate upstream IDs. Preserve legacy XHS strictness.
- Constraints: one client parse endpoint, no client provider routing, no extra ticket POST, no direct-CDN fallback, bounded media streaming, validated/pinned public connections, reusable expiring credentials, no persistent media storage, one worker.
- Source references: app/api/routes.py; app/parser/adapters.py; app/parser/douyin/media.py; app/models.py; app/services/parse_service.py; app/services/cache.py; .trellis/spec/backend/service-contract.md; paired client task design.
- History checked: 3791b5a feat(douyin): resolve videos through mobile share pages; f9dd538 fix: support exact regional Live Photo video hosts; 256d8db fix: accept exact rednote desktop image host; fd9d9d3 fix: handle rednote state and empty detail responses.
- Verification limits: current source and offline evidence only; VPS provider/media reachability and WeChat real-device behavior are unverified.
- Deployment, Git writes and business activation are not authorized by implementation approval. Main session owns business-memory lifecycle; implement/check workers only consume this context.


## Verified implementation finish

- Main-session final verification: 489 pytest tests, Ruff format/check, Mypy (33 source files), compileall, OpenAPI and scoped whitespace checks passed.
- Four-platform actual ASGI/client contract check passed, including motion, cover and proxied avatar.
- Current project-owned knowledge is synchronized in docs/unified-vps-media.md and the backend service contract; no additional duplicate business_docs library was created.
- Deployment, live providers/CDNs, Nginx runtime validation and WeChat devices remain release gates. No task archive, journal or Git writes were performed.
