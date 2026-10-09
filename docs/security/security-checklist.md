# KYAPTURE security checklist (SEC-0)

Project-specific checklist for this codebase, filled in against commit `469fb66` by reading code and config only.
Use it as the acceptance list for chunks 7-A, 7-B, 13-C and 15-A. Finding IDs (SEC-xx) are in
[threat-model.md](threat-model.md); debt rows are in `docs/KYAPTURE_PRODUCTION_DEBT.md`.

**Current state (7-E, 2026-10-07).** Sections 1-20 reflect the code after 7-A, 7-B, 7-C and 7-D; every remaining ⚠️, ❌
and ❓ names its debt row and owning chunk, or says why it is accepted. Final status of every item:
[docs/qa-7e/results.md](../qa-7e/results.md) section 4. Sections 21-22 are the SEC-0 cross-check as it was made
(historical; the owners there were later reassigned in the debt file).

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
| Password policy (length 8, common, numeric, similarity) on register, change, reset | ✅ | One helper since 7-C: `apps/users/password_policy.py` (validators + not the email + not the current password) |
| Login throttled | ✅ | `login` 5/min per address (no longer client-chosen, 7-B) + `login_account` 20/h per account; Redis-shared (`apps/users/tests/test_security_7b.py`) |
| Per-account lockout / backoff after failures | ✅ | `login_account` 20/h per email (7-B) |
| Generic login error | ✅ | "Invalid email or password." (`apps/users/serializers.py:217`) |
| Reset is anti-enumeration and rate-limited | ✅ | 7-C: same status/body for any address, 0 queries in the request (Celery task does the lookup); `password_reset` 10/h per client (429), `password_reset_email` 3/h per address (silent), `password_reset_confirm` 30/h |
| Reset link: random, hashed, single-use, short, newest only, host from settings | ✅ | 7-C: 256 bits, SHA-256 at rest (`PasswordResetToken`), 30 min (`PASSWORD_RESET_TOKEN_MINUTES`), URL fragment on `FRONTEND_URL`, deleted on use / newer request / revocation (`apps/users/tests/test_password_reset_7c.py`) |
| Reset/change revokes other sessions | ✅ | 7-C: `revoke_all_sessions` bumps `token_version` (`tv` claim checked on every request and refresh): access AND refresh tokens die at once; also admin password change; owner gets a "password changed" email |
| Email verification at sign-up | ❌ | SEC-16, row 91: decided in 7-C (verify before publishing or third-party email); owner RS0-D |
| MFA (at least for staff) | ❌ | SEC-15, row 90 (13-C; plan in secrets.md §7.2) |
| Gallery password hashed (bcrypt, ≤ 72 bytes) | ✅ | `apps/galleries/views.py:459-521`, `apps/clients/serializers.py:349-366` |
| Gallery password / PIN strength | ⚠️ | ≥ 4 chars; PIN 4-8 digits; failure lockout per client and per gallery since 7-B (`apps/clients/lockout.py`); minimum lengths unchanged (row 135) |

## 2. Authorization / RBAC

| Check | Status | Evidence / finding |
|---|---|---|
| Default permission is `IsAuthenticated` | ✅ | `base.py:90-92` |
| Every owner query scoped to `request.user` | ✅ | `apps/galleries/views.py:60, 159, 203-206, 406-409, 452-455, 558-561, 615-616, 708-709`; `apps/photos/views.py:429, 466, 503, 535, 719, 771, 813, 846`; notifications `notification_api.py:76-91` |
| Public lookups scoped by photographer + slug + published/active/unexpired | ✅ | every `get_gallery` in `apps/clients/views.py` |
| Child objects (asset, set, list, job) scoped to their gallery | ✅ | `apps/clients/views.py:216-228, 769-776, 1413, 1838` |
| Favorites scoped to the visitor | ✅ | Fixed in 7-A: lists match the client key only; an email is a label (SEC-02, rows 5, 79; tests in `apps/clients/tests/test_tenancy_7a.py`) |
| Contact allow-list for downloads | ✅ | One-time emailed code before a token (7-B, row 80) |
| Plan entitlements enforced server-side | ✅ | `require_feature` (`apps/users/serializers.py:86-111`), upload metrics and row lock (`apps/photos/views.py:186-252`), `effective_high_res_mode` |
| Entitlement edge cases | ✅ | Fixed in 7-B: metrics need `expires_at` in the future (row 43); minutes re-checked under the row lock (row 44) |
| An ended plan loses paid features with no job running; the daily job and the sweep never overwrite a renewal | ✅ | 7.5-C: request-time rule proven with the job never run (`RequestTimeExpiryTests`); the sweep and `my-subscription` flip `expired` only under the user + subscription row locks with the status re-read (`lifecycle.expire_lapsed`); the job is lock-protected and idempotent; no HTTP endpoint runs it. Branding colour is not plan-gated (row 183) |
| Staff-only endpoints use `IsAdminUser` | ✅ | `apps/subscriptions/views.py:154, 189` |
| Staff bypass of plan limits is intended | 💡 | `apps/galleries/views.py`, `apps/photos/views.py`: document it |

