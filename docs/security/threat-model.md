# KYAPTURE threat model (SEC-0)

Scope: the code and config on branch `feature/landing-page-redesign` at commit `469fb66` (2026-10-06).
Method: read-only review of the backend (Django 6 / DRF / SimpleJWT / Celery), the frontend (React + Vite, nginx image),
`docker-compose.yml`, both Dockerfiles, settings, and the git history of every branch. Nothing was run: no Docker, no app,
no browser. Every behaviour claim below comes from reading code or config, so per the SEC-0 rules a vulnerability that
was not reproduced is marked **Needs verification**, even when the code path is unambiguous.

Companion files: [secrets.md](secrets.md), [attack-surface.md](attack-surface.md), [security-checklist.md](security-checklist.md).
New gaps are tracked as rows 78-102 in `docs/KYAPTURE_PRODUCTION_DEBT.md` (section L).

Classification used for every finding:

| Label | Meaning |
|---|---|
| **Confirmed vulnerability** | Exploitable flaw proven by direct evidence (a file, a git object). None of the code-path flaws below were reproduced, so none carry this label except where the evidence is the artifact itself |
| **Weakness** | The control exists but is weaker than it should be; the fact is directly visible in a file |
| **Missing control** | No control exists for this threat |
| **Needs verification** | Inferred from reading code/config, or depends on runtime/infra not in the repo |
| **Recommendation** | Hardening advice with no current defect |

Severity scale: Critical / High / Medium / Low / Info.

---

## 1. System overview

```
Browser (photographer SPA, client gallery SPA)
   │  HTTPS (prod, assumed) / HTTP :3000 + :8000 (dev compose)
   ├──► nginx (frontend image, static SPA only, frontend/nginx.conf) — does NOT proxy /api
   └──► Django API :8000 (runserver in dev, gunicorn in the image CMD)
            ├── PostgreSQL 16 (users, galleries, assets, sessions, logs, payments)
            ├── Redis (Celery broker /0 and results /1, no auth)
            ├── Celery worker, celery_websize worker, celery beat
            │      └── ffmpeg / ffprobe / cjpegli subprocesses on uploaded files
            ├── Storage: S3 (prod, enforced by production.py) or local MEDIA_ROOT (dev)
            │      ├── PrivateMediaStorage: originals, Download Masters, Web Size cache, ZIPs (private ACL, signed 1 h URLs)
            │      └── PublicMediaStorage: WebP tiers, posters, playback MP4, logos, avatars (public-read, unsigned)
            └── Mail: SES (prod) / Mailpit SMTP (dev compose) / console (bare dev)
```

The production reverse proxy (TLS, request body limit, X-Forwarded-For handling) is **not in this repo**
(debt row 73). `docker-compose.yml` is explicitly a development stack (its header, lines 2-28).

---

## 2. Assets

| ID | Asset | Where it lives | Why it matters |
|---|---|---|---|
| A1 | Original photos and videos (byte-preserved) | `MediaAsset.original_file`, PrivateMediaStorage (`apps/photos/models.py:212`) | The product's core value; "originals stay private" is a project rule |
| A2 | Download Masters (3600 px) and cached Web Sizes | PrivateMediaStorage (`apps/photos/models.py:231`, `apps/clients/web_size.py`) | Plan entitlement: a Free client must not get more than the master |
| A3 | Public derivatives (WebP tiers, posters, playback MP4) | PublicMediaStorage (`apps/photos/models.py:219-255`) | Watermarked display copies; still the photographer's work |
| A4 | Prepared ZIP downloads | PrivateMediaStorage, `DownloadJob.files[].storage_path` | Whole galleries in one file |
| A5 | Photographer accounts and sessions | `users.User`, JWT cookies `access_token` / `refresh_token` | Full control of galleries and billing |
| A6 | Gallery password and download PIN | bcrypt hashes `Gallery.password_hash`, `Gallery.download_pin_hash` (`apps/galleries/models.py:56,66`) | Gate client access |
| A7 | Client unlock tokens and download tokens | `ClientSession.access_token` (plaintext, `apps/clients/models.py:61`); signed tokens (`apps/clients/download_access.py:348-460`) | Bearer access to protected galleries |
| A8 | Client PII: emails, IPs, names, favorites | `ClientSession`, `DownloadLog`, `FavoriteList`, `Favorite` | Personal data of the photographer's clients |
| A9 | Payment receipts and subscription state | `ManualPayment.payment_proof`, `UserSubscription` | Financial data; plan entitlement |
| A10 | Secrets | `SECRET_KEY`, DB credentials, AWS keys (S3 + SES) | `SECRET_KEY` signs every JWT and every download token (see [secrets.md](secrets.md)) |
| A11 | Platform config | `SubscriptionPlan`, `UploadLimits` rows (Django admin) | Controls every limit and price |

## 3. Actors

