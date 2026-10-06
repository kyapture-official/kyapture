# KYAPTURE security checklist (SEC-0)

Project-specific checklist for this codebase, filled in against commit `469fb66` by reading code and config only.
Use it as the acceptance list for chunks 7-A, 7-B, 13-C and 15-A. Finding IDs (SEC-xx) are in
[threat-model.md](threat-model.md); debt rows are in `docs/KYAPTURE_PRODUCTION_DEBT.md`.

Status legend:

| Mark | Meaning |
|---|---|
| ✅ | Present, read in the code (not runtime-tested unless stated) |
| ⚠️ | Present but weak (**Weakness**) |
| ❌ | Absent (**Missing control**) |
| ❓ | Depends on runtime/infra not in the repo, or inferred only (**Needs verification**) |
| 💡 | **Recommendation** (no current defect) |

---

## 1. Authentication

| Check | Status | Evidence / finding |
|---|---|---|
| Passwords hashed with a slow hasher | ✅ | Django default PBKDF2 (no `PASSWORD_HASHERS` override) |
| Password policy (length 8, common, numeric, similarity) on register, change, reset | ✅ | `base.py:150-155`; `apps/users/serializers.py:174-186, 241-251`; `apps/users/views.py:547-553` |
| Login throttled | ⚠️ | `login` 5/min per IP (`apps/users/views.py:103-122`), but the IP bucket is client-chosen (SEC-01) |
| Per-account lockout / backoff after failures | ❌ | None (SEC-01, row 78) |
| Generic login error | ✅ | "Invalid email or password." (`apps/users/serializers.py:217`) |
| Reset is anti-enumeration and rate-limited | ✅ | `apps/users/views.py:422-501`, `password_reset` 5/h |
| Reset/change revokes other sessions | ✅ | `apps/users/views.py:555-563`; change via serializer `save()` |
| Email verification at sign-up | ❌ | SEC-16, row 91 |
| MFA (at least for staff) | ❌ | SEC-15, row 90 |
| Gallery password hashed (bcrypt, ≤ 72 bytes) | ✅ | `apps/galleries/views.py:459-521`, `apps/clients/serializers.py:349-366` |
| Gallery password / PIN strength | ⚠️ | ≥ 4 chars; PIN 4-8 digits; no failure lockout (SEC-04, row 81) |

## 2. Authorization / RBAC

| Check | Status | Evidence / finding |
|---|---|---|
| Default permission is `IsAuthenticated` | ✅ | `base.py:90-92` |
| Every owner query scoped to `request.user` | ✅ | `apps/galleries/views.py:60, 159, 203-206, 406-409, 452-455, 558-561, 615-616, 708-709`; `apps/photos/views.py:429, 466, 503, 535, 719, 771, 813, 846`; notifications `notification_api.py:76-91` |
| Public lookups scoped by photographer + slug + published/active/unexpired | ✅ | every `get_gallery` in `apps/clients/views.py` |
| Child objects (asset, set, list, job) scoped to their gallery | ✅ | `apps/clients/views.py:216-228, 769-776, 1413, 1838` |
| Favorites scoped to the visitor | ⚠️ | Typed email grants another visitor's lists (SEC-02, rows 5, 79) |
| Contact allow-list for downloads | ⚠️ | Typed email, unverified (SEC-03, row 80) |
| Plan entitlements enforced server-side | ✅ | `require_feature` (`apps/users/serializers.py:86-111`), upload metrics and row lock (`apps/photos/views.py:186-252`), `effective_high_res_mode` |
| Entitlement edge cases | ⚠️ | Lapsed plan keeps limits up to 15 min (row 43, confirmed `apps/core/utils.py:97`); video minutes outside the lock (row 44, confirmed `apps/photos/views.py:240-252`) |
| Staff-only endpoints use `IsAdminUser` | ✅ | `apps/subscriptions/views.py:154, 189` |
| Staff bypass of plan limits is intended | 💡 | `apps/galleries/views.py:106`, `apps/photos/views.py:192` — document it |

## 3. Session / token security