## 3. Session / token security

| Check | Status | Evidence / finding |
|---|---|---|
| JWT in HttpOnly cookies, not in JS storage | ✅ | `apps/users/views.py:52-71`; `frontend/src/store/authStore.js:158-161` |
| `Secure` cookies in production | ✅ | `production.py:203-204`; cookies read `SESSION_COOKIE_SECURE` (`views.py:49`) |
| SameSite | ✅ | `Lax` on both JWT cookies |
| Short access token, rotating refresh with blacklist | ✅ | 15 min / 7 days (`base.py:132-136`); real rotation (`views.py:206-228`) |
| Logout clears cookies and blacklists refresh | ⚠️ | Requires a valid access token (`IsAuthenticated`). **Accepted (7-E)**: the SPA's 401 handler refreshes and retries the logout (`frontend/src/api/axiosInstance.js`); a caller without a valid refresh token has nothing left to blacklist. Not browser-tested |
| Cookie domain scope | ❓ | `.kyapture.com` for JWT + CSRF cookies (SEC-28, row 100) |
| Unlock tokens: random, expiring, revoked on password change | ✅ | `apps/clients/models.py:10-15`; 30 days; `apps/galleries/views.py:500-537` |
| Unlock tokens hashed at rest, kept out of URLs | ⚠️ | SHA-256 at rest since 7-B; still accepted in `?token=` for `<a href>`/`<video src>` (row 133) |
| Signed download tokens bound to gallery + PIN fingerprint, 2 h | ✅ | `apps/clients/download_access.py:340-387` |
| Signing key separated / rotatable | ✅ | `JWT_SIGNING_KEY`, `SECRET_KEY_FALLBACKS` (7-B; runbook secrets.md §7.1) |
| Refresh endpoint throttle sized for real use | ✅ | `token_refresh` 60/h per verified user (7-B) |

## 4. Input validation

| Check | Status | Evidence / finding |
|---|---|---|
| Text fields stripped of HTML | ✅ | `sanitize_text` (bleach, `apps/core/utils.py:916-949`) on display name, bio, titles |
| Strict settings payloads (unknown keys rejected) | ✅ | `apps/users/serializers.py:288-297` |
| UUID lists validated before ORM | ✅ | `apps/clients/views.py:1263-1280` |
| Enumerated params allow-listed | ✅ | `resolution`, `sort` |
| Email format + length | ✅ | `download_access.py:309-326`, `favorite_lists.py:45-60` |
| Every `Gallery.design_settings` key validated | ⚠️ | Checked in 7-E: presentation keys, `watermark`, `downloads`, `privacy`, `coverPhoto` validated; the public payload is an allow-list re-validated on read; unknown top-level keys from the owner are stored as sent (accepted: owner-only, never sent to visitors). A partial `downloads` block resets omitted keys (row 152, 7R) |

## 5. Injection