| Actor | Trust | Capabilities |
|---|---|---|
| Anonymous internet user | Untrusted | All `/api/v1/public/*`, register, login, password reset, `/api/total-users`, `/health/`, `/admin/` login page |
| Gallery client (visitor) | Untrusted, holds link and maybe password/PIN | Browse, favorite, download within gallery policy |
| Photographer (authenticated user) | Partly trusted: trusted for own data only | Upload untrusted files, configure galleries, submit receipts |
| Staff / superuser | Trusted | Django admin (all models), payment approval API, bypasses plan limits |
| Celery workers | Trusted code, untrusted input | Decode images, run ffmpeg/ffprobe/cjpegli on uploads |
| Malicious photographer | Untrusted | Crafted media to attack workers; abuse of storage/email |
| Infra operator / host | Trusted | Env vars, Docker host, S3 bucket, DB |
| Third parties | Semi-trusted | AWS S3, AWS SES, Google Fonts, Unsplash (landing images), GitHub (build-time jpegli clone) |

## 4. Trust boundaries

| TB | Boundary | Controls present |
|---|---|---|
| TB1 | Internet → nginx SPA | CSP, X-Frame-Options, nosniff, Referrer-Policy (`frontend/nginx.conf:55-66`) |
| TB2 | Internet → Django API | Cookie JWT + CSRF, CORS allow-list, DRF throttles, permissions; production HTTPS settings (`production.py:200-252`) |
| TB3 | Public visitor → protected gallery | bcrypt password → `ClientSession` token; PIN → signed download token |
| TB4 | Photographer → another photographer's data | Every owner query filters `photographer=request.user` (`apps/galleries/views.py`, `apps/photos/views.py`) |
| TB5 | API → workers | Redis without auth, JSON serializer only (`base.py:236-238`) |
| TB6 | Uploaded file → decoders (Pillow, ffmpeg, ffprobe, cjpegli) | Magic bytes, size and pixel limits, ffprobe/cjpegli timeouts |
| TB7 | App → object storage | Private vs public storage classes, signed URLs for private |
| TB8 | Staff → platform | Django admin, `IsAdminUser` payment endpoints |
| TB9 | Build → image | `backend/Dockerfile`, `frontend/Dockerfile`, `.dockerignore` (frontend only) |

## 5. Entry points

Full list with methods, auth and throttle per route: [attack-surface.md](attack-surface.md). Summary:

- 18 public routes under `/api/v1/public/` (`apps/clients/urls.py`), all `AllowAny` with `authentication_classes = []`.
- Auth routes `/api/v1/auth/*` (`apps/users/urls.py`): register, login, refresh, reset, reset-confirm are anonymous.
- Owner routes under `/api/v1/galleries/`, `/api/v1/photos/`, `/api/v1/notifications/`, `/api/v1/subscriptions/`.
- `/admin/` (Django admin), `/health/`, `/api/total-users`, `/media/*` (only when `DEBUG=True`, `config/urls.py:37-38`).
- Multipart uploads: photos/videos (`/api/v1/photos/<slug>/upload/`), avatar/logo (`/api/v1/auth/me/`), receipts (`/api/v1/subscriptions/payments/`).
- Background: Celery beat schedule (`config/celery.py:35-77`).

---

## 6. Existing mitigations (verified in code)

These are present and were read in the source. They are listed so the gaps below are not over-stated.

| Control | Evidence |
|---|---|
| JWT in HttpOnly cookies, SameSite=Lax, 15 min access / 7 day refresh | `apps/users/views.py:40-71`, `base.py:132-142` |
| CSRF enforced on unsafe methods when the JWT came from a cookie | `apps/core/authentication.py:38-64` |
| Refresh rotation mints a new token and blacklists the old one | `apps/users/views.py:206-228` |
| Logout-all and password change/reset revoke all refresh tokens | `apps/users/views.py:323-340, 555-563`, `apps/users/utils.py:7` |
| Password validators (length 8, common, numeric, similarity) | `base.py:150-155` |
| Password reset is anti-enumeration (same 200 either way) | `apps/users/views.py:422-501` |
| Per-route throttles: login 5/min, unlock/PIN 5/min, reset 5/h, password change 10/h, browse 120/min | `base.py:98-128` (but see SEC-01) |
| Gallery password and PIN stored as bcrypt; PIN-change invalidates download tokens (fingerprint) | `apps/galleries/views.py:518, 591`, `apps/clients/download_access.py:340-372` |
| Unlock tokens from `secrets.token_hex(32)`; sessions expire (`CLIENT_SESSION_TTL_DAYS`=30) | `apps/clients/models.py:10-15`, `base.py:278` |
| Download tokens signed (Django `signing`, salted), 2 h TTL; file tokens bound to job/gallery/index | `apps/clients/download_access.py:348-460` |
| Tenant scoping on every owner and public query (gallery + photographer, asset + gallery, set + gallery) | e.g. `apps/galleries/views.py:203-206`, `apps/clients/views.py:216-228, 769-776` |
| Raw `resolution=original` refused for clients; Free clients get the 3600 px master | `apps/clients/views.py:117-132, 231-273` |
| Originals in a private-ACL storage class with 1 h signed URLs (S3) | `apps/core/storage.py:68-74` |
| Upload checks: magic bytes, admin-set size and pixel limits, Pillow bomb guard, ffprobe timeout 60 s, cjpegli timeout | `apps/core/utils.py:169-270`, `apps/subscriptions/upload_limits.py:45-53` |
| Subprocesses use argv lists, never a shell | `apps/core/utils.py:180, 511, 864-895` |
| GPS stripped from JPEG originals at upload | `apps/core/utils.py:272-330`, `apps/photos/views.py:265` |
| Production refuses to boot without a real SECRET_KEY, DB, S3 and sender | `production.py:23-125` |
| Production: DEBUG off, HSTS 1 y + preload, Secure cookies, SSL redirect, nosniff, X-Frame DENY | `production.py:8, 203-252` |
| SPA CSP (`script-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`) and security headers | `frontend/nginx.conf:55-97` |
| Unhandled API errors return a generic JSON 500 | `apps/core/middleware.py:41-61` |
| No raw SQL (only `SELECT 1` in the health check); no `dangerouslySetInnerHTML`/`innerHTML` in the SPA | `config/urls.py:15`; grep of `frontend/src` |
| `.env` files git-ignored; frontend `.dockerignore` keeps `.env*` out of the bundle | `.gitignore:16-21`, `frontend/.dockerignore` |
| Ready-email rate limits per email / IP / gallery; download count limits; ZIP size limits | `base.py:298-325`, `apps/clients/download_access.py:232-284` |
| Public portfolio hides staff accounts, private portfolios and protected galleries | `apps/clients/views.py:2020-2049` |

