# KYAPTURE attack surface (SEC-0)

Everything an outsider, a client, a photographer or a compromised component can reach, taken from the code at commit
`469fb66`. Routes come from `backend/config/urls.py` and each app's `urls.py`; auth/throttle from each view class.
Finding IDs (SEC-xx) are defined in [threat-model.md](threat-model.md). Nothing was run; runtime facts are marked
**needs verification**.

**Current state (7-E, 2026-10-07).** The tables below were brought up to date with the code after 7-A, 7-B, 7-C and 7-D:
a finding that was fixed is marked with the chunk that fixed it; anything still open names its debt row. Rows changed
in 7-E name files and functions; line numbers left from SEC-0 point at `469fb66` and may have shifted. Final status of every item:
[docs/qa-7e/results.md](../qa-7e/results.md) section 4.

Throttle names map to `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES` (`backend/config/settings/base.py`):
`login` 5/min, `login_account` 20/h, `register` 10/h, `token_refresh` 60/h per user, `password_unlock` 5/min,
`password_reset` 10/h per client, `password_reset_email` 3/h per address, `password_reset_confirm` 30/h,
`password_change` 10/h, `public_gallery_browse` 120/min, `video_preflight` 60/min, `feedback` 5/h, defaults `anon` 100/day
and `user` 1000/h. Since 7-B the client address comes from `REST_FRAMEWORK['NUM_PROXIES']` (0 in dev, 1 in production;
`apps/core/request_ip.client_ip`), so a client-sent `X-Forwarded-For` no longer picks the bucket (SEC-01 fixed), and every
count is shared in Redis across processes (row 108). Wrong gallery passwords/PINs also lock per client and per gallery
(`apps/clients/lockout.py`).

---

## 1. Public (unauthenticated) endpoints

### 1.1 Client gallery API — `/api/v1/public/` (`apps/clients/urls.py`, `apps/clients/views.py`)

Every view: `permission_classes = [AllowAny]`, `authentication_classes = []` (no cookies read, so no CSRF).
Every gallery lookup requires `is_published=True`, `is_active=True`, not expired, and `photographer__username` = path.

| # | Method + path | View (line) | Throttle | Gate / input | Notes |
|---|---|---|---|---|---|
| P1 | `GET {u}/` | `PublicPhotographerPortfolioView` (1991) | browse | username | Hides staff, private portfolios, protected galleries (2020-2049) |
| P2 | `GET {u}/{slug}/` | `PublicGalleryView` (332) | browse | `Authorization: Bearer` or `?token=` for protected | Returns title + color only when locked (456-461) |
| P3 | `GET {u}/{slug}/photos/` | `PublicGalleryPhotosView` (498) | browse | same token; `?page`, `?set` | READY assets only |
| P4 | `POST {u}/{slug}/unlock/` | `GalleryUnlockView` (582) | password_unlock | body `password`, `email` | bcrypt check, creates a `ClientSession` (token stored hashed); failure lockout per client and per gallery (7-B) |
| P5 | `POST {u}/{slug}/download-access/` | `PublicDownloadAccessView` (973) | password_unlock | `pin`, `email`, `token` | Issues 2 h `download_token`; a listed contact must first enter an emailed one-time code; PIN failures lock out (7-B) |
| P6 | `POST {u}/{slug}/download/` | `PublicGalleryDownloadView` (1103) | password_unlock | `download_token`/`pin`, `resolution`, `set_id(s)`, `asset_ids`, `email` | Creates a `DownloadJob`, queues Celery, may send email |
| P7 | `GET {u}/{slug}/download-jobs/{uuid}/` | `PublicDownloadJobStatusView` (1439) | browse | job key in the `X-Download-Link-Key` header (7G; `?link_token=` refused) or `download_token` (+ unlock token) | Returns signed file URLs |
| P8 | `GET {u}/{slug}/download-jobs/{uuid}/files/{i}/` | `PublicDownloadJobFileView` (1524) | browse | `file_token` | Streams ZIP from private storage; may redirect to `FRONTEND_URL` |
| P9 | `GET {u}/{slug}/download-all/` | `PublicGalleryDirectDownloadView` (1338) | browse | — | Always 410 |
| P10 | `GET {u}/{slug}/video/{uuid}/stream/` | `PublicVideoStreamView` (1649) | browse | unlock token in query (row 133, accepted) | Playback MP4 only, else 409 `video_processing` (7-B; SEC-07 fixed) |
| P11 | `GET {u}/{slug}/photo/{uuid}/download/` | `PublicPhotoDownloadView` (1761) | browse (+ password_unlock when `?pin=`) | `token`, `download_token`, `pin`, `resolution`, `check` | READY assets only; Web Size never falls back to the original (7-B; SEC-27 fixed) |
| P12 | `GET POST DELETE {u}/{slug}/favorites/` | `GalleryFavoritesView` (702) | browse | `client_uid` or unlock token, `email`, `name`, `list_id`, `media_asset_id` | A list belongs to the client key only; an email is a label (7-A; SEC-02 fixed) |
| P13 | `GET POST {u}/{slug}/favorites/lists/` | `GalleryFavoriteListsView` (872) | browse | as P12, `name`, `sort` | Max lists per visitor |
| P14 | `GET PATCH DELETE {u}/{slug}/favorites/lists/{uuid}/` | `GalleryFavoriteListDetailView` (916) | browse | as P12 | Own lists only (7-A) |

