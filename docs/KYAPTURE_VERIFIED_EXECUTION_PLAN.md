# KYAPTURE — Verified Execution Plan

**Verification date:** 2026-09-30
**Method:** Direct inspection of the live repository (`C:\Users\LENOVO\Desktop\kyapture`) against every claim in `KYAPTURE_FORENSIC_AUDIT_2026-09-29.md.md`. Every P0, every production-critical P1, and every UNCLEAR item was checked against actual source (models, serializers, views, urls, settings, frontend api/pages) — not re-inferred from the audit text. No application code was changed to produce this document.

**Bottom line:** The original audit is accurate everywhere it could be checked, and it under-counts the danger in one area: **production deployment as currently configured cannot run at all**, for a reason the audit never saw (`DATABASES` is undefined in `production.py`). That single gap is more fundamental than F-01 and must be fixed first. Everything else in the audit's P0/P1 list is confirmed real, with a few precise corrections below.

---

## 1. Verified P0 Blockers (production cannot ship without these)

### P0-0 — NEW, not in original audit: `production.py` has no `DATABASES` setting at all
- `backend/config/settings/production.py` does `from .base import *` and never defines `DATABASES`. Only `development.py` defines it (from `DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`).
- `backend/config/wsgi.py` defaults `DJANGO_SETTINGS_MODULE` to `config.settings.production`. The `backend/Dockerfile`'s `CMD` runs `gunicorn config.wsgi:application`.
- `docker-compose.yml`'s `celery_worker` and `celery_beat` services **explicitly** set `DJANGO_SETTINGS_MODULE=config.settings.production` (the `backend` web service does not override it, so it falls through to whatever `backend/.env`'s `DJANGO_SETTINGS_MODULE` says — currently `development` locally, which is why local dev "works").
- **Effect:** any process actually started under `config.settings.production` (gunicorn per the Dockerfile as-shipped, and both `celery_worker`/`celery_beat` per docker-compose today) will raise `ImproperlyConfigured: settings.DATABASES is improperly configured` the instant it touches Postgres — i.e. on almost every request/task, including the subscription-expiry sweep and every photo/video processing job.
- **Fix:** add a `DATABASES` block to `production.py` (or a shared `dj-database-url`-style parser in `base.py` used by all three env files), sourced from env vars, before anything else in this list is worth deploying.

### P0-1 — F-01 confirmed: every gallery PATCH/PUT crashes
- `Gallery` model (`backend/apps/galleries/models.py`) has no `design_settings` field, and no migration (0001–0004) adds one — confirmed by `grep -rl design_settings apps/` returning only `serializers.py`.
- `GalleryUpdateSerializer.Meta.fields` (`backend/apps/galleries/serializers.py`) lists `'design_settings'` anyway. DRF raises `ImproperlyConfigured` the first time the serializer's fields are built (first PATCH/PUT), so `GalleryDetailView.put/patch` 500s on **every** call.
- Frontend confirms the blast radius: `GallerySettingsPage.jsx` and `GalleryDesignPage.jsx` (`design_settings: settings`) both call this same endpoint.
- **Fix:** either add `design_settings = JSONField(default=dict)` + migration and expose it properly, or drop the field from `GalleryUpdateSerializer.Meta.fields` until it's built. Add a PATCH regression test per field.

### P0-2 — F-04 confirmed: upload timeout kills real uploads
- `frontend/src/api/axiosInstance.js` sets `timeout: 15000` on the shared axios instance. `photosApi.uploadBulk` (`photosApi.js`) passes `{ signal, onUploadProgress }` with no timeout override — it inherits 15s.
- Any 15–30MB photo or any video on a non-trivial connection will abort mid-upload.
- **Fix:** override timeout to `0` (or a large value) specifically on the upload call; keep an `AbortController` for user-cancel.

