# KYAPTURE security report (Task 7: chunks 7-A to 7-E)

Date: 2026-10-07. Branch `feature/landing-page-redesign`. This is the summary; the evidence lives in:

- [docs/qa-7e/results.md](qa-7e/results.md): suite, browser regression, real-photo upload check, and the final status of
  **every** SEC finding, checklist item and 7-x debt row (with commits).
- [docs/security/threat-model.md](security/threat-model.md) (findings SEC-01..31, chunk sections 9-13),
  [attack-surface.md](security/attack-surface.md), [security-checklist.md](security/security-checklist.md),
  [secrets.md](security/secrets.md): updated in 7-E to match the code; nothing there claims a control that does not exist.
- `docs/KYAPTURE_PRODUCTION_DEBT.md`: every open gap with its owning chunk.

Chunk commits: 7-A `8608e04` (tenancy), 7-B `bdca0e9` (downloads, throttles, headers, uploads), 7-D `10470f3` + `ce63161`
(client deterrence), 7-C `a2b214f` + `9d7e039` (password reset, session revocation). 7-E changed no application code.

## 1. What was fixed

| Area | Fixed | Chunk |
|---|---|---|
| Throttle identity | Throttles and stored client IPs no longer follow a client-sent `X-Forwarded-For` (`REST_FRAMEWORK['NUM_PROXIES']`, one IP helper); counts shared in Redis across workers (before: 9 of 20 logins passed a 5/min limit with 2 workers, after: exactly 5) | 7-B |
| Gallery gates | Wrong password/PIN lockout per client (5 / 15 min) and per gallery (50 / h, photographer notified); contact allow-list needs an emailed one-time code; any password change on any path revokes unlock tokens; ready/file links die when the password or PIN changes | 7-A, 7-B |
| Favorites | A list belongs to the browser that made it; a typed email can no longer read, rename, delete or add to someone else's list | 7-A |
| Originals stay private | Video stream serves the playback copy only; non-READY downloads refused and Web Size never falls back to the original; private keys get a 128-bit random part; dev `/media/` serves public derivatives only, private files need a signed 1-hour URL; owner `original_url` is a 1-hour signed URL | 7-B |
| Public derivative URLs | Closing a gallery (password added/changed, unpublished) moves every public file to a new random path; old URLs 404 (re-checked in the 7-E browser run) | 7-B |
| Tokens at rest | Unlock tokens and password-reset tokens stored as SHA-256 | 7-B, 7-C |
| Accounts | Per-account login limit, register limit, token-refresh limit per user; admin login lock; hashes/tokens hidden in admin; `JWT_SIGNING_KEY`, `SECRET_KEY_FALLBACKS` and a rotation runbook | 7-B |
| Password reset and sessions | Reset/change/logout-all/admin password change revoke access tokens at once (`token_version`), 30-minute single-use newest-only links in a URL fragment, per-address and per-client limits, no timing or uid oracle, "password changed" email, one password policy | 7-C |
| Uploads and workers | 413 / storage-full 403 from headers before the body is read; timeouts on every ffmpeg/ffprobe/cjpegli call and the photo task; plan edge cases (lapsed plan, video minutes race) | 7-B |
| Location privacy | Photos fail closed (EXIF GPS, XMP GPS, PNG eXIf); video location remuxed out; derivatives carry no metadata. 7-E: 0 of 103 real JPEGs refused | 7-B, 7-E check |
| Build and headers | `backend/.dockerignore` (the old image held `/app/.env`); Google font hosts out of the CSP; stale CSP comment | 7-B |
| Casual saving | Right-click, drag and long-press callout blocked on client media (deterrence only, never called protection) | 7-D |
| Errors | Malformed ids and oversized `client_uid` answer 400/ignored instead of 500 | 7-A |

## 2. What was deferred, and why