### 1.2 Other anonymous endpoints

| # | Method + path | Where | Auth / throttle | Notes |
|---|---|---|---|---|
| A1 | `POST /api/v1/auth/register/` | `apps/users/views.py:78` | AllowAny, no auth classes; `register` 10/h per address (7-B) | No email verification (SEC-16, row 91: RS0-D); sets JWT cookies |
| A2 | `POST /api/v1/auth/login/` | `apps/users/views.py:115` | `login` 5/min per address + `login_account` 20/h per account (7-B) | Generic error; JWT carries `tv` (7-C) |
| A3 | `POST /api/v1/auth/token/refresh/` | `apps/users/views.py:175` | `token_refresh` 60/h per verified user (7-B; SEC-17 fixed) | Reads `refresh_token` cookie; SameSite=Lax is the CSRF defence; refused after a revocation (`tv`, 7-C) |
| A4 | `POST /api/v1/auth/password/reset/` | `apps/users/views.py` (7-C) | `password_reset` 10/h per client; `password_reset_email` 3/h per address (silent) | Same answer and 0 queries for any address; a Celery task looks the account up and mails a `FRONTEND_URL/reset-password#token=` link |
| A4b | `POST /api/v1/auth/password/reset/check/` | `apps/users/views.py` (7-C) | `password_reset_confirm` 30/h | `token` in the body; 200 or one `reset_link_invalid`; does not use the link up |
| A5 | `POST /api/v1/auth/password/reset/confirm/` | `apps/users/views.py` (7-C) | `password_reset_confirm` 30/h | `token` + new password in the body; one `reset_link_invalid` answer (the uid oracle is gone); success revokes every session |
| A6 | `GET /api/v1/subscriptions/plans/` | `apps/subscriptions/views.py:28` | AllowAny; defaults | Public price list |
| A7 | `GET /api/total-users` | `apps/users/views.py:377` | browse | Count + 5 initials/colours |
| A8 | `GET /health/` | `config/urls.py:11-19` | plain Django view, **no throttle** | Runs `SELECT 1`; cheap but unthrottled |
| A9 | `/admin/` | `config/urls.py:25` | Django session login; 5 failures per address / 10 per account lock for 15 min (`apps/core/admin_login.py`, 7-B) | No MFA, no network restriction (row 90). See §8 |
| A10 | `GET /media/<path>` | `config/urls.py:37-38` | only when `DEBUG=True` | Public derivative names only; private files (originals, masters, receipts) need a signed 1-hour URL (`apps/core/media.py`, 7-B; SEC-06 fixed) |

## 2. Authenticated (photographer) endpoints