### P0-3 — F-40 confirmed: production HTTPS/proxy/CSRF config is incomplete
- `production.py` sets `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS — but **never sets `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST`, `CSRF_TRUSTED_ORIGINS`, or `NUM_PROXIES`**. `development.py` sets `CSRF_TRUSTED_ORIGINS` but production does not.
- Behind any TLS-terminating reverse proxy/load balancer, Django won't know the original request was HTTPS → `SECURE_SSL_REDIRECT` can loop, and `request.build_absolute_uri()` (used for cover/display/thumbnail/download URLs and the password-reset link) will emit `http://` links → mixed content.
- No `CSRF_TRUSTED_ORIGINS` in prod means cross-origin POST/PUT/PATCH/DELETE from the SPA will fail CSRF checks the moment frontend and backend are on different hosts (typical for `app.kyapture.com` + `api.kyapture.com`).
- **New related finding:** no nginx config exists anywhere in the repo. `frontend/Dockerfile` builds a plain `nginx:1.27-alpine` image with the default config — there is no `try_files ... /index.html` fallback, so refreshing on any client-side route (`/dashboard/galleries/x/settings`, `/g/username/slug`) will 404 at the nginx layer once deployed, not just fall back to the SPA shell. A minimal `nginx.conf` needs to ship with the frontend image.
- **Fix:** decide same-origin-via-proxy vs. separate-subdomains topology, then set `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`, `USE_X_FORWARDED_HOST = True`, `CSRF_TRUSTED_ORIGINS`, `CSRF_COOKIE_DOMAIN`, `NUM_PROXIES`, and write the missing nginx SPA-fallback config.