---

## 7. Threats, attack scenarios and findings

STRIDE category in brackets. Likelihood: how easy the attack is with the current code. Risk = severity after likelihood.

### SEC-01 — Throttle identity can be chosen by the client (X-Forwarded-For) [Spoofing / DoS]

- **Severity:** High
- **Classification:** Needs verification (library source and settings read; not reproduced)
- **Evidence:** `backend/config/settings/production.py:242` sets `NUM_PROXIES` as a top-level Django setting. DRF reads it only from `REST_FRAMEWORK` (`rest_framework/settings.py:65, 213-216`), where it is absent (`base.py:86-129`), so `api_settings.NUM_PROXIES` is `None`. With `None`, `BaseThrottle.get_ident` returns the whole `X-Forwarded-For` header when one is present (`rest_framework/throttling.py:29-40`, DRF 3.17.1). Separately, `_get_client_ip` takes the left-most XFF entry (`apps/clients/views.py:135-139`, `apps/clients/serializers.py:390-397`).
- **Attack scenario:** an attacker sends each login, gallery-unlock or PIN request with a different `X-Forwarded-For: <random>` header. Each request lands in a new throttle bucket, so the 5/min limits never trigger. In dev the API is reached directly on `:8000`; in production it depends on whether the proxy overwrites or appends XFF (proxy config not in repo).
- **Risk:** credential stuffing on photographer login, brute force of 4-digit download PINs and short gallery passwords (SEC-04), unlimited reset emails per target (5/h per bucket), throttle evasion for scraping. The IP stored on `ClientSession` and `DownloadLog` is also attacker-chosen (audit data is forgeable).
- **Affected location:** `production.py:236-242`, `base.py:86-129`, every view using `AnonRateThrottle`/`UserRateThrottle` subclasses, `apps/clients/views.py:135`, `apps/clients/serializers.py:390`, `apps/clients/ready_email.py:43-48`.
- **Likelihood:** High (one header). **Impact:** High.
- **Why it matters:** every brute-force control in the app is an IP-bucket throttle; this removes all of them at once.
- **Recommended fix:** put `NUM_PROXIES` inside `REST_FRAMEWORK`; make the production proxy overwrite (not append) `X-Forwarded-For` or use `X-Real-IP`; use one helper (DRF `get_ident`) for stored IPs; add a test that a spoofed XFF does not reset the login throttle. Debt row 78.

### SEC-02 — Any visitor can read, change and delete another visitor's favorite lists by typing their email [Spoofing / Info disclosure / Tampering]