| Gap | Why not now | Owner (debt row) |
|---|---|---|
| Bearer tokens in query strings for `<a href>` downloads and `<video src>` | **Accepted in 7-E.** A fix needs short-lived per-file grants from a new API, changing every gallery download and video play. Acceptable because Referrer-Policy keeps tokens on their origin (SPA `strict-origin-when-cross-origin`, API `same-origin`), file-granting links live 1-2 h, the 30-day unlock token is hashed at rest and dies on a password change, and the production log format drops query strings. Residual: a shared computer's history keeps the unlock token up to 30 days | accepted (133) |
| MFA for staff; network restriction on `/admin/` | Needs an MFA package and a deployment decision; the admin login lock is in place | 13-C, 15-A (90) |
| Email verification at sign-up | Decision made (verify before publishing or emailing third parties); touches 26 publish paths and 29 test files | RS0-D (91) |
| Proxy: overwrite `X-Forwarded-For`, body limit, TLS, no query strings in logs, timeouts | No production proxy in the repo; the config block is written in `docs/KYAPTURE_UPLOAD_LIMITS.md` | 14-A / 16-A (54, 73), 15-A (72) |
| Bucket policy, Block Public Access, encryption at rest | Bucket config is not in the repo; must be checked on staging | 15-A (82) |
| Gallery expiry does not move public URLs; CDN/browser caches keep old copies | Needs an expiry sweep and CDN invalidation | 11-D, 15-A (134) |
| Per-environment CSP (no `localhost`, no `'unsafe-inline'`), `server_tokens off` | Needs a templated nginx config per build | 15-A (95) |
| Root container, image digests, unpinned `bcrypt`/`django-ses`, dependency CVE audit | Release hardening work | 15-A (96) |
| Security event logging, alerting, error tracking | No log pipeline yet | 15-A (97) |
| Dev compose secrets, unauthenticated Redis, ports on all interfaces | Dev stack only; release config audit | 13-C (87) |
| Separate IAM principals for S3/SES, secret manager | Infrastructure | 13-C (88) |
| Data retention, account deletion/export, Terms/Privacy | Owner decisions and pages | 13-C (98), 13-B (25) |
| Cookie domain `.kyapture.com` | Depends on DNS/hosting | 15-A (100) |
| QA values in `docs/qa-1r5e`, presigned URL printed by `test_s3_connection`, pushed screenshots | Repo hygiene with an owner decision on history | 13-C (101, 102) |
| PIN/password thresholds and minimum lengths; gallery-level lockout can be triggered on purpose | Owner decision | 13-A (135) |
| Video metadata dropped when a location is removed | Owner decision | 13-A (137) |
| Fail-closed EXIF on PNG and other cameras | Not in the test media (103 JPEGs passed) | 15-A (138) |
| Celery time limits for video / Web Size / ZIP tasks | Needs measured limits | 15-B (139) |
| Unreadable-codec videos and over-pixel images upload in full before refusal | Needs a chunked/resumable upload | product decision, 15-A (31, 75) |
| A partial `downloads` PATCH resets the keys it omits (owner-only, direct API) | Found in 7-E; not a client-reachable hole, the settings screen sends the whole block | 7R (152) |
| Concurrent use of one reset link not tested concurrently | Needs a TransactionTestCase that keeps the plan rows | 7R (150) |
| Hero cover and portfolio photos without deterrence; grid tile not keyboard-openable | UI chunks | 9B-1 (141, 142) |

## 3. Tests added in Task 7

| Chunk | Backend | Frontend / browser |
|---|---|---|
| 7-A | `apps/clients/tests/test_tenancy_7a.py`, `apps/galleries/tests/test_tenancy_7a.py`, `apps/users/tests/test_privilege_7a.py` (14 favorites tests failed before the fix) | — |
| 7-B | `apps/users/tests/test_security_7b.py`, `apps/clients/tests/test_security_7b.py`, `apps/photos/tests/test_security_7b.py` (54 of the first 70 failed before the fix) | `frontend/src/security/nginxCsp.test.js`, `downloadFlow.test.js` additions; browser run in the 7-B report |
| 7-D | `apps/clients/tests/test_deterrence_7d.py` (9) | `frontend/src/security/honestCopy.test.js`; `docs/qa-7d/qa-script.mjs` (98 checks) |
| 7-C | `apps/users/tests/test_password_reset_7c.py` (42); pre-fix proof `docs/qa-7c/test_prefix_proof_7c.py` (8, run against `f97d5c5`) | `docs/qa-7c/qa-script.mjs` (31 checks) |
| 7-E | none added (no code changed); the full suite re-run on a fresh test DB | `docs/qa-7e/qa-script.mjs` (42 checks), real-photo strip check over 103 files |

7-E run: backend 1373 tests OK on a fresh test DB (EXIT:0); `npm test` 121/121; `vite build` OK; browser 42/42 (login, reset, gallery
password, PIN, High Resolution, ZIP and its share/email link, share link, favorite, workspace and public images,
video, close/reopen, Pro Original byte-identical). No empty image box was found.

## 4. What was NOT tested

- **Real phone long-press**: headless Chrome fires no `contextmenu` for a held touch; iOS Safari / Android Chrome menus
  need a device (row 143, QA-A).
- **Real email deliverability**: every email went to Mailpit; SES sending, SPF/DKIM/DMARC, spam placement and bounce
  handling were not exercised (15-A).
- **Real 2 GB upload**: the largest real upload was a 3.7 MB JPEG; the 2048 MB video limit, proxy body limit and gunicorn
  timeout under a real large body were not run (rows 62, 72: 15-A).
- **MFA**: does not exist (row 90).
- **Network restrictions on `/admin/`**: none exist; nothing to test (row 90, 15-A).
- **Dependency CVE audit**: no `pip-audit`, `npm audit` or image scan was run in Task 7 (row 96, 15-A).
- Also not covered: the production proxy and S3 bucket (not in the repo), PNG and non-JPEG camera files, logout with an
  expired access cookie in a browser, a concurrent double-submit of one reset link (row 150), and anything on staging
  or production.