### P0-4 — F-46 confirmed and resolved from UNCLEAR to definite: password reset 500s for every real user
- `apps/users/emails/password_reset_email.txt` and `.html` **do not exist anywhere in the repository** (confirmed: only Django/DRF's own built-in template paths under `venv/` match; nothing under `apps/users/`).
- `PasswordResetRequestView.post()` calls `render_to_string('users/emails/password_reset_email.txt', ...)` and `.html` **inside** a `try` block that only catches `User.DoesNotExist`. For any email that *does* match an active user, `TemplateDoesNotExist` propagates uncaught → **500**. For any email that does *not* match, the same code path returns 200 with the generic "if an account exists…" message.
- Net effect: password reset is not just "the confirm link 404s" (F-50, also confirmed below) — the **request step itself throws a 500 for every legitimate user** and silently succeeds (200) for anyone probing for valid emails. This is a P0, not just a UX gap: it's both a full-flow break and a live user-enumeration oracle.
- **Fix:** add the two templates (or switch to plain `send_mail(message=...)` without `render_to_string` for MVP), and move template rendering inside the same exception-safe path so a template bug can never distinguish real accounts from fake ones.

---

## 2. Verified Production-Critical P1s

All confirmed by direct code read; grouped by area.

**Client-facing correctness**
- **F-10** confirmed exactly as written, still unfixed: `clientsApi.js`'s `normalizeError()` sets `.status` directly on the thrown `Error` (no `.response` property at all). `ClientGalleryPage.jsx`'s `fetchGallery` catch block still reads `err.response?.status`, which is always `undefined`. Every 404 falls through to the generic "Something went wrong" state instead of "Gallery not found"; every 401 does the same instead of showing the password gate. Same for `handleUnlock`'s error parsing (`err.response?.data?.password?.[0]`) — dead code, always falls to the fallback string (harmless by luck, but confirms the mismatch is real and unaddressed).
- **F-10b** confirmed: `axiosInstance.js`'s response interceptor triggers the token-refresh flow on **any** 401 that isn't `/auth/token/refresh|login|register`, with no exclusion for `/public/...` endpoints. A wrong gallery password or expired guest session token causes a refresh attempt, which fails for guests, which calls `triggerGlobalLogout()` — clearing the *photographer's own* auth state in `localStorage` and dispatching a logout event, in the same browser tab if a photographer is previewing their own gallery link.
- **F-11** confirmed: `PublicGallerySerializer.Meta.fields` (`clients/serializers.py`) has no cover, no `event_date`, no `processing_status`. `ClientGalleryPage.jsx` already codes around the missing cover (`photos[0]?.display_url` fallback chain) and already reads `data.event_date` — which the backend never sends, so the event date silently never renders even though the frontend is ready for it.
- **F-12** confirmed: `ClientGalleryPage.jsx` always renders "Download Full Gallery" regardless of `allow_download`.
- **F-13** confirmed: `GalleryUpdateSerializer.update()` regenerates the slug whenever `title` changes (`instance.slug = generate_unique_slug(...)`), with no separate "custom URL" concept — a typo fix breaks every shared link.
- **F-15** confirmed: `sanitize_text()` (`core/utils.py`) calls `bleach.clean(text, tags=[], strip=True)`, which HTML-entity-escapes text nodes during re-serialization (e.g. `&` → `&amp;`). React then displays the escaped entity literally since it isn't re-decoded anywhere downstream.
- **F-02 / F-03** confirmed verbatim: `GallerySettingsPage.jsx` still sends `custom_url` (defaulted to the literal string `"davilandd"`), `category_tags`, `download_pin_enabled`, `favorites_enabled`, `store_enabled`, `slider_enabled`, `slideshow_enabled` — none exist on `Gallery` or in `GalleryUpdateSerializer.Meta.fields`, so DRF silently drops them even after P0-1 is fixed. `TopNavBar.handleDelete()` shows `addToast({ message: "Collection deleted" })` and navigates away **without ever calling the delete API** — the gallery is never touched.

**Storage / quota**
- **F-30** confirmed: `GalleryDetailView.delete()` only sets `is_active = False`. `get_user_subscription_metrics()` counts galleries/storage with `is_active=True` only. No purge task exists anywhere — `config/celery.py`'s `beat_schedule` has exactly one entry (`sweep_expired_subscriptions`, every 15 min). A user can upload, soft-delete, repeat indefinitely at zero counted cost while S3 usage grows unbounded.
- **F-32** confirmed: no code path sets `Gallery.cover_photo` automatically on first successful upload; it must be set manually via the (currently broken, P0-1) update endpoint.

**Media pipeline**
- **F-21** confirmed: `strip_exif_gps()` (`core/utils.py`), called from `PhotoListUploadView.post()` on every JPEG with EXIF, re-saves via `img.save(..., format='JPEG', quality=100)` with no `icc_profile=` passed through — the ICC profile is dropped and the "original" is a fresh JPEG re-encode, not byte-identical.
- **F-22** confirmed: `requirements.txt` has no `blurhash` / `blurhash-python` package. `process_image_pipeline()` does `import blurhash` inside a bare `try/except: pass`, silently falling back to the hardcoded placeholder `"LEHV6nWB2yk8pyo0adR*.7kCMdnj"` for every single photo.
- **F-25** confirmed: `process_video_pipeline()` does `video_file.read()` (whole file into memory) before spooling to a temp file.
- **F-25b** confirmed and slightly sharper than the audit's phrasing: `get_video_poster_path()` (`photos/models.py`) hardcodes a `.webp` extension for the `poster_image` field's storage key, but `process_video_pipeline()`/`tasks.py` produce and store actual **JPEG** bytes (`content_type="image/jpeg"`) under that `.webp`-named key. Storage backends that infer `Content-Type` from key extension (S3 via django-storages, by default) will serve JPEG bytes as `Content-Type: image/webp`, which can fail to render.
- **F-26 / F-11 video UNCLEAR resolved:** `backend/Dockerfile` **does** install `ffmpeg` via `apt-get`. FFmpeg availability is no longer unclear — it's present in the image. The audit's caution about "verify FFmpeg present" is resolved: yes. Video transcoding (single H.264 rendition) is still genuinely not implemented — only a poster + unused 3s WebM hover preview are generated; the original file is played back as-is.

**Downloads**
- **F-27** confirmed, partially superseded (see §4): ZIP is still compiled synchronously inside the request (into a temp file, then streamed — this part is *better* than the audit's original description, since files are chunked at 1MB rather than loaded fully into RAM), `DownloadLog` is still written **before** the ZIP is known to succeed, `zipfile.ZIP_DEFLATED` is still used (wastes CPU on already-compressed JPEGs), duplicate `original_name`s are still not de-duplicated, and non-UUID `asset_ids` still reach `MediaAsset.objects.filter(id__in=asset_ids)` unvalidated — Django raises `django.core.exceptions.ValidationError` for a malformed UUID in a filter, which is **not** caught by `custom_exception_handler` (it only reformats what DRF's own `exception_handler` recognizes) and is **not** wrapped by a try/except in `PublicGalleryDownloadView.post()` before that line → unhandled 500.
- **F-28** confirmed: `PublicPhotoDownloadView.get()` still does `asset.original_file.read()` (whole file into RAM) and puts `asset.original_name` unsanitized into `Content-Disposition` — quote/CRLF injection risk if a filename contains a `"` or newline.
- **F-29** confirmed verbatim: `PhotoListUploadView.post()` wraps its entire `transaction.atomic()` block (validation, DB writes, image parsing) in `except Exception as e: return Response({"error": str(e)}, status=400)` — internal errors leak as raw strings, and legitimate validation errors, S3 errors, and PIL errors are all indistinguishable 400s.

**Security / auth**
- **F-35** confirmed: `PublicPhotographerPortfolioView.get()` lists all `is_published=True, is_active=True` galleries with no filter on `is_password_protected` — protected-gallery titles/covers are visible on the public portfolio. `User.objects.filter(is_active=True)` also doesn't exclude staff/superuser accounts.
- **F-36** confirmed precisely: `CookieTokenRefreshView.post()` wraps the *same* `RefreshToken(refresh_token)` instance and does `new_refresh_token = str(refresh)` — this re-serializes the identical token (same `jti`), it does not mint a new one or blacklist the old one, despite `ROTATE_REFRESH_TOKENS: True` in `SIMPLE_JWT` settings and the misleading `if getattr(settings, 'SIMPLE_JWT', {}).get('ROTATE_REFRESH_TOKENS', False):` guard around it. A stolen refresh cookie stays valid for its full 7-day life regardless of subsequent refreshes. Password reset (`PasswordResetConfirmView`) also does not blacklist outstanding refresh tokens after a password change.
- **F-41** confirmed: `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES` in `base.py` does define scoped rates (`password_unlock: 5/minute`, `password_reset: 5/hour`, `login: 5/minute`) and these *are* wired up via dedicated throttle classes on the relevant views (`PasswordUnlockRateThrottle`, `LoginRateThrottle`, `PasswordResetRateThrottle`) — this part of the audit undersells what's already correctly scoped. However, the blanket `anon: 100/day` **does** still apply by default to `PublicGalleryView`, `PublicGalleryDownloadView` (also throttled at the tighter `password_unlock` scope — reasonable), `PublicVideoStreamView`, `PublicPhotoDownloadView`, and `TotalUsersView`, none of which override `throttle_classes`. No `NUM_PROXIES` is set anywhere, so client IP identity behind a proxy is unreliable for all of these. CGNAT/office-IP lockout risk on ordinary public gallery browsing stands.
- Polling storm confirmed: `GalleryPhotosPage.jsx` has `POLL_INTERVAL_MS = 3000`, `setInterval` per pending asset.

**Business/legal (unchanged from audit, not re-verified line-by-line but spot-checked)**
- **F-39** confirmed: `seed_plans.py` seeds `$9.99/$24.99/$59.99` and prints `${plan.price}`; `frontend/src/utils/formatters.js`'s currency formatter hardcodes `NPR ${amount}`. Real mismatch, needs a client decision (see §5).
- **F-50** confirmed and directly linked to P0-4 above: `PasswordResetRequestView` builds `reset_url = f"{settings.FRONTEND_URL}/auth/password/reset/confirm/{uidb64}/{token}/"`; `frontend/src/App.jsx`'s route table has no matching route (only `/forgot-password` exists) — the catch-all `<Route path="*" element={<Navigate to="/" replace />} />` silently redirects a clicked reset link to the landing page.

---

## 3. New Issues Discovered (not in the original audit)

1. **P0-0 above** — `production.py` missing `DATABASES` entirely. The single most severe finding in this pass.
2. **No nginx SPA-fallback config** — `frontend/Dockerfile` ships a bare `nginx:1.27-alpine` with the default config and no `try_files`. Every deep-linked or refreshed client-side route will 404 at the web server, not just misbehave in the SPA.
3. **docker-compose settings-module inconsistency** — `celery_worker`/`celery_beat` explicitly force `config.settings.production` while `backend` (the Django web process) does not, leaving it to whatever `DJANGO_SETTINGS_MODULE` happens to be in `.env`. This means today's docker-compose stack already runs the web server and the Celery workers under **different settings modules** by default — a latent source of "works on web, breaks in the task queue" bugs even before P0-0 is fixed, and it will get worse once P0-0 is fixed if the two are allowed to drift (e.g. different `CORS`/`CSRF` assumptions).
4. **F-46's UNCLEAR is resolved, and it's worse than "unclear"**: the reset email templates are 100% absent, not just unverified, and the try/except placement guarantees a 500 (not a silent failure) for every real account attempting a reset. This elevates F-46 from "P1, verify templates" to a launch-blocking P0 (folded into P0-4 above).
5. **`zipfile`'s `force_zip64` claim in the audit is moot** (see §4) but worth flagging precisely so it isn't miscounted as a fix needed: Python's `zipfile.ZipFile` has defaulted `allowZip64=True` since Python 3.4, so >2GB archives already work without code changes here. Not a real gap.
6. **Throttle scoping is better than the audit implies** — `password_unlock`, `password_reset`, and `login` all have dedicated throttle classes already wired to their views. Only the blanket `anon` scope on ordinary public browsing/streaming endpoints is the real remaining P1 (see F-41 above). Worth not over-building a throttle-scoping project when only the anon-scope gap needs closing.

---

## 4. Audit Findings That Are Outdated, Already Partially Fixed, or Imprecise

- **F-27 (ZIP memory handling):** the audit's original framing ("reads originals into RAM") is out of date — the current `PublicGalleryDownloadView` already streams each asset in 1MB chunks to a temp-file ZIP and streams the response back in 64KB chunks via `StreamingHttpResponse`. The *sync-in-request* compilation, `ZIP_DEFLATED` CPU waste, pre-success `DownloadLog` write, and unvalidated `asset_ids` are all still real (confirmed above) — but "loads everything into RAM" is no longer an accurate description of this specific view.
- **"Downloads >2GB need `force_zip64=True`" (§9/F-27):** incorrect for this codebase's Python version — `zipfile.ZipFile` defaults `allowZip64=True` in Python 3.4+, and `requirements.txt` targets Python 3.12 (per `backend/Dockerfile`'s `FROM python:3.12-slim`). No code change is needed for large-archive support specifically.
- **F-40's Dockerfiles/"UNCLEAR — files not supplied":** resolved. Both `backend/Dockerfile` and `frontend/Dockerfile` exist, are reasonable (FFmpeg installed for backend, multi-stage Node→nginx build for frontend), and confirm FFmpeg is present — but they also surface the new nginx-fallback gap in item 2 above.
- **F-41 (throttle scoping) is described as more broadly "mis-scoped" than it is** — the brute-force-sensitive endpoints (login, password reset, gallery unlock) already have correct dedicated scopes. Only the blanket anonymous browsing/streaming endpoints need scoping work, not a wholesale throttle redesign.
- **Clients app error-handling (F-10) has visibly been worked on since the audit** — `clientsApi.js` was rewritten with a proper `normalizeError()`/`.status` contract and cancellation handling, but `ClientGalleryPage.jsx` was not updated to match, so the *user-visible* bug the audit described is unchanged even though the code on one side of it looks different now. Worth knowing this is a one-sided fix, not an untouched file, when planning the correction (small: swap `err.response?.status` → `err.status`, `err.response?.data?...` → read from the normalized `Error`/its `.code`).
- **Photo upload validation/exception handling (F-29)** is confirmed as-described; no partial fix found here, despite other nearby code (bulk delete, list) showing more recent, more careful error handling patterns. Worth flagging as an inconsistency in how recently different parts of `photos/views.py` were touched.