- **Severity:** High
- **Classification:** Needs verification (code path read; confirms and widens debt row 5)
- **Evidence:** `_claimed_email` takes `?email=` or body `email` with format validation only (`apps/clients/views.py:638-646`). `known_emails` adds that claimed email to the caller's identity (`apps/clients/favorite_lists.py:87-100`) and `visitor_lists` then matches every list whose `email` equals it (`favorite_lists.py:103-112`). `get_visitor_list` uses the same set (`favorite_lists.py:217-222`) for GET, PATCH and DELETE of a list (`apps/clients/views.py:926-970`). In an open gallery `client_uid` is any string (`views.py:690-699`).
- **Attack scenario:** on an open gallery, call `GET .../favorites/lists/?client_uid=x&email=victim@example.com` to list the victim's lists, `GET .../favorites/lists/<id>/` to see the photos, then `DELETE` or `PATCH` them. Works on a protected gallery too once the attacker has the gallery password.
- **Risk:** disclosure of a client's selections (wedding/family proofing), destruction of a client's proofing lists the photographer relies on.
- **Affected location:** `apps/clients/favorite_lists.py:87-128, 217-222`; `apps/clients/views.py:638-970`.
- **Likelihood:** Medium (needs the victim's email and gallery link). **Impact:** Medium-High.
- **Why it matters:** row 5 describes "see"; the same path also allows rename, delete and adding photos to the victim's list.
- **Recommended fix:** never grant list access from a typed email; verify ownership by an emailed one-time link or code before merging lists across browsers; until then, match only `client_key`. Debt rows 5 and 79.

### SEC-03 — "Restrict downloads to specific contacts" trusts a typed, unverified email [Spoofing / Elevation]

- **Severity:** Medium
- **Classification:** Needs verification
- **Evidence:** `email_is_allowed` checks the typed email against the allow-list (`apps/clients/download_access.py:224-229`); the email comes from the request body with format validation only (`apps/clients/views.py:1063-1079`).
- **Attack scenario:** a visitor who knows (or guesses) one allowed contact's address types it and receives a download token.
- **Risk:** the photographer believes downloads are limited to named people; they are limited to anyone who knows one name on the list.
- **Affected location:** `download_access.py:224-229`, `apps/clients/views.py:1061-1100`.
- **Likelihood:** Medium. **Impact:** Medium.
- **Why it matters:** a privacy control that the UI presents as access control.
- **Recommended fix:** send a one-time code or magic link to the allowed address before issuing the token, or relabel the feature as a soft filter. Debt row 80.

### SEC-04 — Short download PIN / gallery password with no per-gallery lockout [Spoofing]

- **Severity:** Medium (High combined with SEC-01)
- **Classification:** Weakness
- **Evidence:** PIN accepted when `pin.isdigit() and 4 <= len(pin) <= 8` (`apps/galleries/views.py:585`); gallery password minimum 4 characters (`apps/galleries/views.py:473`). Failed attempts are limited only by the per-IP `password_unlock` throttle (`apps/clients/views.py:294-299, 590, 1000, 1121`); `pin_limit_reached` counts successes, not failures (`apps/clients/views.py:1039-1059`). No failure counter, backoff or alert exists.
- **Attack scenario:** 10,000 PIN values at 5/min/IP take about 33 h from one IP, minutes with SEC-01 or a small IP pool.
- **Risk:** download gate bypass; gallery password bypass for short passwords.
- **Affected location:** `apps/galleries/views.py:473, 585`; `apps/clients/views.py:1037-1059`; `apps/clients/download_access.py:329-337`.
- **Likelihood:** Medium. **Impact:** Medium.
- **Why it matters:** the PIN is the only gate on many galleries' downloads.
- **Recommended fix:** per-gallery failed-attempt counter with exponential backoff and a photographer notification; raise the password minimum; fix SEC-01 first. Debt row 81.

### SEC-05 — Original's storage key is derivable from any public display URL; privacy relies only on per-object ACL [Info disclosure]

- **Severity:** Medium (High if the bucket policy is ever made public on that prefix)
- **Classification:** Needs verification (bucket config is not in the repo)
- **Evidence:** originals and public tiers share one key pattern: `photographers/{photographer_id}/galleries/{gallery_id}/photos/{asset_id}_original{ext}` vs `..._display.webp` (`apps/photos/models.py:13-31`). Both storage classes use the same bucket (`apps/core/storage.py:68-83`); only `default_acl` differs (`private` vs `public-read`). Display URLs are handed to every visitor.
- **Attack scenario:** a visitor takes a display URL, swaps `_display.webp` for `_original.jpg`. On S3 this is blocked only while every original object keeps a private ACL and no bucket policy grants `s3:GetObject` on `photographers/*`. In dev it works today (SEC-06).
- **Risk:** full-resolution, unwatermarked originals of every gallery, bypassing download settings, PIN and plan caps.
- **Affected location:** `apps/photos/models.py:13-97, 212-255`; `apps/core/storage.py:68-84`; `base.py:198-209`.
- **Likelihood:** Low today in prod (needs a bucket misconfiguration), High in dev. **Impact:** High.
- **Why it matters:** one bucket-policy change (common when "making images public" for a CDN) would expose every original.
- **Recommended fix:** separate private and public buckets (or at least separate top-level prefixes with a deny policy on the private one); add a random component to private keys; document the required bucket settings (Block Public Access on the private bucket, Object Ownership). Verify on staging (15-A). Debt row 82.

### SEC-06 — Dev server serves every private file under `/media/` without auth [Info disclosure]

- **Severity:** Medium (dev / any DEBUG deployment)
- **Classification:** Needs verification (code read; not run)
- **Evidence:** `config/urls.py:37-38` adds `static(MEDIA_URL, document_root=MEDIA_ROOT)` when `DEBUG`; `development.py:5` sets `DEBUG = True`; without AWS keys both storage classes are plain `FileSystemStorage` on `MEDIA_ROOT` (`apps/core/storage.py:86-100`); compose publishes `8000:8000` on all host interfaces (`docker-compose.yml:97-98`).
- **Attack scenario:** anyone who can reach the dev host on port 8000 and has seen one display URL fetches `..._original.<ext>`, `..._download.<ext>` or a payment receipt (`payment_proofs/<user>/<uuid>.<ext>`).
- **Risk:** originals, masters and receipts readable on the LAN of any dev/QA machine; a DEBUG=True deploy would expose them publicly.
- **Affected location:** `config/urls.py:36-38`, `development.py:5`, `docker-compose.yml:97-98`.
- **Likelihood:** Medium for dev. **Impact:** Medium.
- **Why it matters:** violates the project rule "Originals stay private" in the environment where real QA photos live.
- **Recommended fix:** serve only the public storage directory in dev (or require auth for private paths); bind dev ports to `127.0.0.1`. Debt row 83.

### SEC-07 — Video stream returns the private original when no playback MP4 exists, ignoring allow_download [Info disclosure / Elevation]

- **Severity:** Medium
- **Classification:** Needs verification
- **Evidence:** `video_field = asset.playback_file if asset.playback_file else asset.original_file` then, on S3, `HttpResponseRedirect(video_field.url)` — a signed URL to the private original (`apps/clients/views.py:1742-1753`). The view does not check `allow_download` or READY state (`views.py:1712-1732`; the docstring at 1654-1664 says this is deliberate).
- **Attack scenario:** for a video whose transcode is pending or failed, any visitor of the gallery gets the full original video via `.../video/<id>/stream/`, plus the private storage key in the redirect URL.
- **Risk:** originals and private paths reach clients on galleries where downloads are off.
- **Affected location:** `apps/clients/views.py:1649-1758`.
- **Likelihood:** Low-Medium (only while processing or after a failed transcode). **Impact:** Medium.
- **Why it matters:** related to debt row 6 (original exposure) but on a different, public path.
- **Recommended fix:** stream only `playback_file`; answer 409 "still processing" otherwise. Debt row 84.

### SEC-08 — `original_url` in the owner media API exposes the private storage path (debt row 6)

- **Severity:** Low
- **Classification:** Weakness
- **Evidence:** `MediaAssetSerializer.original_url` returns `original_file.url` (`apps/photos/serializers.py:43, 61, 79-83`); used only by authenticated, owner-scoped views (`apps/photos/views.py:152, 358, 445, 477, 828, 852`). The public serializer does not include it (`apps/clients/serializers.py:31-64`).
- **Risk:** the owner (any plan) gets a signed URL to their own original; the key reveals the private path layout (feeds SEC-05). Clients do not receive it through this field, so row 6's "Free user must not reach Original" concern holds for clients on this path; SEC-07 and SEC-27 are the client-side exceptions.
- **Affected location:** `apps/photos/serializers.py:79-83`.
- **Recommended fix:** owner downloads of originals through an authenticated endpoint that streams or redirects on demand; drop `original_url` from list payloads. Already debt row 6 (7-B).

### SEC-09 — Public derivatives are public-read with permanent URLs [Info disclosure]

- **Severity:** Medium
- **Classification:** Weakness (design choice, documented in `apps/core/storage.py:19-37`)
- **Evidence:** `PublicMediaStorage`: `default_acl = "public-read"`, `querystring_auth = False`, `Cache-Control: public, max-age=31536000, immutable` (`apps/core/storage.py:76-84`). Applies to 2048 px display, 1280 px medium, thumbnails, video posters and the 1080p playback MP4 (`apps/photos/models.py:219-255`).
- **Attack scenario:** a former guest keeps the display/playback URLs. The photographer later adds a password, unpublishes, or lets the gallery expire. The URLs keep working (and stay in CDN/browser caches for a year) until the asset is purged.
- **Risk:** gallery-level access control does not apply to already-seen derivatives.
- **Affected location:** `apps/core/storage.py:76-84`.
- **Likelihood:** Medium. **Impact:** Medium (watermarked, max 2048 px / 1080p).
- **Recommended fix:** CDN signed cookies/URLs scoped per gallery, or key rotation (re-key derivatives) when a gallery's access changes; at minimum document the behaviour to photographers. Debt row 85.

### SEC-10 — Backend image build copies `backend/.env` and local folders into the image [Info disclosure]

- **Severity:** Medium
- **Classification:** Needs verification (no image was built or inspected)
- **Evidence:** `backend/.dockerignore` does not exist (only `frontend/.dockerignore`); `backend/Dockerfile:50` is `COPY . .` with build context `./backend` (`docker-compose.yml:70`). `backend/` contains `.env` (holds `SECRET_KEY`, `DB_*` names), `venv/`, `media/`, `logs/`, `celerybeat-schedule`, and a stray `C:` directory.
- **Risk:** anyone who can pull the image (registry, CI cache, a shared host) reads the dev secrets and any local media/logs baked into its layers.
- **Affected location:** `backend/Dockerfile:50`; missing `backend/.dockerignore`.
- **Likelihood:** Medium once images are pushed anywhere. **Impact:** Medium.
- **Recommended fix:** add `backend/.dockerignore` (`.env*`, `venv/`, `media/`, `logs/`, `__pycache__/`, `celerybeat-schedule*`, `C:/`, `staticfiles/`); rebuild and inspect a layer listing. Debt row 86.

### SEC-11 — Dev stack: hardcoded DB password, unauthenticated Redis, all ports on all interfaces [Spoofing / Tampering]

- **Severity:** Low (development only)
- **Classification:** Weakness (directly visible in tracked files)
- **Evidence:** the same 13-character DB password appears at `docker-compose.yml:38, 84, 129, 163, 193`, equals the dev fallback at `backend/config/settings/development.py:14`, and equals the DB name/user. Ports `5432` (line 43), `6379` Redis with no password (line 61), `8000` (98), `8025`/`1025` Mailpit (230-231) are published on all interfaces. Mailpit holds password-reset links. Redis/Mailpit tags float (`redis:alpine`, `axllent/mailpit:latest`, lines 59, 228).
- **Risk:** anyone on the same network as a dev machine can read/alter the dev DB, inject Celery tasks via Redis (JSON only, but any registered task with attacker arguments), or read reset links in Mailpit and take over dev accounts.
- **Recommended fix:** bind dev ports to `127.0.0.1:`; move the password to an untracked env file; require a Redis password even in dev. Debt row 87. Value is never repeated in these docs (see [secrets.md](secrets.md)).

### SEC-12 — Insecure `SECRET_KEY` fallback in base settings

- **Severity:** Low
- **Classification:** Weakness (mitigated)
- **Evidence:** `base.py:14` falls back to a public `django-insecure-` placeholder; `production.py:23-34` refuses to boot if the env var is missing or equals that placeholder. Development uses the fallback only if `backend/.env` lacks `SECRET_KEY` (it currently defines it).
- **Recommendation:** also fail in `development.py` when the fallback is used on a non-localhost host. No debt row (guard exists).

### SEC-13 — One `SECRET_KEY` signs everything; no rotation path [Spoofing]

- **Severity:** Medium
- **Classification:** Missing control
- **Evidence:** SimpleJWT HS256 with no `SIGNING_KEY` (defaults to `SECRET_KEY`, `base.py:132-142`); download, job-link and file tokens via `django.core.signing` (`download_access.py:348-460`); password-reset tokens (`apps/users/views.py:473`). No `SECRET_KEY_FALLBACKS` anywhere in `backend/config`.
- **Risk:** a leaked key lets an attacker mint a JWT for any user id (full account takeover, incl. staff on the API) and download tokens for any gallery. Rotating the key today logs everyone out and kills every emailed download link at once, which discourages rotation.
- **Recommended fix:** separate `SIMPLE_JWT['SIGNING_KEY']`; adopt `SECRET_KEY_FALLBACKS` for zero-downtime rotation; write a rotation runbook. Debt row 88.

### SEC-14 — Gallery unlock tokens stored in plaintext and accepted in URLs [Info disclosure]

- **Severity:** Low
- **Classification:** Weakness
- **Evidence:** `ClientSession.access_token` is a plaintext indexed column (`apps/clients/models.py:61-86`), shown read-only in Django admin (`apps/clients/admin.py:37`). Tokens are accepted as `?token=` (`apps/clients/views.py:431, 536, 674, 1152, 1420, 1818`); the photo download and video stream require it in the URL (`views.py:1818`, docstring 1666-1670). Frontend keeps tokens in `sessionStorage` (`frontend/src/store/clientStore.js:22-60`).
- **Risk:** a DB/backup read or staff account yields live gallery access; tokens in URLs land in proxy/access logs and browser history.
- **Recommended fix:** store a SHA-256 of the token; prefer header/POST; keep `Referrer-Policy` (already `strict-origin-when-cross-origin`). Debt row 89.

### SEC-15 — Django admin hardening missing [Spoofing / Elevation]

- **Severity:** Medium
- **Classification:** Missing control
- **Evidence:** `/admin/` at the default path (`config/urls.py:25`); DRF throttles do not apply to Django admin views; no lockout package in `requirements.txt`; no MFA. Admin exposes plans, upload limits, subscriptions, payments, sessions (with tokens) and gallery rows (the change form shows every model field, incl. the password/PIN hashes, since `apps/galleries/admin.py` declares no `fields`/`exclude`).
- **Risk:** password guessing against staff accounts without throttle (and SEC-01 does not even matter here); one staff compromise = whole platform.
- **Recommended fix:** rate-limit/lock admin login, MFA for staff, restrict `/admin/` by network or move it, exclude hash/token fields from admin forms. Debt row 90.

### SEC-16 — No email verification on registration [Spoofing]

- **Severity:** Low
- **Classification:** Missing control
- **Evidence:** `RegisterView` creates the user and sets session cookies immediately (`apps/users/views.py:78-101`); no verification flag or email.
- **Risk:** accounts under someone else's address (impersonation of a studio in emails sent "from" that studio's display name, spam via share/ready emails).
- **Recommended fix:** verify email before publishing galleries or sending client emails. Debt row 91.

