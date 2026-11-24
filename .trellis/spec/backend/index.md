# Backend Development Guidelines

## Overview

This repository is a Python 3.12 FastAPI service without a database, frontend, or distributed runtime. Xiaohongshu uses a bounded HTTP client. Douyin uses anonymous mobile share pages for ordinary videos and sandboxed Chromium behind a loopback CONNECT proxy for image works and eligible fallbacks. The public contract lives in `docs/openapi.json`.

## Guidelines Index

| Guide | Description | Status |
| --- | --- | --- |
| [Directory Structure](./directory-structure.md) | Application layer ownership | Active |
| [Database Guidelines](./database-guidelines.md) | Persistence scope | Not applicable in v1 |
| [Error Handling](./error-handling.md) | Domain errors and public envelopes | Active |
| [Quality Guidelines](./quality-guidelines.md) | Required checks and tests | Active |
| [Logging Guidelines](./logging-guidelines.md) | Secret-safe request logging | Active |
| [Service Contract](./service-contract.md) | Cross-layer API, transport, parsing, limits, errors, and deployment contract | Active |

All backend documentation is written in English. Update these guides only with patterns present in the codebase.