---

## 5. Remaining Unknowns Requiring Your Decision

1. **Currency (F-39):** ship in USD (matches seeded plan prices and SES/Stripe defaults) or NPR (matches the frontend formatter)? This is a product decision, not something to infer from code.
2. **Payment processor (F-53):** manual-payment-only (current state, functional) is acceptable for MVP, but confirm whether the US client requires card payments (Stripe) at launch or can follow in a fast-follow.
3. **Client-gallery URL scheme (F-14):** `frontend/src/utils/formatters.js`'s `buildClientGalleryUrl()` builds a **subdomain** URL in production (`https://{username}.{domain}/{slug}`), but `App.jsx`'s router only has path-based routes (`/g/:username/:slug`) with no subdomain handling anywhere (no wildcard DNS assumption in settings, no subdomain-based CORS/session logic). Recommend collapsing to the path-based scheme everywhere for MVP (subdomains are a real infra project: wildcard TLS, cookie-domain scoping, CORS regex) — confirm you agree before this becomes a "which three URL builders do we delete" cleanup task.
4. **Free-tier gallery cap (F-31):** `max_galleries=None` on the free tier today (unlimited galleries, 3GB total storage only). Decide the actual number before launch, since it interacts directly with the storage-leak fix in P1 (F-30).
5. **Design settings scope (P0-1):** is "Design" (cover/typography/color/grid) an MVP-required feature, or should `design_settings` ship as a minimal JSON blob (just enough to stop the 500) with the full design UI deferred? This changes the size of Phase 0/1 meaningfully.
6. **Subdomain vs. path-based tenancy long-term:** related to #3 — worth a one-line confirmation that subdomains are explicitly post-MVP, so nobody re-introduces the subdomain URL builder while fixing F-14.