| Check | Status | Evidence / finding |
|---|---|---|
| JWT in HttpOnly cookies, not in JS storage | ✅ | `apps/users/views.py:52-71`; `frontend/src/store/authStore.js:158-161` |
| `Secure` cookies in production | ✅ | `production.py:203-204`; cookies read `SESSION_COOKIE_SECURE` (`views.py:49`) |
| SameSite | ✅ | `Lax` on both JWT cookies |
| Short access token, rotating refresh with blacklist | ✅ | 15 min / 7 days (`base.py:132-136`); real rotation (`views.py:206-228`) |
| Logout clears cookies and blacklists refresh | ⚠️ | Requires a valid access token (`IsAuthenticated`, `views.py:151`); with an expired access cookie the refresh token is not blacklisted |
| Cookie domain scope | ❓ | `.kyapture.com` for JWT + CSRF cookies (SEC-28, row 100) |
| Unlock tokens: random, expiring, revoked on password change | ✅ | `apps/clients/models.py:10-15`; 30 days; `apps/galleries/views.py:500-537` |
| Unlock tokens hashed at rest, kept out of URLs | ❌ | SEC-14, row 89 |
| Signed download tokens bound to gallery + PIN fingerprint, 2 h | ✅ | `apps/clients/download_access.py:340-387` |
| Signing key separated / rotatable | ❌ | SEC-13, row 88 |
| Refresh endpoint throttle sized for real use | ❓ | SEC-17, row 92 |

## 4. Input validation

| Check | Status | Evidence / finding |
|---|---|---|
| Text fields stripped of HTML | ✅ | `sanitize_text` (bleach, `apps/core/utils.py:916-949`) on display name, bio, titles |
| Strict settings payloads (unknown keys rejected) | ✅ | `apps/users/serializers.py:288-297` |
| UUID lists validated before ORM | ✅ | `apps/clients/views.py:1263-1280` |
| Enumerated params allow-listed | ✅ | `resolution`, `sort` |
| Email format + length | ✅ | `download_access.py:309-326`, `favorite_lists.py:45-60` |
| Every `Gallery.design_settings` key validated | ❓ | `apps/galleries/serializers.py` not exhaustively traced in SEC-0 |

## 5. Injection

| Check | Status | Evidence / finding |
|---|---|---|
| SQL: ORM only | ✅ | Only `SELECT 1` raw (`config/urls.py:15`) |
| OS command: argv lists, no shell, fixed binaries | ✅ | `apps/core/utils.py:180, 511, 864-895` |
| Media parser abuse (ffmpeg/Pillow) | ⚠️ | Signature + size + pixel checks ✅; ffmpeg without timeout (SEC-18, row 93); decode memory not measured (row 74) |
| Email header injection | ✅ | Django mail API; studio name control chars stripped (`apps/clients/ready_email.py:51-54`) |
| Template injection | ✅ | No user-supplied templates; autoescape on HTML emails |

## 6. XSS / CSRF

| Check | Status | Evidence / finding |
|---|---|---|
| No raw HTML sinks in the SPA | ✅ | No `dangerouslySetInnerHTML`, `innerHTML`, `eval`, `new Function` in `frontend/src` |
| CSP on the SPA | ⚠️ | Present (`frontend/nginx.conf:66, 77, 97`) but includes `http://localhost:8000` and `style-src 'unsafe-inline'` in every build (SEC-20, row 95); stale comment (row 37 — confirmed, lines 41-45) |
| CSP / headers on Django-served HTML (admin) | ❓ | Django sets X-Frame-Options and nosniff; no CSP (dev: DEBUG pages) |
| CSRF for cookie-authenticated unsafe requests | ✅ | `apps/core/authentication.py:45-64`; `CSRF_TRUSTED_ORIGINS` set per env |
| Anonymous POSTs need no CSRF | ✅ | They read no cookies (`authentication_classes = []`); bearer values come from body/header |
| Uploaded files never served as HTML from the API origin | ❓ | Receipts limited to image extensions by the model validator; dev serves `/media/` from the API origin (SEC-06) |

## 7. API security