| Check | Status | Evidence / finding |
|---|---|---|
| SQL: ORM only | ✅ | Only `SELECT 1` raw (`config/urls.py:15`) |
| OS command: argv lists, no shell, fixed binaries | ✅ | `apps/core/utils.py:180, 511, 864-895` |
| Media parser abuse (ffmpeg/Pillow) | ⚠️ | Signature + size + pixel checks ✅; every ffmpeg call has a timeout (7-B); decode memory not measured (row 74) |
| Email header injection | ✅ | Django mail API; studio name control chars stripped (`apps/clients/ready_email.py:51-54`) |
| Template injection | ✅ | No user-supplied templates; autoescape on HTML emails |

## 6. XSS / CSRF

| Check | Status | Evidence / finding |
|---|---|---|
| No raw HTML sinks in the SPA | ✅ | No `dangerouslySetInnerHTML`, `innerHTML`, `eval`, `new Function` in `frontend/src` |
| CSP on the SPA | ⚠️ | Present in every `frontend/nginx.conf` location but includes `http://localhost:8000` and `style-src 'unsafe-inline'` in every build (SEC-20, row 95, 15-A); Google font hosts removed and the stale comment fixed in 7-B (rows 120, 37) |
| CSP / headers on Django-served HTML (admin) | ⚠️ | Django sends `X-Frame-Options: DENY`, nosniff and `Referrer-Policy: same-origin` (checked on `:8000` in 7-E); no CSP. Deferred to 15-A with row 95 |
| CSRF for cookie-authenticated unsafe requests | ✅ | `apps/core/authentication.py:45-64`; `CSRF_TRUSTED_ORIGINS` set per env |
| Anonymous POSTs need no CSRF | ✅ | They read no cookies (`authentication_classes = []`); bearer values come from body/header |
| Uploaded files never served as HTML from the API origin | ✅ | Receipts limited to image extensions and private; dev `/media/` serves public derivative names only, private files need a signed URL (7-B, `apps/core/media.py`); production media is on S3, another origin |

## 7. API security

| Check | Status | Evidence / finding |
|---|---|---|
| Consistent JSON error shape, no stack traces | ✅ | `apps/core/exceptions.py`, `apps/core/middleware.py:41-61` |
| Enumeration-resistant 404s | ✅ | Owner and public lookups answer 404 for "not yours" |
| Pagination on list endpoints | ✅ | `PAGE_SIZE` 20, gallery/media paginators |
| Private storage paths never in public payloads | ✅ | Video stream serves the playback copy only (7-B); owner `original_url` is a 1 h signed URL to a random key |
| Bearer secrets out of URLs | ⚠️ | Still in query strings where a browser cannot send a header (`<a href>`, `<video src>`). **Accepted in 7-E** (row 133): Referrer-Policy keeps them on their origin, file-granting links live 1-2 h, the unlock token is hashed at rest and the production access log drops query strings |
| API versioning | ✅ | `/api/v1/` |

## 8. Rate limiting / abuse