---

## 6. Confirmed-Sound Architecture (preserve, do not rewrite)

Directly verified, not just carried over from the audit:
- Multi-tenant scoping on every authenticated gallery/photo endpoint (`photographer=request.user` / `gallery__photographer=user`), returning 404 rather than 403 to avoid enumeration — consistently applied across `galleries/views.py`, `photos/views.py`.
- `CookieJWTAuthentication` (`core/authentication.py`): correctly extracts from HttpOnly cookie, falls back to `Authorization` header, and enforces Django's real `CSRFCheck` on cookie-authenticated unsafe methods. This is solid and should not be touched.
- bcrypt for gallery passwords (`galleries/serializers.py`, `clients/serializers.py`), constant-time `bcrypt.checkpw`, and `GallerySetPasswordView` correctly revokes all `ClientSession` rows on password change/removal — genuinely correct security behavior, confirmed by reading the view.
- `UniqueConstraint(photographer, slug)` and the async Celery pipeline shape (`process_photo_asset`/`process_video_asset`, `bind=True, max_retries=3`, state machine `pending → processing → ready/failed`) are well-designed and should be extended, not replaced.
- S3/local-disk storage abstraction via `STORAGES` dict with a hard production guard (`production.py` refuses to boot without real `AWS_*` vars and a verified `DEFAULT_FROM_EMAIL`) — good fail-loudly pattern, keep it, just fix the `DATABASES` gap sitting right next to it.
- Login/password-reset brute-force throttling (`LoginRateThrottle`, `PasswordUnlockRateThrottle`, `PasswordResetRateThrottle`) is already correctly wired to dedicated views — extend the pattern to the currently-unscoped public browsing endpoints rather than redesigning throttling.