Default auth `CookieJWTAuthentication` (cookie first, then `Authorization: Bearer`; CSRF on unsafe methods for cookie auth,
`apps/core/authentication.py:17-64`), default permission `IsAuthenticated`, default throttle `user` 1000/h.
Object access is scoped by `photographer=request.user` or `gallery__photographer=request.user` in every view below.

| Area | Routes | Source |
|---|---|---|
| Account | `GET PUT /auth/me/` (profile, avatar, logo multipart), `PUT /auth/change-password/` (`password_change` 10/h), `POST /auth/logout/`, `POST /auth/logout-all/`, `GET PATCH /auth/settings/` (unknown keys rejected) | `apps/users/urls.py`, `views.py:146-362` |
| Notifications | `GET /notifications/`, `GET unread-count/`, `POST read-all/`, `POST {uuid}/read/` | `apps/users/notification_urls.py`, `notification_api.py:49-95` |
| Galleries | `GET POST /galleries/`, `GET search/?q=`, `GET dashboard/stats/`, `POST {slug}/publish/`, `POST {slug}/set-password/`, `POST {slug}/set-download-pin/`, `GET {slug}/favorites/`, `GET {slug}/download-logs/`, `GET PUT PATCH DELETE {slug}/` | `apps/galleries/urls.py`, `views.py` |
| Photos | `POST video-preflight/` (60/min), `POST {slug}/upload/` (multipart), `POST {slug}/delete-bulk/`, `PATCH {slug}/reorder/`, `GET {slug}/status/`, `PATCH {slug}/move/`, `PATCH {slug}/sets/reorder/`, `PATCH DELETE {slug}/sets/{uuid}/`, `GET POST {slug}/sets/`, `GET {slug}/`, `PUT photo/{uuid}/favorite/`, `GET favorites/all/`, `GET DELETE photo/{uuid}/` | `apps/photos/urls.py`, `views.py` |
| Subscriptions | `GET my-subscription/`, `GET me/` (alias), `GET POST payments/` (receipt multipart) | `apps/subscriptions/urls.py`, `views.py:45-145` |

Owner responses include `original_url` for every asset: a 1-hour signed URL to a key with a 128-bit random part (7-B; SEC-08 fixed). Public payloads never carry it.

## 3. Internal endpoints and channels

| Channel | Exposure | Notes |
|---|---|---|
| Redis broker/results (`base.py:232-233`) | Dev: published `6379` on all interfaces, **no password** (`docker-compose.yml:58-61`) | Anyone who reaches it can enqueue registered tasks with chosen arguments (JSON only, `base.py:236-238`) |
| PostgreSQL | Dev: published `5432`, hardcoded password (SEC-11). Prod: env vars, **no `sslmode`** in `DATABASES` (`production.py:64-79`) | TLS to the DB depends on the host default (needs verification) |
| Celery beat tasks (`config/celery.py:35-77`) | Internal | Subscription sweep (15 min), gallery purge, session/log/job/notification purge, JWT blacklist flush |
| Celery work on uploads | Internal, untrusted input | Pillow decode, ffprobe, ffmpeg and cjpegli all with timeouts; photo task Celery limits 600/660 s (7-B). Video/Web Size/ZIP tasks have no Celery time limit (row 139) |
| Mailpit (dev) | `8025` web inbox + `1025` SMTP on all interfaces (`docker-compose.yml:227-231`) | Holds reset links and download links |
| Management commands | Shell access only | `backfill_*`, `purge_orphans`, `test_s3_connection` (prints a presigned URL, SEC-26) |

## 4. Authentication and authorization surfaces