| Check | Status | Evidence / finding |
|---|---|---|
| Consistent JSON error shape, no stack traces | ✅ | `apps/core/exceptions.py`, `apps/core/middleware.py:41-61` |
| Enumeration-resistant 404s | ✅ | Owner and public lookups answer 404 for "not yours" |
| Pagination on list endpoints | ✅ | `PAGE_SIZE` 20, gallery/media paginators |
| Private storage paths never in public payloads | ⚠️ | Public serializer clean; video stream redirect (SEC-07, row 84) and owner `original_url` (SEC-08, row 6) expose them |
| Bearer secrets out of URLs | ⚠️ | Several by design (`link_token`, `file_token`, `?token=`): SEC-14 |
| API versioning | ✅ | `/api/v1/` |

## 8. Rate limiting / abuse

| Check | Status | Evidence / finding |
|---|---|---|
| Scoped throttles exist for login, unlock/PIN, reset, change, browse, preflight | ✅ | `base.py:98-128` |
| Client identity for throttles is trustworthy | ❌ | `NUM_PROXIES` outside `REST_FRAMEWORK` (SEC-01, row 78) |
| Proxy overwrites `X-Forwarded-For` | ❓ | Proxy not in repo (row 73) |
| Email abuse limits | ✅ | Ready email per email/IP/gallery (`base.py:298-304`); reset 5/h |
| Download/PIN limits per gallery | ✅ | `download_limit_reached`, `pin_limit_reached` (`download_access.py:232-284`) — successes only |
| Upload body refused before it is received | ❌ | Rows 4, 31, 75 (owned by 7-B) — confirmed: Django parses the multipart body before the view runs |
| `/health/` and `/admin/` throttled | ❌ | Plain Django views (SEC-15) |
| Registration abuse (anon 100/day only) | ⚠️ | No CAPTCHA/verification (SEC-16) |

## 9. File uploads

| Check | Status | Evidence / finding |
|---|---|---|
| Type by signature, not extension | ✅ | `validate_magic_bytes`, `validate_video_magic_bytes` (`apps/core/utils.py:231-270`) |
| Size and pixel limits before decoding; editable in admin | ✅ | `apps/photos/views.py:184-188`, `apps/subscriptions/upload_limits.py:40-53` (rows 8, 76 for the owner decisions) |
| Storage names generated server-side | ✅ | UUID-based paths (`apps/photos/models.py:13-97`); receipts `payment_proofs/{user}/{uuid}{ext}` |
| Original filename only used after sanitizing | ✅ | `sanitize_download_filename` (`apps/core/utils.py:385`) |
| Metadata privacy | ⚠️ | JPEG GPS stripped, fail-open; video metadata kept (SEC-19, row 94) |
| Proxy body limit / timeouts sized for limits | ❓ | Rows 72, 73 |
| Processing timeouts | ⚠️ | ffprobe 60 s, cjpegli timeout ✅; ffmpeg none (SEC-18) |
| Disk-space guard for video processing | ❌ | Row 71 |
| Antivirus / content scanning | 💡 | Not present; consider for receipts and any future non-image upload |

## 10. Database security

| Check | Status | Evidence / finding |
|---|---|---|
| Credentials from env in production | ✅ | `production.py:53-79` |
| Dev credentials not hardcoded / not exposed | ❌ | SEC-11, row 87 |
| TLS to the database | ❓ | No `sslmode` in `DATABASES` (row 103) |
| Least-privilege runtime DB user (no DDL) | ❌ | Every container runs `migrate` with the runtime credentials (`backend/docker-entrypoint.py:85-118`; row 103) |
| 64-bit byte columns | ✅ | Rule in `docs/KYAPTURE_AGENT_RULES.md`; `photos.0008` (rows 61-63) |
| Sensitive columns protected | ⚠️ | Unlock tokens plaintext (SEC-14) |

## 11. Secrets

| Check | Status | Evidence / finding |
|---|---|---|
| `.env` ignored and never committed | ✅ | `.gitignore:16-21`; history scan ([secrets.md](secrets.md) §5) |
| No cloud credentials in tree or history | ✅ | 0 high-signal hits across 171 commits |
| Production refuses insecure defaults | ✅ | `production.py:23-125` |
| `.env` kept out of images | ❌ | No `backend/.dockerignore` (SEC-10, row 86) |
| Rotation runbook / fallbacks | ❌ | SEC-13, row 88 |
| Separate IAM principals for S3 and SES | ❌ | `production.py:130-136` (row 88) |
| QA/test secrets not in tracked files | ⚠️ | `docs/qa-1r5e/qa-script.js:1, 11, 12` (SEC-25, row 102) |

