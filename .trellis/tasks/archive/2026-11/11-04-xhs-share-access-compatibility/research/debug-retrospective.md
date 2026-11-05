# Bug Analysis: status redirects and mobile note layout

## 1. Root Cause Category

- B, cross-layer contract: upstream acquisition reused caller note-path validation for status redirects; an upstream error route became public INVALID_URL before page classification could run.
- D, coverage gap: direct login/404 classification tests did not exercise short link→detail→status chains or a full mobile API result.
- E, implicit assumption: successfully acquired note state and image candidates were assumed to always use the desktop layout.

## 2. Why Surface Fixes Would Fail

No abandoned production fixes were applied. Probe evidence showed that changing input paths or using the desktop long link did not restore desktop acquisition. Changing the fingerprint alone obtained mobile HTML but still failed at desktop-only selection; changing selection alone would still miss H5 detail image candidates. A logged-in success and visible login modal did not establish that all anonymous acquisition was impossible.

## 3. Prevention Mechanisms

| Priority | Mechanism | Action | Status |
| --- | --- | --- | --- |
| P0 | Typed acquisition boundary | Only exact safe status redirects select fallback; public errors are not retry selectors | Implemented |
| P0 | Shared resource budget | Attempts/redirects/Deadline span strategies; negative tests cover resets, unsafe targets and cancellation | Verified offline |
| P0 | Layout-aware normalization | Exact ID/error selection plus every mobile image slot/detail/motion guard | Verified offline and authorized local static sample |
| P0 | Full chain tests | Both API routes, shared cache/fresh caller metadata and no partial success | Verified offline and locally |
| P1 | Code-spec capture | Service contract and error-handling specs contain signatures, error matrix, tests and wrong/correct examples | Updated |
| P1 | Separate deployment evidence | VPS acquisition, candidateAPI/media and caller reads are distinct gates | VPS full acceptance pending |

## 4. Systematic Expansion

Do not infer semantic deletion from error-page paths or undocumented upstream numbers. Keep unsafe-input rejection independent from strategy selection. Do not inherit a legacy skip-invalid-images normalizer into a branch promising complete images. Fresh context/session and exact target identity matter more than an HTTP200 or rendered preview.

## 5. Knowledge Capture

Concrete rules are in .trellis/spec/backend/service-contract.md and error-handling.md; execution and remote gates are in implement.md and docs/vps-xhs-mobile-acceptance.md. Login-modal classification, mobile motion/video and new provider/browser strategies remain separately evidenced scope rather than speculative additions to this fix.