---

## 7. Exact Recommended Implementation Order

**Phase 0 — Make production boot at all (day 1, before anything else)**
1. Add `DATABASES` to `production.py` (P0-0). Without this nothing downstream is testable in a production-like environment.
2. Reconcile `docker-compose.yml`'s settings-module split — `backend`, `celery_worker`, and `celery_beat` must all run under the same, intentional settings module per environment.
3. Add the two password-reset email templates (or drop `render_to_string` in favor of a plain string for MVP), and move all of `PasswordResetRequestView`'s reset-link construction inside an exception-safe path so template/email failures can never distinguish real accounts (P0-4).

**Phase 1 — Fix the crash-on-every-save bug (day 1–2)**
4. Resolve `design_settings` (P0-1) per your answer to unknown #5 above — either add the field+migration or strip it from `GalleryUpdateSerializer` for now. Add PATCH regression tests for every field (title, cover, watermark, expiry, event date, branding color, publish).
5. Fix upload timeout (P0-2): remove/raise it specifically for `photosApi.uploadBulk`.

**Phase 2 — Production networking (day 2–3)**
6. `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST`, `CSRF_TRUSTED_ORIGINS`, `CSRF_COOKIE_DOMAIN`, `NUM_PROXIES` in `production.py` (P0-3), decided against your chosen proxy topology.
7. Add a real `nginx.conf` to `frontend/Dockerfile` with SPA fallback (`try_files $uri /index.html;`).

**Phase 3 — Client-facing correctness (week 1)**
8. Fix `ClientGalleryPage.jsx` to read `err.status`/the normalized `Error` instead of `err.response?.status` (F-10) — small, precise change given `clientsApi.js` already does the right thing on its side.
9. Exclude `/public/` requests from the token-refresh interceptor in `axiosInstance.js` (F-10b).
10. Add `cover_url`/`cover`, `event_date`, and per-photo `processing_status` to `PublicGallerySerializer` (F-11); filter public `photos` to `processing_status=READY` (or explicitly render pending/failed states).
11. Gate the "Download Full Gallery" button on `allow_download` (F-12).
12. Make slugs stable on rename — only regenerate via an explicit "edit URL" action, never as a side effect of a title edit (F-13).
13. Fix `sanitize_text()` to strip tags without HTML-entity-escaping survivors (`bleach.clean(..., strip=True)` output run through `html.unescape`, or switch to `django.utils.html.strip_tags`) (F-15).
14. Hide or wire up the fake Settings controls and `TopNavBar.handleDelete` (F-02/F-03) — per project principle, prefer hiding over shipping fake success states.