| Check | Status | Evidence / finding |
|---|---|---|
| Scoped throttles exist for login, unlock/PIN, reset, change, browse, preflight | ✅ | `base.py:98-128` |
| Client identity for throttles is trustworthy | ✅ | `REST_FRAMEWORK['NUM_PROXIES']` (7-B); counts shared in Redis (row 108) |
| Proxy overwrites `X-Forwarded-For` | ❓ | Proxy not in repo (row 73) |
| Email abuse limits | ✅ | Ready email per email/IP/gallery (`base.py:298-304`); reset email 3/h per address + 10/h per client (7-C) |
| Download/PIN limits per gallery | ✅ | `download_limit_reached`, `pin_limit_reached` (successes); failures lock per client and per gallery (`apps/clients/lockout.py`, 7-B) |
| Upload body refused before it is received | ⚠️ | 7-B: oversized / storage-full refused from headers before the body is read; the proxy limit is the real stop (plan in `docs/KYAPTURE_UPLOAD_LIMITS.md`); row 31 open |
| `/health/` and `/admin/` throttled | ⚠️ | Admin login throttled and locks (7-B). `/health/` unthrottled: **accepted** (one `SELECT 1`, needed by container probes; edge rate limits are the proxy's job, 14-A/16-A) |
| Registration abuse | ⚠️ | `register` 10/h per address (7-B); no CAPTCHA or email verification (SEC-16, row 91, RS0-D) |

## 9. File uploads

| Check | Status | Evidence / finding |
|---|---|---|
| Type by signature, not extension | ✅ | `validate_magic_bytes`, `validate_video_magic_bytes` (`apps/core/utils.py:231-270`) |
| Size and pixel limits before decoding; editable in admin | ✅ | `apps/photos/views.py:184-188`, `apps/subscriptions/upload_limits.py:40-53` (rows 8, 76 for the owner decisions) |
| Storage names generated server-side | ✅ | UUID-based paths (`apps/photos/models.py:13-97`); receipts `payment_proofs/{user}/{uuid}{ext}` |
| Original filename only used after sanitizing | ✅ | `sanitize_download_filename` (`apps/core/utils.py:385`); payment proofs never keep the uploaded name (7.5-B) |
| Metadata privacy | ✅ | Fail closed; EXIF, XMP and PNG eXIf GPS; video location removed (7-B) |
| Proxy body limit / timeouts sized for limits | ❓ | Rows 72 (15-A), 73 (14-A/16-A); plan in `docs/KYAPTURE_UPLOAD_LIMITS.md` |
| Processing timeouts | ✅ | ffprobe, ffmpeg, cjpegli all time-limited; photo task Celery limits (7-B) |
| Disk-space guard for video processing | ❌ | Row 71 (11-D, 15-A) |
| Antivirus / content scanning | 💡 | Not present; consider for payment proofs (images and PDFs, 7.5-B, row 171) and any future non-image upload |

## 10. Database security

| Check | Status | Evidence / finding |
|---|---|---|
| Credentials from env in production | ✅ | `production.py:53-79` |
| Dev credentials not hardcoded / not exposed | ❌ | SEC-11, row 87 (13-C); re-checked 7-E: still in compose |
| TLS to the database | ❓ | No `sslmode` in `DATABASES` (row 103, 15-A) |
| Least-privilege runtime DB user (no DDL) | ❌ | Every container runs `migrate` with the runtime credentials (`backend/docker-entrypoint.py`; row 103, 15-A) |
| 64-bit byte columns | ✅ | Rule in `docs/KYAPTURE_AGENT_RULES.md`; `photos.0008` (rows 61-63) |
| Sensitive columns protected | ✅ | Unlock tokens (7-B) and password-reset tokens (7-C) stored as SHA-256; passwords/PINs hashed |

## 11. Secrets

| Check | Status | Evidence / finding |
|---|---|---|
| `.env` ignored and never committed | ✅ | `.gitignore:16-21`; history scan ([secrets.md](secrets.md) §5) |
| No cloud credentials in tree or history | ✅ | 0 high-signal hits across 171 commits |
| Production refuses insecure defaults | ✅ | `production.py:23-125` |
| `.env` kept out of images | ✅ | `backend/.dockerignore` (7-B; rebuilt image checked) |
| Rotation runbook / fallbacks | ✅ | secrets.md §7.1 (7-B) |
| Separate IAM principals for S3 and SES | ❌ | `production.py` (row 88, 13-C) |
| QA/test secrets not in tracked files | ⚠️ | `docs/qa-1r5e/qa-script.js:1, 11, 12` (SEC-25, row 102, 13-C). The 7-C and 7-E QA scripts take every secret from the environment |

## 12. Encryption

| Check | Status | Evidence / finding |
|---|---|---|
| HTTPS enforced by the app in production | ✅ | `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, HSTS 1 y + subdomains + preload (`production.py:217-247`) |
| TLS termination and certificates | ❓ | Proxy/hosting not in repo (rows 54, 73: 14-A/16-A) |
| S3 SigV4 and HTTPS URLs | ✅ | `production.py:258-265` |
| Encryption at rest (S3 SSE, RDS/volume encryption) | ❓ | No `ServerSideEncryption` parameter in storage classes; bucket default encryption not in repo (verify in 15-A with row 82) |
| Passwords/PINs hashed, never reversible | ✅ | bcrypt / PBKDF2 |
| Dev traffic | 💡 | Plain HTTP on `:3000`/`:8000` (expected for local dev) |

## 13. CORS

| Check | Status | Evidence / finding |
|---|---|---|
| Explicit origin allow-list, no wildcard | ✅ | `development.py:21-26`; `production.py:163-168` |
| Credentials only with explicit origins | ✅ | `CORS_ALLOW_CREDENTIALS = True` (`base.py:78`) with lists above |
| Env parsing robust | ✅ | Spaces stripped (7-B, tested in `ProductionHeaderSettingsTests`) |
| Exposed headers minimal | ✅ | Only `Retry-After` (`base.py:83`) |

## 14. Dependency security

| Check | Status | Evidence / finding |
|---|---|---|
| All Python deps pinned | ⚠️ | `bcrypt`, `django-ses>=4.0.0` unpinned (`backend/requirements.txt:37, 40`; row 96, 15-A) |
| Lock file for npm | ✅ | `frontend/package-lock.json` |
| Automated vulnerability audit (pip-audit / npm audit / Dependabot) | ❌ | No CI config in repo (SEC-21, row 96) |
| Known-CVE status of current versions | ❓ | Not checked in SEC-0 nor in 7-E (no `pip-audit` / `npm audit` run); row 96, 15-A |
| Base images pinned by digest | ❌ | Tags only; `redis:alpine`, `mailpit:latest` float (row 96, 15-A) |
| Build-time network fetches pinned | ⚠️ | jpegli by commit ✅, needs GitHub at build (row 53) |

## 15. Logging / monitoring

| Check | Status | Evidence / finding |
|---|---|---|
| No secrets/tokens in app logs | ✅ | Reviewed logger calls ([secrets.md](secrets.md) §6) |
| Security events logged (failed login/unlock/PIN, 429s, admin actions) | ⚠️ | SEC-22, row 97 (15-A). Since 7.5-A the audit log records lockouts, password changes/resets and staff actions (row 162 lists what is not covered); there is still no log shipping or alerting |
| Central log shipping, retention, alerting | ❌ | Local file + console only (`base.py` `LOGGING`; row 97, 15-A) |
| Error tracking | ❌ | None in requirements (row 97, 15-A) |
| Worker/queue health alerting | ❌ | Accepted row 66 points to 11-D / 15-B |
| Audit trail integrity (real client IP) | ✅ | Stored and counted IPs come from `apps/core/request_ip.client_ip` with `NUM_PROXIES` (7-B); the production proxy must overwrite XFF (14-A/16-A) |

## 16. Admin security

| Check | Status | Evidence / finding |
|---|---|---|
| Admin requires staff | ✅ | Django admin; `IsAdminUser` API |
| Admin login rate-limited / lockout | ✅ | `apps/core/admin_login.py` (7-B) |
| MFA for staff | ❌ | Plan in secrets.md §7.2 (row 90, 13-C) |
| Admin path/network restricted | ❌ | Default `/admin/` (`config/urls.py`; row 90, 15-A) |
| Hashes and tokens hidden in admin forms | ✅ | Excluded (7-B) |
| Payment approval audited | ✅ | `verified_by` stored, and an append-only `staff_audit_log` row per submit, approve, reject, proof opened and queue read (7.5-A, 7.5-B: `payment.*` actions, ids and money only, never the proof, reference or note); approve / reject lock the payment row and are idempotent; staff cannot review their own payment; the old unlocked review route is gone; no alert/log stream (row 97, 15-A) |
| Staff actions and security events in an append-only audit log | ✅ | 7.5-A: `StaffAuditLog` (ORM, admin and DB trigger refuse change/delete); suspend, reactivate, list/lookup/audit reads, feedback status, payment review, password change/reset, login lockouts, gallery gate lock. Not covered: row 162 |
| Suspended account: login, tokens and public galleries stop | ✅ | 7.5-A: `revoke_all_sessions` + `photographer__is_active` on every public lookup; one test per path (row 131) |

## 17. Deployment / infrastructure

| Check | Status | Evidence / finding |
|---|---|---|
| `DEBUG` off in production | ✅ | `production.py:8` |
| Production manifest (proxy, TLS, body limits, workers incl. `celery_websize`) in repo | ❌ | Rows 54, 73 (14-A/16-A) |
| Containers run as non-root | ❌ | Backend has no `USER` (SEC-21, row 96, 15-A); re-checked 7-E |
| Dev ports bound to localhost | ❌ | SEC-11, row 87 (13-C) |
| Redis authentication | ❌ | SEC-11, row 87 (13-C) |
| Private and public media separated at bucket/policy level | ❓ | Keys separated in code (random private key part, rotating public `media_token`, 7-B); bucket policy / Block Public Access to verify in 15-A (row 82) |
| Gunicorn timeout sized for uploads | ❌ | Default 30 s (`backend/Dockerfile`, row 72, 15-A; plan in `docs/KYAPTURE_UPLOAD_LIMITS.md`) |
| Migrations safe under concurrency | ✅ | Advisory lock (`backend/docker-entrypoint.py:85-118`) |
| Host header trust | ❓ | `USE_X_FORWARDED_HOST = True` (`production.py`) requires the proxy to set/overwrite it (block in `docs/KYAPTURE_UPLOAD_LIMITS.md`; 14-A/16-A) |

## 18. Data privacy

| Check | Status | Evidence / finding |
|---|---|---|
| Client PII minimised and retained for a defined time | ⚠️ | DownloadLog 365 days, ClientSession 30 days, favorites/emails until gallery delete (SEC-23, row 98, 13-C) |
| Account deletion / data export | ❌ | No endpoint (row 98, 13-C) |
| Terms / Privacy / Cookies pages | ❌ | Row 25 (13-B) |
| Protected galleries hidden from portfolio; private portfolio = 404 | ✅ | `apps/clients/views.py:2020-2049` |
| Location data removed from delivered photos | ✅ | 7-B (photos and videos) |
| Public derivative URLs revocable | ⚠️ | Moved to new keys on password / unpublish (7-B; re-checked in the 7-E browser run: old URL 404, new URLs load); not on expiry, caches not purged (row 134: 11-D, 15-A) |
| Screenshots with PII kept out of git | ❓ | 11 files already pushed (SEC-29, row 101, 13-C; contradicts row 39's precondition). The 7-E QA screenshots (real people) were not committed |
| Third-party requests disclosed (Unsplash; Google Fonts no longer used since 7-B) | 💡 | Mention in the privacy policy |

## 19. Error handling

| Check | Status | Evidence / finding |
|---|---|---|
| API errors are JSON, generic on 500 | ✅ | `apps/core/middleware.py:41-61`; frontend normalises HTML errors (`axiosInstance.js:58-75`) |
| Reset flow never leaks via exceptions | ✅ | 7-C: mail is sent by a Celery task (a failure is retried there, the API answer never changes); no token or password in logs, bodies or the bell (tested) |
| Error text does not reveal secrets or private paths | ✅ | Reviewed messages in `apps/clients/views.py` |
| Fail-closed on security helpers | ✅ | `strip_exif_gps` fails closed since 7-B; `_original_within_cap` fails closed |

## 20. Backup / recovery

| Check | Status | Evidence / finding |
|---|---|---|
| DB backup and tested restore | ❌ | Nothing in repo; rows 27, 61, 67, 77 (13-C / 15-B) |
| Media durability (S3 versioning / replication) | ❓ | Bucket config not in repo (verify in 15-A with row 82) |
| Accidental delete protection | ⚠️ | Gallery delete is permanent and immediate (`apps/galleries/views.py`, `purge_gallery`); owner decision with the backup work (13-C, rows 27/77) |
| Secrets recoverable after loss (secret manager) | ❓ | Not in repo; secret manager is part of row 88 (13-C) |
| Runbook for key/credential rotation | ✅ | `SECRET_KEY` / `JWT_SIGNING_KEY` runbook in secrets.md §7.1 (7-B); the IAM split stays open (row 88, 13-C) |

---

## 21. Cross-check of security-related rows in `docs/KYAPTURE_PRODUCTION_DEBT.md` (SEC-0, historical)

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

## 22. New debt rows added by SEC-0 (owners as first assigned; the debt file holds the current owner)

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