### SEC-17 — Refresh endpoint shares the anonymous 100/day bucket [DoS]

- **Severity:** Low
- **Classification:** Needs verification
- **Evidence:** `CookieTokenRefreshView` has `authentication_classes = []` and no `throttle_classes` (`apps/users/views.py:175-183`), so the defaults apply: `anon 100/day` per IP (`base.py:99-104`). One active user refreshes about 96 times a day (15 min access lifetime).
- **Risk:** several users behind one NAT exhaust the bucket and are logged out; conversely the endpoint has no dedicated abuse limit.
- **Recommended fix:** a dedicated `refresh` scope keyed on the refresh token's user id. Debt row 92.

### SEC-18 — ffmpeg runs without a timeout on uploaded videos [DoS]

- **Severity:** Low
- **Classification:** Weakness
- **Evidence:** poster extraction and playback transcode call `subprocess.run(...)` with no `timeout` (`apps/core/utils.py:868, 895`); ffprobe has one (line 191).
- **Risk:** a crafted or pathological video can hold a Celery worker indefinitely; repeated uploads starve the queue.
- **Recommended fix:** timeouts proportional to duration, Celery `time_limit`/`soft_time_limit`. Debt row 93.

### SEC-19 — Location metadata can reach clients [Privacy]

- **Severity:** Low
- **Classification:** Weakness
- **Evidence:** `strip_exif_gps` logs and keeps the original when stripping fails (`apps/core/utils.py:329`); only JPEG EXIF is handled; videos are stored and served as-is (stream fallback SEC-07, High Resolution for video serves the original: `apps/clients/views.py:244-245`).
- **Recommended fix:** refuse or quarantine on strip failure; strip `©xyz`/location atoms from video originals or from what is served. Debt row 94.

