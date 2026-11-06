# Read-only Xiaohongshu server diagnosis

Scope: verify current deployment, inspect bounded recent logs, reproduce the user-provided successful sample with refresh=true, compare configured public ingress, record sanitized evidence. No product code/configuration edits, service restarts, deployment changes, TLS weakening, dependency or allowlist changes.

Acceptance: report deployment identity, HTTP outcome, request ID and timing, distinguish observed facts from inferred causes, and identify missing evidence. Do not persist credentials, signed URLs, share tokens, HTML, or full configuration.