| Surface | Mechanism | Evidence | Gaps |
|---|---|---|---|
| Photographer login | email + password → JWT pair in HttpOnly SameSite=Lax cookies | `apps/users/views.py` | No MFA; no email verification (SEC-16) |
| Session refresh | refresh cookie, rotation + blacklist | `apps/users/views.py` | None left (own throttle since 7-B) |
| CSRF | `CSRFCheck` on unsafe methods for cookie JWT; `CSRF_TRUSTED_ORIGINS` per env | `apps/core/authentication.py:45-64`, `development.py:30-35`, `production.py:179-184` | Header-token requests (`Authorization: Bearer`) skip CSRF, correctly |
| Gallery password | bcrypt → `ClientSession` token (64 hex, 30 days) | `apps/clients/serializers.py:334-408` | Token hashed at rest (7-B); still accepted as `?token=` for `<a href>`/`<video src>` (row 133, accepted in 7-E); 4-char minimum (row 135) |
| Download PIN / email | bcrypt PIN → signed `download_token` (2 h) | `apps/clients/download_access.py:329-387` | 4-digit minimum (row 135); lockout and the emailed contact code since 7-B |
| Job link / file tokens | Django `signing`, bound to job + gallery (+ index) | `download_access.py:389-487` | Bearer links in URLs and email by design |
| Favorites identity | client key (`client_uid`, else the unlock token's hash); an email is only a label (7-A) | `apps/clients/views.py:649-699`, `favorite_lists.py:87-128` | A typed email no longer links two devices (row 129, accepted) |
| Plan entitlement | server-side `require_feature`, metrics, limits under row lock | `apps/users/serializers.py:86-111`, `apps/photos/views.py:186-255` | Fixed in 7-B (rows 43, 44) |
| Staff | `is_staff` → Django admin, `IsAdminUser` payment API, the staff area `/api/v1/staff/` (7.5-A: users list, suspend / reactivate, audit log; `IsStaffUser`, throttled, audited), unlimited plan | `apps/subscriptions/views.py:109, 154, 189`, `apps/galleries/views.py:106`, `apps/photos/views.py:192` | No MFA (row 90); admin login lock since 7-B |

## 5. User inputs

| Input | Where accepted | Validation present |
|---|---|---|
| Username, display name, bio, phone, website, branding colour | register, `/auth/me/` | Regex, reserved names, `sanitize_text` (bleach), hex colour (`apps/users/serializers.py:44-80, 150-187`) |
| Gallery title, description, settings JSON, watermark text | `/galleries/` create/update | Serializers in `apps/galleries/serializers.py`. `design_settings` checked in 7-E: presentation keys, `watermark`, `downloads`, `privacy`, `coverPhoto` are validated; unknown top-level keys are stored as sent (owner-only); the public payload is an allow-list re-validated on read. A partial `downloads` block resets the keys it omits (row 152) |
| Collection defaults, notification/privacy settings | `/auth/settings/` | `_StrictSerializer` rejects unknown keys (`apps/users/serializers.py:288-361`) |
| Search `?q=` | `/galleries/search/` | ORM filters only (no raw SQL anywhere) |
| IDs (UUID path params, `asset_ids`, `set_ids`, `list_id`) | public + owner | UUID converters / `UUIDField` lists; scoped to gallery (`apps/clients/views.py:1263-1296`) |
| Emails (client) | unlock, download-access, download, favorites | `validate_email`, max length (`download_access.py:309-326`, `favorite_lists.py:45-60`) |
| Visitor name, list name | favorites | `clean_visitor_name`, `clean_list_name` (80 chars) |
| Gallery password, PIN | owner set endpoints | ≥ 4 chars and ≤ 72 bytes; PIN 4-8 digits (`apps/galleries/views.py:459-591`) |
| `resolution`, `sort`, `page`, `set` query params | public | Allow-lists (`apps/clients/views.py:117-132, 885, 939`) |
| Request headers | `X-Forwarded-For` read only through `NUM_PROXIES` (7-B); `Accept` decides HTML redirect (P8) | — |

Output encoding: React escapes by default and the SPA has no `dangerouslySetInnerHTML`/`innerHTML`/`eval`; HTML emails
use Django templates with autoescape (only `download_ready.txt` turns it off, plain text).

## 6. File uploads

| Upload | Endpoint | Checks | Storage |
|---|---|---|---|
| Photos (JPEG/PNG) | `POST /photos/{slug}/upload/` field `image` | Admin size limit (`UploadLimits`, default 100 MB) and pixel limit (144 MP) before decode; magic bytes `FF D8` / PNG; Pillow bomb guard follows the limit; location removed, fail closed (7-B; 0 of 103 real JPEGs refused in 7-E); storage + plan checks under a row lock | Original → private; tiers → public |
| Videos (MP4/MOV) | same, field `video` | Size limit (default 2048 MB); `ftyp` box check (`utils.py:231-250`); ffprobe duration (timeout); plan minutes re-checked under the account lock (7-B); location remuxed out of the original (7-B) | Original → private; poster + 1080p MP4 → public |
| Avatar, logo | `PUT /auth/me/` | Pillow validation and re-encode (`apps/core/branding.py`); logo needs Branding entitlement before parse (`apps/users/serializers.py:86-111`) | Public storage |
| Payment receipt | `POST /subscriptions/payments/` | 5 MB, Pillow `verify()`, model `ImageField` extension validator (`apps/subscriptions/serializers.py:143-175`) | Default storage: private + signed in prod (`base.py:198-209`); `payment_proofs/{user}/{uuid}{ext}` |
| Watermark logo use | derived from the logo | — | — |

Body limits: since 7-B a body above the largest file limit (413) or from an account with no storage left (403) is refused from
its headers before a byte is read; otherwise the body is received before the remaining checks (pixel limit, video length:
rows 31, 75). The production proxy limit is a plan in `docs/KYAPTURE_UPLOAD_LIMITS.md`, not deployed config (rows 73, 54);
gunicorn still has the default 30 s timeout (row 72). Django's `DATA_UPLOAD_MAX_*` settings are left at defaults.

## 7. Database and storage

- ORM only; `config/urls.py:15` `SELECT 1` is the only raw SQL. No `.raw()`, `.extra()`, `RawSQL`.
- Every container runs `manage.py migrate` at start with the app's own DB credentials (`backend/docker-entrypoint.py:85-118`), so the runtime DB user needs DDL rights (no least-privilege split). Needs verification on the production DB (debt row 103).
- No DB TLS option in settings (debt row 103).
- Storage layout and privacy: [threat-model.md](threat-model.md) SEC-05, SEC-06, SEC-09. Private objects: originals, Download Masters, Web Size cache, ZIP parts, receipts. Public objects: WebP tiers, posters, playback MP4, avatars, logos. Same bucket and `photographers/{id}/galleries/{id}/` prefix for private and public media, but since 7-B a private key carries a 128-bit random part (not derivable from a public URL) and public keys carry the gallery's `media_token`, which rotates when the gallery is closed. Bucket policy / Block Public Access to verify on staging (15-A).
- Signed URL lifetime: 1 h (`apps/core/storage.py:72-73`, `production.py:261-262`).

## 8. Admin surfaces

| Surface | Access | What it controls |
|---|---|---|
| Django admin `/admin/` (default path) | `is_staff` | Users (`UserAdmin`; a password set here revokes every session, 7-C), galleries and client sessions (password/PIN hashes and tokens excluded since 7-B), media assets, subscription plans, `UploadLimits`, user subscriptions, manual payments (`apps/*/admin.py`) |
| `/api/v1/staff/users/`, `/staff/users/{id}/suspend|reactivate/`, `/staff/audit/` | `IsStaffUser` (`is_staff`, active) | 7.5-A: user list (allowlisted fields, exact-email search, 25 per page, 60/min), suspend / reactivate (reason, sessions revoked, galleries 404), append-only audit log. Not for staff targets or self. Docs: [KYAPTURE_STAFF.md](../KYAPTURE_STAFF.md) |
| `GET /api/v1/subscriptions/admin/payments/` | `IsAdminUser` | Pending payment queue |
| `POST /api/v1/subscriptions/payments/{uuid}/review/` | `IsAdminUser` | Approve/reject → creates/extends subscriptions (`apps/subscriptions/views.py:176-260`) |
| `GET /api/v1/subscriptions/payments/` as staff | `is_staff` | Every user's payments with receipt URLs (`views.py:108-128`) |
| Staff accounts in the product | `is_staff`/`is_superuser` | Bypass gallery, storage and video limits (`apps/galleries/views.py:106`, `apps/photos/views.py:192, 400`) |

Present since 7-B: login throttle and lock. Missing: MFA, IP restriction (row 90), admin action alerting (row 97).

## 9. Webhooks

None. There is no payment gateway, email-event or storage-event webhook in the code; payments are manual receipts
reviewed by staff. (If SES bounce/complaint handling or a gateway is added, it becomes a new signed-webhook surface.)

## 10. Third-party integrations

| Service | Used for | Trust / exposure |
|---|---|---|
| AWS S3 | All media in production (`django-storages`, `boto3`) | One key pair, also used by SES (secrets.md §1.1) |
| AWS SES | Transactional email in production (`django-ses`, `production.py:127-144`) | Sends as `DEFAULT_FROM_EMAIL` |
| Unsplash | Landing images (CSP `img-src https://images.unsplash.com`) | Third-party request |
| GitHub | `git clone google/jpegli` at image build (`backend/Dockerfile:14-18`, pinned commit) | Build-time supply chain (row 53) |
| Docker Hub, PyPI, npm | Base images and packages | Tags not digests; `bcrypt`, `django-ses` unpinned (SEC-21) |
| Mailpit | Dev mail catcher only | Never in production |

## 11. Network and deployment exposure

| Component | Dev compose (`docker-compose.yml`) | Production |
|---|---|---|
| SPA nginx | `3000:80` (line 217); HTTP only | Not in repo; CSP includes `http://localhost:8000` (SEC-20) |
| Django | `8000:8000` runserver, `DEBUG=True` (lines 72, 98) | Image CMD gunicorn 3 workers, default timeout (`backend/Dockerfile:105`), runs as root (SEC-21) |
| Postgres | `5432:5432` (43) | Not in repo |
| Redis | `6379:6379`, no auth (61) | Not in repo |
| Mailpit | `8025`, `1025` (230-231) | n/a |
| TLS, HSTS at edge, body size, XFF overwrite | none (HTTP) | Proxy not in repo (row 73); Django sets HSTS/SSL redirect (`production.py:217-247`) |
| Host header | `ALLOWED_HOSTS` `localhost`, `127.0.0.1` | env or fallback `.kyapture.com` wildcard; `USE_X_FORWARDED_HOST = True` (`production.py:157-160, 234`) — host header trust depends on the proxy (needs verification) |

Docker publishes these ports on all host interfaces unless bound to `127.0.0.1`; whether the host firewall blocks them
is a runtime fact (needs verification).

## 12. Dependencies and other externally reachable surfaces

- Backend (`backend/requirements.txt`): Django 6.0.5, djangorestframework 3.17.1, djangorestframework_simplejwt 5.5.1, PyJWT 2.13.0, django-cors-headers 4.9.0, Pillow 12.2.0, gunicorn 26.0.0, celery 5.6.3, redis 8.0.0, psycopg2-binary 2.9.12, django-storages 1.14.4, boto3 1.35.0, whitenoise 6.12.0, bleach 6.4.0, piexif 1.1.3; `bcrypt` and `django-ses>=4.0.0` unpinned. System: Debian `ffmpeg`, `cjpegli` from a pinned jpegli commit.
- Frontend (`frontend/package.json`): react 18, react-router-dom 6, axios 1.x, zustand 4, framer-motion, qrcode, vite 5 (caret ranges, lock file present).
- **Known-CVE status was not checked** (no `pip-audit`/`npm audit` run: SEC-0 is read-only and offline). Needs verification (debt row 96).
- Media decoders are the largest parser surface: Pillow (JPEG/PNG/receipt formats), ffprobe/ffmpeg (any container whose first box is `ftyp`), cjpegli. Keep them patched; run them with timeouts and memory limits (rows 74, 93).
- Emails: download-ready and notification emails contain bearer links (job `link_token`), so the recipient mailbox is part of the surface.
- Shared links: gallery share URLs and QR codes (`frontend` `qrcode`) expose `username/slug`; slugs are not secrets.