**Phase 4 — Storage & quota integrity (week 1–2)**
15. Add a real trash state (`deleted_at` + retention window) and a purge Celery-beat task; stop counting soft-deleted galleries as "free" only in quota math while leaving their files live (F-30).
16. Auto-set `cover_photo` on first successful upload if unset (F-32).
17. Decide and enforce the free-tier gallery cap (unknown #4).

**Phase 5 — Media pipeline (week 2)**
18. Add `blurhash`/`blurhash-python` to `requirements.txt` (F-22) — one-line fix, currently silently degrading every photo.
19. Fix `strip_exif_gps` to preserve the ICC profile (pass `icc_profile=img.info.get('icc_profile')` through to `img.save`) or switch to a byte-level EXIF strip that never re-encodes image data (F-21).
20. Fix the poster image extension/content-type mismatch — either generate a real WebP poster or change `get_video_poster_path` to emit `.jpg` (F-25b).
21. Stream video processing input instead of `.read()`-ing the whole file (F-25).

**Phase 6 — Downloads & upload error handling (week 2–3)**
22. Validate `asset_ids` as UUIDs before the queryset filter in `PublicGalleryDownloadView` (F-27's 500 case); move `DownloadLog.objects.create()` to after ZIP success; switch to `ZIP_STORED`; de-duplicate `original_name` collisions.
23. Replace `PublicPhotoDownloadView`'s full-file `.read()` with a streamed response, and sanitize `original_name` before it reaches `Content-Disposition` (F-28).
24. Replace `PhotoListUploadView`'s blanket `except Exception as e: return Response({"error": str(e)}, 400)` with structured error handling that doesn't leak internals and distinguishes validation vs. system errors (F-29).

**Phase 7 — Security hardening (week 3)**
25. Fix `CookieTokenRefreshView` to actually rotate (mint a new `RefreshToken` via `RefreshToken.for_user(user)` semantics or SimpleJWT's real rotation path, blacklist the old token) rather than re-serializing the same token (F-36).
26. Blacklist outstanding refresh tokens on password reset/change.
27. Exclude password-protected galleries' covers/titles from `PublicPhotographerPortfolioView`, and exclude staff/superuser from the public username lookup (F-35).
28. Add `throttle_classes` (anon-scoped or a dedicated `public_browse` scope) to `PublicGalleryView`, `PublicVideoStreamView`, `PublicPhotoDownloadView`, `TotalUsersView`; set `NUM_PROXIES` once the proxy topology (Phase 2) is decided (F-41).
29. Replace `GalleryPhotosPage.jsx`'s fixed 3s-per-asset polling with a batched status endpoint or backoff.

**Phase 8 — Everything else from the original audit, unchanged priority**
30. Photo sets, favorites, download PIN/resolution choice, download activity UI, slideshow, design-settings-applied-to-client — per the audit's §5/§16 gap matrix and your answer to unknown #5.
31. Currency and payment-processor decisions (unknowns #1–2), truthful marketing copy + legal pages (F-60), N+1/pagination cleanup (F-33), code splitting/font/perf pass (§7/§12), test suite repair (F-70 — confirmed `users/tests/*.py` are 2-line stubs).
32. Deployment hardening: CI, health checks, Sentry, DB backups, S3 lifecycle rules.

---

## 8. Summary Counts

- **Verified P0 blockers:** 5 (1 new — missing `DATABASES` in production — plus F-01, F-04, F-40, F-46/F-50 combined as one flow-breaking chain).
- **Verified production-critical P1s:** 19 distinct confirmed findings across client correctness, storage/quota, media pipeline, downloads, and security.
- **New issues found beyond the audit:** 6 (most severe: production `DATABASES` gap; also nginx SPA fallback, docker-compose settings-module split).
- **Audit findings corrected/updated:** 6 (ZIP memory handling improved since audit, zip64 non-issue on Python 3.12, Dockerfiles now exist and confirm FFmpeg, throttle scoping better than described, F-10 is a one-sided partial fix not an untouched bug, F-29 unchanged despite nearby code being more careful).