### SEC-20 — Production CSP carries dev origins and inline styles [XSS hardening]

- **Severity:** Low
- **Classification:** Weakness
- **Evidence:** one `nginx.conf` for every build; CSP allows `http://localhost:8000` in `img-src`, `media-src`, `connect-src` and `style-src 'unsafe-inline'` (`frontend/nginx.conf:66, 77, 97`); no `server_tokens off;`. The header comment at lines 41-45 still says no CSP is set (debt row 37).
- **Recommended fix:** template the CSP per environment; drop localhost in production. Debt row 95.

### SEC-21 — Container and supply-chain hygiene [Tampering]

- **Severity:** Low
- **Classification:** Weakness / Missing control
- **Evidence:** backend runtime image has no `USER` (runs as root, `backend/Dockerfile:28-105`); base images by tag, not digest (`python:3.12-slim`, `node:20-alpine`, `nginx:1.27-alpine`, `postgres:16`); `bcrypt` unpinned and `django-ses>=4.0.0` (`backend/requirements.txt:37, 40`); jpegli cloned from GitHub at build time (pinned commit, debt row 53); no `.github/` or other CI, no `pip-audit`/`npm audit` step. Frontend uses caret ranges (`frontend/package.json`) with a lock file.
- **Recommended fix:** non-root user; pin digests; pin all Python deps; add a dependency-audit step. Debt row 96.