## 12. Encryption

| Check | Status | Evidence / finding |
|---|---|---|
| HTTPS enforced by the app in production | ✅ | `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, HSTS 1 y + subdomains + preload (`production.py:217-247`) |
| TLS termination and certificates | ❓ | Proxy/hosting not in repo |
| S3 SigV4 and HTTPS URLs | ✅ | `production.py:258-265` |
| Encryption at rest (S3 SSE, RDS/volume encryption) | ❓ | No `ServerSideEncryption` parameter in storage classes; bucket default encryption not in repo |
| Passwords/PINs hashed, never reversible | ✅ | bcrypt / PBKDF2 |
| Dev traffic | 💡 | Plain HTTP on `:3000`/`:8000` (expected for local dev) |

## 13. CORS

| Check | Status | Evidence / finding |
|---|---|---|
| Explicit origin allow-list, no wildcard | ✅ | `development.py:21-26`; `production.py:163-168` |
| Credentials only with explicit origins | ✅ | `CORS_ALLOW_CREDENTIALS = True` (`base.py:78`) with lists above |
| Env parsing robust | ⚠️ | `production.py:163, 179` split on `,` without stripping spaces (a space after a comma silently breaks that origin) |
| Exposed headers minimal | ✅ | Only `Retry-After` (`base.py:83`) |

## 14. Dependency security

| Check | Status | Evidence / finding |
|---|---|---|
| All Python deps pinned | ⚠️ | `bcrypt`, `django-ses>=4.0.0` unpinned (`backend/requirements.txt:37, 40`) |
| Lock file for npm | ✅ | `frontend/package-lock.json` |
| Automated vulnerability audit (pip-audit / npm audit / Dependabot) | ❌ | No CI config in repo (SEC-21, row 96) |
| Known-CVE status of current versions | ❓ | Not checked in SEC-0 (offline, read-only) |
| Base images pinned by digest | ❌ | Tags only; `redis:alpine`, `mailpit:latest` float (row 96) |
| Build-time network fetches pinned | ⚠️ | jpegli by commit ✅, needs GitHub at build (row 53) |

## 15. Logging / monitoring

| Check | Status | Evidence / finding |
|---|---|---|
| No secrets/tokens in app logs | ✅ | Reviewed logger calls ([secrets.md](secrets.md) §6) |
| Security events logged (failed login/unlock/PIN, 429s, admin actions) | ❌ | SEC-22, row 97 |
| Central log shipping, retention, alerting | ❌ | Local file + console only (`base.py:335-379`) |
| Error tracking | ❌ | None in requirements |
| Worker/queue health alerting | ❌ | Accepted row 66 points to 11-D / 15-B |
| Audit trail integrity (real client IP) | ⚠️ | IP from left-most XFF (SEC-01) |

## 16. Admin security

| Check | Status | Evidence / finding |
|---|---|---|
| Admin requires staff | ✅ | Django admin; `IsAdminUser` API |
| Admin login rate-limited / lockout | ❌ | SEC-15, row 90 |
| MFA for staff | ❌ | SEC-15 |
| Admin path/network restricted | ❌ | Default `/admin/` (`config/urls.py:25`) |
| Hashes and tokens hidden in admin forms | ⚠️ | Session tokens shown read-only (`apps/clients/admin.py:37`); gallery form shows every field (no `fields`/`exclude` in `apps/galleries/admin.py`) |
| Payment approval audited | ⚠️ | `verified_by` stored (`apps/subscriptions/views.py:215-218`); no alert/log stream |

## 17. Deployment / infrastructure

| Check | Status | Evidence / finding |
|---|---|---|
| `DEBUG` off in production | ✅ | `production.py:8` |
| Production manifest (proxy, TLS, body limits, workers incl. `celery_websize`) in repo | ❌ | Rows 54, 73 |
| Containers run as non-root | ❌ | Backend has no `USER` (SEC-21, row 96) |
| Dev ports bound to localhost | ❌ | SEC-11, row 87 |
| Redis authentication | ❌ | SEC-11 |
| Private and public media separated at bucket/policy level | ❓ | SEC-05, row 82 |
| Gunicorn timeout sized for uploads | ❌ | Default 30 s (`backend/Dockerfile:105`, row 72) |
| Migrations safe under concurrency | ✅ | Advisory lock (`backend/docker-entrypoint.py:85-118`) |
| Host header trust | ❓ | `USE_X_FORWARDED_HOST = True` (`production.py:234`) requires the proxy to set/overwrite it |

## 18. Data privacy

| Check | Status | Evidence / finding |
|---|---|---|
| Client PII minimised and retained for a defined time | ⚠️ | DownloadLog 365 days, ClientSession 30 days, favorites/emails until gallery delete (SEC-23, row 98) |
| Account deletion / data export | ❌ | No endpoint (row 98) |
| Terms / Privacy / Cookies pages | ❌ | Row 25 |
| Protected galleries hidden from portfolio; private portfolio = 404 | ✅ | `apps/clients/views.py:2020-2049` |
| Location data removed from delivered photos | ⚠️ | SEC-19 |
| Public derivative URLs revocable | ❌ | SEC-09, row 85 |
| Screenshots with PII kept out of git | ❓ | 11 files already pushed (SEC-29, row 101; contradicts row 39's precondition) |
| Third-party requests disclosed (Google Fonts, Unsplash) | 💡 | Mention in the privacy policy |

## 19. Error handling

| Check | Status | Evidence / finding |
|---|---|---|
| API errors are JSON, generic on 500 | ✅ | `apps/core/middleware.py:41-61`; frontend normalises HTML errors (`axiosInstance.js:58-75`) |
| Reset flow never leaks via exceptions | ✅ | `apps/users/views.py:467-501` |
| Error text does not reveal secrets or private paths | ✅ | Reviewed messages in `apps/clients/views.py` |
| Fail-closed on security helpers | ⚠️ | `strip_exif_gps` fails open (SEC-19); `_original_within_cap` fails closed ✅ (`apps/clients/views.py:280-290`) |

## 20. Backup / recovery

| Check | Status | Evidence / finding |
|---|---|---|
| DB backup and tested restore | ❌ | Nothing in repo; rows 27, 61, 67, 77 (13-C / 15-B) |
| Media durability (S3 versioning / replication) | ❓ | Bucket config not in repo |
| Accidental delete protection | ⚠️ | Gallery delete is permanent and immediate (`apps/galleries/views.py:265-284`, `purge_gallery`) |
| Secrets recoverable after loss (secret manager) | ❓ | Not in repo |
| Runbook for key/credential rotation | ❌ | Row 88 |

---

## 21. Cross-check of security-related rows in `docs/KYAPTURE_PRODUCTION_DEBT.md`

| Row | Claim in the debt file | SEC-0 result | Evidence |
|---|---|---|---|
| 4 | Upload body received before the plan check | **Confirmed** (still open for abusive clients) | Multipart parsed by Django before `PhotoListUploadView.post`; checks start at `apps/photos/views.py:174-206` |
| 5 | Favorites matched by typed email; anyone can see another person's list | **Confirmed and wider**: also rename, delete and add to that list | SEC-02; new row 79 |
| 6 | `original_url` in the media API vs private-storage rule | **Confirmed for the owner API only** (clients never get the field); separate client-facing exposures found | SEC-08; SEC-07 (row 84), SEC-27 (row 99) |
| 7 | "Direct API refused" for Free users proven by tests + raw 403 only | **Not re-verified** (no runtime in SEC-0); server-side checks present in code (`require_feature`, metrics) | stays with 7-B / 15-A |
| 8 | Hard per-file ceilings are admin values now | **Confirmed**: one `UploadLimits` row editable in admin | `apps/subscriptions/admin.py:33-52`, `upload_limits.py:40-53` |
| 9 | Share by email is `mailto:` only | Not a security gap; no change | — |
| 25 | Terms/Privacy/Cookies links removed | **Confirmed relevant to privacy** | checklist §18 |
| 27 | Back up before production | **Confirmed**: no backup tooling in repo | checklist §20 |
| 30 | Agent rules uncommitted; pixieset-ref untracked | **Partly outdated**: `docs/KYAPTURE_AGENT_RULES.md` is tracked (commit `469fb66`); 11 pixieset-ref files are tracked, other subfolders untracked | `git ls-files` |
| 31 | Unreadable-codec video uploads in full | **Confirmed by code** (pre-flight is a browser feature; server reads the body) | rows 4, 75 |
| 37 | nginx comment says no CSP although one is set | **Confirmed** | `frontend/nginx.conf:41-45` vs `66` |
| 39 | Screenshots show IP/emails: blur before the first push | **Contradicted precondition**: 11 files are already on `origin/feature/landing-page-redesign`; contents not inspected | SEC-29, new row 101 |
| 43 | Metrics use `status='active'` only | **Confirmed** | `apps/core/utils.py:97` |
| 44 | Video minutes checked outside the row lock | **Confirmed** | `apps/photos/views.py:240-252` re-checks storage only |
| 53 | jpegli cloned from GitHub at build | **Confirmed** | `backend/Dockerfile:14-18` |
| 54 | `celery_websize` worker must be in the production manifest | **Confirmed**; no production manifest exists | `docker-compose.yml:151-172` only |
| 62, 72 | No real >2 GiB upload; gunicorn default timeout | **Confirmed** (`--timeout` absent) | `backend/Dockerfile:105` |
| 71 | No disk-space guard for video processing | **Confirmed** (none found) | `apps/core/utils.py:793-900` |
| 73 | Proxy `client_max_body_size` not in repo | **Confirmed**: only the SPA nginx config exists and it does not proxy the API | `frontend/nginx.conf:16-22` |
| 74 | Decode memory at the pixel limit not measured | **Confirmed** (no measurement in repo) | — |
| 75 | Server reads the whole body before judging a file | **Confirmed** | as row 4 |

## 22. New debt rows added by SEC-0

Rows 78-103 in section L of `docs/KYAPTURE_PRODUCTION_DEBT.md`. Owners: **7-A** (auth, identity, sessions, admin),
**7-B** (private storage, media pipeline, entitlement abuse), **13-C** (release config, secrets, data), **15-A** (staging
verification, infra, supply chain).

| Row | Finding | Owner |
|---|---|---|
| 78 | SEC-01 XFF throttle identity | 7-A |
| 79 | SEC-02 favorites edit/delete via claimed email | 7-A |
| 80 | SEC-03 contact allow-list | 7-A |
| 81 | SEC-04 PIN/password lockout | 7-A |
| 82 | SEC-05 shared bucket/prefix, derivable original key | 7-B |
| 83 | SEC-06 dev `/media/` serves private files | 7-B |
| 84 | SEC-07 video stream original fallback | 7-B |
| 85 | SEC-09 permanent public derivative URLs | 7-B |
| 86 | SEC-10 backend `.dockerignore` | 13-C |
| 87 | SEC-11 dev credentials and published ports | 13-C |
| 88 | SEC-13 signing-key separation, rotation, IAM split | 13-C |
| 89 | SEC-14 unlock tokens plaintext / in URLs | 7-A |
| 90 | SEC-15 admin hardening | 7-A |
| 91 | SEC-16 email verification | 7-A |
| 92 | SEC-17 refresh throttle | 7-A |
| 93 | SEC-18 ffmpeg timeouts | 7-B |
| 94 | SEC-19 metadata privacy | 7-B |
| 95 | SEC-20 per-environment CSP | 15-A |
| 96 | SEC-21 container user, pins, audits | 15-A |
| 97 | SEC-22 security logging/alerting | 15-A |
| 98 | SEC-23 PII lifecycle | 13-C |
| 99 | SEC-27 non-READY download fallback | 7-B |
| 100 | SEC-28 cookie domain | 15-A |
| 101 | SEC-29 screenshots already pushed | 13-C |
| 102 | SEC-25/26 secret hygiene | 13-C |
| 103 | DB least privilege and TLS | 15-A |
