# Backend Development Guidelines

## Overview

This repository is a Python 3.12 FastAPI service. It has no database, frontend, or distributed runtime. Xiaohongshu uses a bounded HTTP client; Douyin uses a per-parse, anonymous, sandboxed Chromium process behind a loopback CONNECT proxy. Public behavior is anchored by `docs/openapi.json`; parsing and upstream details stay behind service and parser boundaries.

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