### SEC-22 — No security event logging or alerting [Repudiation]

- **Severity:** Medium
- **Classification:** Missing control
- **Evidence:** `LOGGING` has a console handler and a local `django.log` file at WARNING (`base.py:335-379`). Failed logins, failed unlock/PIN attempts, admin actions outside Django's own log, and throttle hits are not logged. No error tracker in `requirements.txt`. Logs inside a container are lost on recreate.
- **Recommended fix:** structured security events (auth failures, PIN failures, 429s, payment approvals), shipped off-host with alerts. Debt row 97.

### SEC-23 — Personal-data lifecycle [Privacy]

- **Severity:** Low
- **Classification:** Missing control
- **Evidence:** no account-deletion or data-export endpoint in `apps/users/urls.py`; client IP + email kept 365 days in `DownloadLog` (`base.py:310`) and 30 days in `ClientSession` (`base.py:278`); favorites keep emails and names; Terms/Privacy pages missing (debt row 25).
- **Recommended fix:** owner decides retention; add deletion/export; publish a privacy policy. Debt row 98.

### SEC-24 — (merged into SEC-01): stored client IPs are attacker-chosen.

### SEC-25 — QA credentials and old example values in git [Secrets]

- **Severity:** Info
- **Classification:** Weakness
- **Evidence and fix:** see [secrets.md](secrets.md) §6 (QA script plaintext gallery password/PIN, `.env.example` history). Debt row 102.

### SEC-26 — `test_s3_connection` prints a presigned URL [Secrets]

- **Severity:** Info
- **Classification:** Weakness
- **Evidence:** `apps/core/management/commands/test_s3_connection.py:49` writes the probe file's URL (a SigV4 URL includes the access key ID and a signature) to stdout. Debt row 102.

### SEC-27 — Single-photo download does not require READY [Elevation]

- **Severity:** Low
- **Classification:** Needs verification
- **Evidence:** `MediaAsset.objects.get(id=photo_id, gallery=gallery)` with no status filter (`apps/clients/views.py:1838`); for `resolution=web` without a cached Web Size, `_resolve_web_source` falls back to `original_file` (`views.py:148-166, 1919-1922`), which is then served.
- **Attack scenario:** needs the UUID of a non-READY asset (public payloads list READY assets only), so likelihood is low.
- **Recommended fix:** require READY for client downloads. Debt row 99.

### SEC-28 — Auth cookies scoped to every `*.kyapture.com` subdomain [Spoofing]

- **Severity:** Low
- **Classification:** Needs verification (DNS/hosting not in repo)
- **Evidence:** `SESSION_COOKIE_DOMAIN` default `.kyapture.com` (`production.py:207`) is also the domain of `access_token`/`refresh_token` (`apps/users/views.py:48-70`) and the CSRF cookie (`production.py:214`); `ALLOWED_HOSTS` falls back to `.kyapture.com` (`production.py:157-160`).
- **Risk:** any subdomain that serves user-controlled content or is taken over receives the JWT cookies.
- **Recommended fix:** host-only cookies on the API host, or keep every subdomain first-party and monitored. Debt row 100.

### SEC-29 — Reference screenshots already pushed (contradicts the condition in debt row 39)

- **Severity:** Medium
- **Classification:** Needs verification (image contents not opened)
- **Evidence:** 11 files under `docs/pixieset-ref/` are tracked (`git ls-files`) and present on `origin/feature/landing-page-redesign` (`git ls-tree`), added in `a451f8f`, `c867f6d`, `af0653c`. Row 39 says "blur before the first push of that folder". Whether the remote is public is unknown.
- **Recommended fix:** owner inspects the 11 files; if any show an IP/email, blur and rewrite branch history before any merge to `main`. Debt row 101.

---

## 8. Risk summary

| ID | Title | Severity | Classification | Debt row |
|---|---|---|---|---|
| SEC-01 | XFF-chosen throttle identity | High | Needs verification | 78 |
| SEC-02 | Favorites by typed email (read/edit/delete) | High | Needs verification | 5, 79 |
| SEC-03 | Contact allow-list trusts typed email | Medium | Needs verification | 80 |
| SEC-04 | Short PIN/password, no lockout | Medium | Weakness | 81 |
| SEC-05 | Original key derivable, shared bucket | Medium | Needs verification | 82 |
| SEC-06 | Dev `/media/` serves private files | Medium | Needs verification | 83 |
| SEC-07 | Video stream falls back to original | Medium | Needs verification | 84 |
| SEC-08 | `original_url` in owner API | Low | Weakness | 6 |
| SEC-09 | Permanent public derivative URLs | Medium | Weakness | 85 |
| SEC-10 | No backend `.dockerignore` | Medium | Needs verification | 86 |
| SEC-11 | Dev creds/ports/Redis | Low | Weakness | 87 |
| SEC-12 | Insecure SECRET_KEY fallback (guarded) | Low | Weakness | — |
| SEC-13 | One signing key, no rotation | Medium | Missing control | 88 |
| SEC-14 | Plaintext unlock tokens, tokens in URLs | Low | Weakness | 89 |
| SEC-15 | Django admin hardening | Medium | Missing control | 90 |
| SEC-16 | No email verification | Low | Missing control | 91 |
| SEC-17 | Refresh in anon 100/day bucket | Low | Needs verification | 92 |
| SEC-18 | ffmpeg without timeout | Low | Weakness | 93 |
| SEC-19 | Location metadata | Low | Weakness | 94 |
| SEC-20 | CSP dev origins | Low | Weakness | 95 |
| SEC-21 | Container/supply chain | Low | Weakness | 96 |
| SEC-22 | No security logging/alerting | Medium | Missing control | 97 |
| SEC-23 | PII lifecycle | Low | Missing control | 98 |
| SEC-25/26 | Secret hygiene (QA values, S3 command) | Info | Weakness | 102 |
| SEC-27 | Non-READY download fallback | Low | Needs verification | 99 |
| SEC-28 | Wildcard cookie domain | Low | Needs verification | 100 |
| SEC-29 | Screenshots pushed | Medium | Needs verification | 101 |

No finding is labelled **Confirmed vulnerability**: nothing was executed, and no committed production secret was found (see [secrets.md](secrets.md)).
Existing debt rows that are security-relevant are cross-checked in [security-checklist.md](security-checklist.md) §21.
