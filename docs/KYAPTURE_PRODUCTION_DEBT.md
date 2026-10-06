# KYAPTURE production debt tracker

Every known gap from every chunk goes here. Nothing is "fine for beta". Each row has a chunk that owns it.
Status: OPEN until the owning chunk fixes it and the chunk report says so.
Put this file in docs/ and commit it. Agents must add a row for any gap they leave (see rule at the bottom).

## A. Fix before Wave 3 (chunk VID-C)

| # | Gap | Raised in | Fix |
|---|-----|-----------|-----|
| 1 | Video length is checked only after the upload (server 403). Must be known BEFORE upload | VID-B | VID-C: allow blob: in media-src, read duration in browser, server pre-flight check. **DONE in VID-C** (a too-long video sends zero upload requests; exception: row 31) |
| 2 | Settings > Plan & Billing meters have no video minutes | VID-B | VID-C. **DONE in VID-C** (Video meter only for a plan with a limit above 0) |
| 3 | Collection-limit modal on the empty-state button tested with a fake list only | VID-B | VID-C: test with real data (Free cap = 0 in admin). **DONE in VID-C** with real data and the cap at 0 on the plan row (the admin form refuses 0: row 32) |
| 4 | Upload body is received before the plan check, so a refused file still costs bandwidth | VID-A | VID-C (pre-flight avoids it for honest clients); 7-B for abuse. **PARTLY DONE in VID-C**: honest clients whose browser can read the length no longer upload a refused video. Still OPEN for abusive clients (7-B) and unreadable codecs (row 31). Storage (BILL-C): an honest client skips files that cannot fit at click time and sends no request for them; a direct API call still has its body received before the 403 |

## B. Security (Task 7, Wave 5)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 5 | Favorites are matched by typed email with no verification: anyone can see another person's favorite list in a gallery | 6.4-B | 7-A (add to its prompt) |
| 6 | original_url is returned in the media API: check it against the private-storage rule (Free user must not reach Original) | VID-A | 7-B |
| 7 | "Direct API refused" for Free users proven by tests and a raw 403 only (curl check failed on token format) | BILL-B | 7-B / 15-A |
| 8 | Hard ceilings 25 MB per image and 5 GB per video are not plan values: owner decision | VID-A | 13-C (owner decides). **PARTLY DONE in UP-A**: they are now ONE admin-editable row (Subscriptions > Upload limits: images 100 MB and 144,000,000 px, video 2048 MB), global, not per plan. Still open: the owner decides the real values and whether any should differ per plan |
| 9 | Share by email is only a mailto: link (no email service) | 5.1-A | 7.5-D (decide: keep or real email) |

## C. UI and design (Wave 6)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 10 | React.lazy routes: check there is a loading state on first open | 6.4-E | 8-C / 9A-1 |
| 11 | Preview button hidden below 640px; Escape does not close Preview | 5.1-E | 9A-3 |
| 12 | Locked-feature banners are plain amber boxes | BILL-A | 9C-1 |
| 13 | Set delete uses native window.confirm, not the styled dialog | 5.1-0 (D6) | 8-C |
| 14 | Highlights tile fixed at 9:10, not each photo's shape | 5.1-E | 9A-3 / 9B-1 |
| 15 | Dashboard card bottom link-icon button unchanged | 5.1-A | 9A-2 |
| 16 | Demo-only feature cards on the landing page | 6.4-D | 10-B |
| 17 | Dashboard header search was removed: confirm the collection search on Galleries still works | 6.4-D | 9A-2 (verify now) |
| 18 | Mailto share and other copy: no real check at 390px for 6.4-E pages | 6.4-E | QA-A |

## D. Engineering and storage (Task 11, Wave 8)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 19 | Orphan ZIP if a collection is deleted while its ZIP is being built | 5.1-0 (D6) | 11-D (scheduled purge_orphans) |
| 20 | Leftover QA video files on the Docker media disk | VID-A | 11-D |
| 21 | Empty galleries/ directory left after user delete | 5.1-0 (D6) | 7.5-E |
| 22 | Two 401 console errors never traced | 5.1-0 | QA-A |
| 23 | Multi-part ZIP bell notification only covered by tests, never seen in a browser | 6.4-B | 6-D and QA-A. **6-D: parts proven by tests (split, names, every photo once), NOT run in a browser** (needs a forced small `DOWNLOAD_ZIP_PART_MAX_BYTES` in the stack); stays OPEN for QA-A (row 68) |
| 24 | Multi-part ZIP: 2 GB limit in dev prevented a real run | 6.4-B | 15-A (staging) |

## E. Release (Waves 9-10)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 25 | Terms / Privacy / Cookies links were removed from the footer and signup: add them back when pages exist | 6.4-D | 13-B |
| 26 | DUMMY plan values (prices, storage, video minutes) must be replaced by the owner in admin | BILL-A/B, VID-A | 13-A checklist (owner) |
| 27 | Migrations changed dev data (favorites merge, plan columns dropped): back up before production | 6.4-B, BILL-B | 13-C, 15-B (real restore) |
| 28 | backfill_video_durations must be run once on real data (dry-run first) | VID-A | 13-C |
| 29 | Dev DB lost a user to a pattern delete: rule added, restore decision by owner | VID-A | rules file |
| 30 | docs/KYAPTURE_AGENT_RULES.md uncommitted; pixieset-ref folders untracked (blur IP and email in screenshots first) | start | owner, now |

## F. Raised by VID-C

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 31 | A video whose length the browser cannot read (verified in Chrome: an MPEG-4 Part 2 `.mp4`) uploads in full before the server's ffprobe check can refuse it, so the bandwidth is still spent. The server stays authoritative; only the early refusal is missing (needs a server-side early probe, e.g. chunked/resumable upload) | VID-C | 7-B (add upload body check for abusive clients) |
| 33 | No visible "checking videos" state while the browser reads lengths and waits for the pre-flight (4 reads at a time, 5 s timeout each: a drop of hung files can wait several seconds with no feedback) | VID-C | 9A-3 |
| 35 | The pre-flight judges the drop as one batch: if the videos together exceed the plan, none upload (photos still do), even when the first alone would fit. No partial acceptance | VID-C | product decision, leave |
| 36 | Dashboard sidebar footer reads "FREE PLAN" for a user on an active Pro subscription, while Settings > Plan & Billing shows Pro (seen in the VID-C desktop screenshot; cause not investigated) | VID-C | 9A-1 (App shell) — **MUST FIX** |
| 37 | `frontend/nginx.conf` file-header comment (lines 41-45) still says no Content-Security-Policy is added, though one is set below it. Left alone to keep VID-C's nginx diff to `media-src` plus its own comment | VID-C | 13-C (fix the stale CSP comment in frontend/nginx.conf during the config audit) |
| 38 | VID-C browser QA ran as throwaway puppeteer scripts outside the repo (no end-to-end harness in the repo). Upload-request counts are covered in the repo only by unit tests with injected fakes. BILL-C's browser QA (modal, meters, admin edit, delete) was also throwaway scripts | VID-C, BILL-C | QA-A |
| 39 | docs/pixieset-ref screenshots show an IP address and emails: blur before committing | start | owner, before the first push of that folder |
| 40 | Photo storage (GB) limit: is it enforced at upload with an upgrade modal, and what happens to a user already over a lowered limit | BILL-C | BILL-C. **DONE in BILL-C** (403 `storage_limit_reached`, shared modal, partial batches, over-limit state; gaps in rows 41-46) |
| 41 | Usage counts only the original (`MediaAsset.file_size`). The private Download Master, the WebP derivatives, the video poster and the playback MP4 are stored but not metered, so real storage cost is higher than the plan number. Counting them needs their sizes recorded per row | BILL-C | 13-A (owner decides what "storage" means, then a size column + backfill) |
| 42 | `MediaAsset.file_size` is a 32-bit `integer` column (max 2,147,483,647 bytes, checked in Postgres). A video between 2 GiB and the 5 GB ceiling (row 8) fails the insert and the upload answers 500 `upload_processing_error`; such a file also could not be counted. Needs a BigInteger migration (not run against the host dev DB) | BILL-C | 13-C (with row 8). **DONE in DB-A**: migration `photos.0008` -> `PositiveBigIntegerField`, run on the Docker dev DB only (rows 61-62 for what is left) |
| 43 | `get_user_subscription_metrics` selects a subscription by `status='active'` only, while entitlements also require `expires_at` in the future. A lapsed plan keeps its paid storage limit until the sweep flips it (runs every 15 minutes) | BILL-C | 7-B |
| 44 | Only the storage check is repeated under the per-account row lock. The video-minutes check still uses usage read before it, so two parallel direct-API video uploads can pass it together and exceed the minutes by one batch | BILL-C | 7-B |
| 45 | The warning state shows on Billing and Settings only. The dashboard home and the workspace show nothing until an upload is refused, and nobody is told when an admin lowers a plan below their usage (no email or notification) | BILL-C | 9A-2 (dashboard) / 9C-1 |
| 46 | Settings > Plan & Billing meters for collections and video still turn red at a frontend 90% constant; only storage reads its state and threshold from the backend | BILL-C | 9C-1 |

## G. Raised by 6-A (compression calibration, docs/KYAPTURE_COMPRESSION_CALIBRATION.md)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 47 | The Download Master helper runs 11 Pillow encodes plus a PSNR check per JPEG: 5.5-12.5 s of worker CPU per upload (measured), against 0.2-0.4 s for one fixed encode | 6-A | 6-B (fixed jpegli q90, no search). **DONE in 6-B** (12 real JPEGs, in-container: median 6113 ms -> 484 ms, max 9222 -> 1492) |
| 48 | `cjpegli` is not in the backend image (Debian `libjxl-tools` has no cjpegli). Needs a pinned multi-stage build (124 s), a subprocess call with timeout, and a tested Pillow fallback | 6-A | 6-B. **DONE in 6-B** (pinned commit, multi-stage, 1.0 MB stripped binary in the runtime image; fallback tests for missing binary, non-zero exit, timeout, garbage and wrong-size output) |
| 49 | Web Size is Pillow q90 baseline at request time: about 28% bigger than jpegli q90 for 1.6 lower SSIMULACRA2 (10 images, 2048 px). Not changed by 6-B unless the owner asks | 6-A | 6-B (owner decides). **DONE in 6-C, Pillow kept**: the lowest jpegli quality not worse than Pillow q90 on every one of 12 images is q95/q96, which is 12-31% LARGER; no quality saves 10% without losing quality on some image (section 6 of the calibration doc). Web Size is now cached per photo/px/watermark state |
| 50 | A source above 3600 px whose capped re-encode is larger than the original gets no Download Master (`_make_download_master` returns None), so `_get_client_download_source` serves the full original to a Free client. Found by reading the code, not reproduced | 6-A | 6-B (keep the capped master for sources above 3600 px). **DONE in 6-B** (JPEG and PNG; also `backfill_download_masters`, which deleted the master in the same case) |
| 51 | Calibration used 10 phone/scan JPEGs (largest 5312 px, one ICC source); no 24 MP+ DSLR file; Linux timings are from the dev Docker host, not production hardware | 6-A | 6-B verification / 15-A. 6-B re-ran on 12 other real JPEGs (largest 3648 px) in the Linux dev container: still no 24 MP+ DSLR file, no production-hardware timing. Open for 15-A |
| 52 | Masters already stored by the old encoder stay as they are (valid; on the 12-file sample they were -33% to +7% in size and SSIMULACRA2 about 1.7 lower on average). Nothing re-encodes them; `backfill_download_masters` only touches masters above 3600 px | 6-B | owner decides whether to re-encode the existing library; no chunk assigned |
| 53 | The pinned `cjpegli` build clones github.com/google/jpegli at image-build time (about 100 s on the dev host, needs network). A production build pipeline with no GitHub access or a build cache needs the source vendored or mirrored | 6-B | 15-A |

## H. Raised by 6-C (Web Size exact-px cache)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 54 | A cold single Web Size needs a `celery_websize` worker (own queue, `--concurrency=2`, added to docker-compose). With no such worker the request waits `WEB_SIZE_WAIT_SECONDS` (25) and answers 503 `web_size_preparing`; there is deliberately no encode in the request thread. The production deploy manifest must run this worker | 6-C | 14-A (staging compose/service config) and 16-A (production) |
| 55 | A ZIP job encodes its cold Web Sizes inline in its own Celery task, serially, so that CPU is bounded by the default worker's concurrency and not by the `websize` queue's 2 slots | 6-C | 15-B (decide only if staging numbers need it) |
| 56 | Cached Web Sizes are private-storage objects that are not metered in the plan storage number (adds to row 41). A superseded entry (watermark edited, master re-encoded) is removed only when that photo/px is next written; until then it stays, at most one stale file per (photo, px). Purge of the photo/set/collection removes all of them | 6-C | 11-D (lifecycle rule: purge old cached Web Sizes) |
| 57 | The cache key reads the source file's size (one storage stat) and then `exists` (second call); on S3 that is two requests per warm download. Measured only on local disk (warm single download 34-47 ms) | 6-C | 15-B |
| 58 | The cold-ZIP timing had unexplained outliers (27-63 s task time) during a host memory shortage; clean runs were 5.3-8.9 s. Not reproduced afterwards | 6-C | 15-B (re-measure on staging hardware) |
| 59 | Cold single Web Size can return 503 web_size_preparing; the client UI shows a generic error | 6-C | 6-D (Preparing state + Retry-After auto-retry). **DONE in 6-D** (single-photo dialog and set-download page: "Preparing your download…", retry after Retry-After, `PREPARING_MAX_ATTEMPTS` = 4, then "Try again"; browser-tested with the worker stopped, then started; see row 66) |

Row 36 note: The sidebar label comes from `frontend/src/components/layout/DashboardLayout.jsx`, which maps `user?.is_active_plan` to "Pro Plan" or "Free Plan".
Plan & Billing gets the plan and subscription from `frontend/src/hooks/useSubscription.js` and checks for an active subscription before showing the plan.
Yes, a real paid user can see different labels if the auth-store flag and the live subscription response disagree or one is stale.

## I. Raised by DB-A (64-bit byte counts)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 61 | `photos.0008` was applied to the Docker dev DB only (2 rows). The host dev DB and production are not migrated. On a large production table it is one `ALTER COLUMN ... TYPE bigint`, a full table rewrite under an ACCESS EXCLUSIVE lock; the length of that lock was not measured on a large table. Run in a quiet window after a backup | DB-A | 13-C, 15-B (real restore + timed run on a production-size copy) |
| 62 | No real upload above 2 GiB has been run. Tests store a tiny clip whose reported size is patched to 4 GiB / 5 GB; the DB, plan rules, serializers and JSON are proven, but the web server, ASGI/gunicorn timeouts, temp disk and storage backend limits for a real 2-5 GB body are not | DB-A | 15-A (staging: one real 5 GB upload and ZIP) |
| 63 | Only `MediaAsset.file_size` held a byte count in an integer column. ZIP/download part sizes live in `DownloadJob.files` JSON (no 32-bit limit); the other integer columns are counts, pixels or seconds. A future byte column must be 64-bit | DB-A | rules file (check on every new size field) |

## J. Raised by 6-D (all download paths + acceptance)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 67 | `clients.0012_download_job_variant` was applied to the Docker dev DB only; host dev DB and production are not migrated. Old READY jobs have variant '' and are simply never reused | 6-D | 13-C, 15-B |
| 68 | The 2 GB multi-part split and its bell notification were not run in a real browser (rows 23/24). A photo with no usable source file is still skipped quietly when a ZIP is built (only a photo that fails while being written fails the job) | 6-D | QA-A / 15-A |
| 69 | The favorites list has no download action, so "favorites download" has no separate path to test; if the owner expects one it is a feature, not a fix | 6-D | RS0-B |
| 70 | 390 px layout of the ZIP preparing page and the Download Photo page not checked | 6-D | QA-A |

## K. Raised by UP-A (per-file upload limits, docs/KYAPTURE_UPLOAD_LIMITS.md)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 71 | Video disk space for processing is not checked or provisioned: a 2 GB upload needs the proxy's temp body, Django's temp file, the stored original and the FFmpeg output on disk at the same time (several times the file), and nothing refuses a video when the disk is short | UP-A | 11-D (disk alert / quota), 15-A (measure on staging) |
| 72 | No real upload at the limits was run: a 100 MB image, a 144-megapixel image and a 2 GB video through the real proxy, gunicorn and worker. Tests use a PNG header with no pixel data and a tiny clip with a patched size. The gunicorn `--timeout` (Dockerfile uses the 30 s default) would cut a long upload, and is not set | UP-A | 15-A (real large upload on staging) |
| 73 | The proxy that fronts Django is not in this repo, so `client_max_body_size` (must be at least `max_video_mb` + about 50 MB, 2100m for the default) is documented but not set or tested anywhere; raising `max_video_mb` in admin without raising it gives a bare nginx 413 | UP-A | 14-A (staging config), 16-A (production config) |
| 74 | Decode memory at the pixel limit was not measured: a 144-megapixel RGB image is about 430 MB in Pillow before the resize and encode copies, per Celery worker process. The default 144,000,000 comes from the Pixieset reference, not from a measurement on our hardware | UP-A | 15-A (measure peak worker memory, then set the default) |
| 75 | The server reads the whole body before it can judge a file, so an image over the pixel limit (up to the size limit) or a file over the size limit still costs its bandwidth up to the proxy limit. The browser pre-checks size only; it never decodes, so a too-large-in-pixels image uploads fully before the refusal | UP-A | 7-B (early body check for abusive clients; see rows 4, 31) |
| 76 | Lowering `max_image_pixels` does not touch photos already stored: the worker, Web Size and ZIP code set Pillow's guard from the new value, which raises above twice it, so an old photo larger than that can fail to process or download after the edit | UP-A | owner decision (13-A), then 13-C |
| 77 | `subscriptions.0009_upload_limits` was applied to the Docker dev DB only; the host dev DB and production are not migrated (the row is also created on first read) | UP-A | 13-C, 15-B |

## L. Raised by SEC-0 (security docs, docs/security/; SEC-xx ids in docs/security/threat-model.md)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 78 | SEC-01: `NUM_PROXIES` is a top-level setting (`production.py:242`) but DRF reads it only from `REST_FRAMEWORK`, so throttles key on the raw client-supplied `X-Forwarded-For`; a new header value per request bypasses login, unlock/PIN and reset throttles. `_get_client_ip` (`clients/views.py:135`, `clients/serializers.py:390`) also stores the left-most XFF as the client IP. Needs a proxy that overwrites XFF plus a test | SEC-0 | 7-A |
| 79 | SEC-02 (widens row 5): a claimed `?email=` also lets any visitor rename, delete and add photos to another visitor's favorite lists (`favorite_lists.py:87-128, 217-222`; `clients/views.py:926-970`) | SEC-0 | 7-A |
| 80 | SEC-03: "Restrict Downloads to Specific Contacts" accepts any typed, unverified email that is on the list (`download_access.py:224-229`) | SEC-0 | 7-A |
| 81 | SEC-04: download PIN 4-8 digits and gallery password min 4 chars, with no per-gallery failed-attempt counter, backoff or alert; only the per-IP throttle (see row 78) | SEC-0 | 7-A |
| 82 | SEC-05: originals and public derivatives share one bucket and the same key prefix; the original's key is derivable from a public display URL, so privacy depends only on per-object ACL. Bucket policy / Block Public Access / Object Ownership not in repo; verify on staging | SEC-0 | 7-B (verify in 15-A) |
| 83 | SEC-06: with `DEBUG=True`, `config/urls.py:37-38` serves all of `MEDIA_ROOT` without auth (originals, Download Masters, receipts) and compose publishes `:8000` on all interfaces | SEC-0 | 7-B |
| 84 | SEC-07: `PublicVideoStreamView` redirects to a signed URL of the private original when no playback MP4 exists, and ignores `allow_download` (`clients/views.py:1742-1753`) | SEC-0 | 7-B |
| 85 | SEC-09: public derivatives (WebP tiers, posters, playback MP4) are public-read with permanent URLs and 1-year immutable cache; adding a password, unpublishing or expiry does not revoke URLs already seen | SEC-0 | 7-B |
| 86 | SEC-10: no `backend/.dockerignore`; `COPY . .` (`backend/Dockerfile:50`) puts `backend/.env`, `venv/`, `media/`, `logs/` into the image. Not inspected (no build in SEC-0) | SEC-0 | 13-C |
| 87 | SEC-11: dev DB password hardcoded in `docker-compose.yml` (5 places) and `development.py:14`, equal to the DB name, in history since the first commit; Postgres, Redis (no auth), Mailpit and Django published on all host interfaces | SEC-0 | 13-C |
| 88 | SEC-13: one `SECRET_KEY` signs JWTs, download/job/file tokens and reset links; no separate JWT key, no `SECRET_KEY_FALLBACKS`, no rotation runbook; S3 and SES share one AWS key pair | SEC-0 | 13-C |
| 89 | SEC-14: gallery unlock tokens stored in plaintext (`clients/models.py:61`), visible in admin, and accepted in `?token=` URLs (logs, history) | SEC-0 | 7-A |
| 90 | SEC-15: Django admin at the default `/admin/` with no login throttle/lockout, no MFA, no network restriction; gallery admin form shows password/PIN hashes | SEC-0 | 7-A |
| 91 | SEC-16: no email verification at registration | SEC-0 | 7-A |
| 92 | SEC-17: token refresh has no own throttle and falls under `anon` 100/day per IP (~96 refreshes/day per active user); several users behind one NAT can be logged out. Not runtime-tested | SEC-0 | 7-A |
| 93 | SEC-18: ffmpeg poster/transcode `subprocess.run` has no timeout (`core/utils.py:868, 895`); no Celery time limits | SEC-0 | 7-B |
| 94 | SEC-19: GPS strip fails open (`core/utils.py:329`); video location metadata is never stripped and video originals are served to clients | SEC-0 | 7-B |
| 95 | SEC-20: one `nginx.conf` CSP for every build allows `http://localhost:8000` and `style-src 'unsafe-inline'`; no `server_tokens off` | SEC-0 | 15-A |
| 96 | SEC-21: backend container runs as root; base images by tag not digest (`redis:alpine`, `mailpit:latest` float); `bcrypt` and `django-ses` unpinned; no CI dependency audit; CVE status of current versions not checked | SEC-0 | 15-A |
| 97 | SEC-22: no security event logging (failed login/unlock/PIN, 429s, payment approvals), no off-host log shipping, no error tracking or alerting | SEC-0 | 15-A |
| 98 | SEC-23: no account deletion or data export; client IP + email kept 365 days (DownloadLog) and 30 days (ClientSession); retention not decided by the owner | SEC-0 | 13-C |
| 99 | SEC-27: single-photo download does not require READY; for a non-READY image `resolution=web` can fall back to the original (`clients/views.py:1838, 1919-1922`). Needs the asset UUID; not reproduced | SEC-0 | 7-B |
| 100 | SEC-28: JWT and CSRF cookies are scoped to `.kyapture.com` (every subdomain) and `ALLOWED_HOSTS` falls back to `.kyapture.com`; verify no subdomain serves untrusted content | SEC-0 | 15-A |
| 101 | SEC-29: 11 `docs/pixieset-ref` screenshots are tracked and already on `origin/feature/landing-page-redesign` (row 39 assumed they were not pushed yet); contents not opened in SEC-0. Owner checks for IP/emails and decides on history rewrite before any merge to main | SEC-0 | 13-C |
| 102 | SEC-25/26: QA gallery password and PIN in plaintext in `docs/qa-1r5e/qa-script.js:1, 11, 12`; an old `backend/.env.example` (commit `aecfb94`, line 10) held a non-placeholder-looking `SECRET_KEY` literal: confirm it was never used; `test_s3_connection` prints a presigned URL | SEC-0 | 13-C |
| 103 | DB hardening: every container runs `migrate` with the runtime DB credentials (runtime user has DDL rights) and `DATABASES` sets no `sslmode`; verify on the production DB | SEC-0 | 15-A |

## M. Raised by 6.3-A (feedback backend and staff inbox API, docs/KYAPTURE_FEEDBACK.md)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 104 | The staff bell notification links to `/dashboard/feedback`, a route that does not exist until the inbox page is built; until then a click lands on the catch-all redirect | 6.3-A | 6.3-B (create the route). **DONE in 6.3-B**: the route and the staff inbox page exist; a real bell notification was clicked in a browser and opened `/dashboard/feedback` |
| 105 | The route is cleaned on the server (path only, UUID and long-token segments masked), but the masking is a heuristic. The submit form must send only `location.pathname` (a route pattern is better), never a full URL or a signed link. The frontend also sends no `app_version` yet, and `APP_VERSION` is not set in compose, so rows read `dev`/`unknown` | 6.3-A | 6.3-B (send pathname + version); 14-A (set `APP_VERSION` per build). **DONE in 6.3-B**: the form sends `location.pathname` (query and fragment cut again in the browser; verified `?token=..#frag` arrives as `/dashboard/billing`) and the one build constant `VITE_APP_VERSION` (default `dev`); compose feeds backend `APP_VERSION` and the frontend build arg from the same `${APP_VERSION:-dev}`; a stored row read `dev`, not `unknown`. What is left: rows 109 and 110 |
| 106 | `users.0007_feedback` was applied to the Docker dev DB only; the host dev DB and production are not migrated | 6.3-A | 13-C, 15-B |
| 107 | No retention rule for feedback rows (they are kept until the user is deleted; deleting the user cascades to their feedback) and no purge task. Staff are told only through the bell, never by email, so nobody is told if no staff account is signed in | 6.3-A | 13-C (with row 98) |
| 108 | The per-user feedback throttle (and every other DRF throttle) uses Django's default cache. No `CACHES` is configured, so it is the per-process local-memory cache: with several gunicorn workers each worker counts separately, so the real limit is higher than `feedback: 5/hour`. Needs a shared cache (Redis is already in the stack) | 6.3-A | 15-A (also fixes the other throttles, see row 78) |

## N. Raised by 6.3-B (feedback widget and staff inbox UI)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 109 | The frontend version and the backend `APP_VERSION` are two separate settings. Compose feeds both from `${APP_VERSION:-dev}`, but a staging/production build that sets only one side (or a deploy that serves an older frontend build after the backend moved on) is not an error: the server silently stores `unknown`. The deploy pipeline must pass the same value to the frontend build (`VITE_APP_VERSION`) and the backend (`APP_VERSION`), and list older still-served builds in `FEEDBACK_ACCEPTED_APP_VERSIONS` | 6.3-B | 14-A (staging) and 16-A (production) |
| 110 | The widget sends the raw `location.pathname`, so a gallery slug is part of `route` (e.g. `/dashboard/galleries/<slug>/settings`). Row 105 preferred a route pattern (`/dashboard/galleries/:id/settings`); the task said to send the path, so a pattern was not built. The slug is the photographer's own data shown to staff, not a secret | 6.3-B | 13-C (with row 107, the feedback privacy and retention decision) |
| 111 | No cookie-consent or other site-wide banner exists yet, so the button was not tested against one. The button steps aside for anything marked `aria-modal="true"`, `role="alertdialog"` or `data-hide-feedback-fab`; a future cookie banner or any new modal must carry one of those, or it can sit under or over the button | 6.3-B | 13-B (when the cookie banner is built) |
| 112 | The mobile offsets of the button on the gallery workspace (`7.75rem`) and the page-end padding (`pb-48`) are fixed rem values matched to the current heights of the two phone bars (photo-sets bar + bottom tabs). If those bars change height, the button must be re-measured | 6.3-B | 9A-3 (workspace UI pass) |
| 113 | A person can send feedback but cannot see their own past messages or their status: `GET /feedback/mine/` exists and has no screen. The staff inbox has no search, no per-message page and no reply (no email either, rows 107) | 6.3-B | product decision, then 13-C |
| 114 | 6.3-B browser QA ran as throwaway puppeteer scripts outside the repo (same pattern as row 38); only the pure helpers (`feedbackFlow.js`) are covered by repo tests | 6.3-B | QA-A |

## O. Raised by 6.2-A (typography backend, docs/KYAPTURE_TYPOGRAPHY.md)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 115 | `frontend/index.html` loads Cormorant Garamond, Outfit and Plus Jakarta Sans from fonts.googleapis.com / fonts.gstatic.com, so every client gallery visit already sends the visitor's IP to Google. The six typography fonts must be self-hosted instead (CSP `font-src 'self'` already allows it); the existing three should move too, and the two Google hosts can then leave `style-src` / `font-src` | 6.2-A | 13-B (privacy), with 6.2-B for the six new fonts **DONE in 6.2-B**: the Google `<link>`s and the `@import` are gone; all eight families (the six styles + Outfit + Plus Jakarta Sans) are self-hosted woff2 under `/assets/`; no request to fonts.googleapis.com or fonts.gstatic.com in the browser. nginx CSP left unchanged on purpose (`font-src 'self'` already allows the files); the two Google hosts are still listed in it: row 120 |
| 116 | No font file exists yet: until 6.2-B bundles the six OFL families, `typography_style.font_family` falls back to the system part of each stack (the gallery works, but the chosen look is not shown). The OFL licence of each family is recorded from the Google Fonts catalogue, not yet checked against a downloaded `OFL.txt` | 6.2-A | 6.2-B **DONE in 6.2-B**: 20 Latin woff2 files copied from the Fontsource packages (368 KB in the repo); each family's licence text (SIL OFL 1.1, opened and checked) is in `frontend/public/font-licenses/`, served at `/font-licenses/` |
| 117 | The Design page and the Collection Defaults screen still draw the six styles with Tailwind classes (`TYPOGRAPHY_CLASSES`, `font-serif`/`font-sans`), not from the API table, so their preview does not match `typography_style` until 6.2-B | 6.2-A | 6.2-B **DONE in 6.2-B**: the Design typography tab, its Live Preview (`CoverPreview`), the dashboard Preview and the client hero draw from the server style through CSS variables; `TYPOGRAPHY_CLASSES` is deleted; Collection Defaults lists the six ids with the server's names |
| 118 | The gallery Design save validates the presentation keys but still stores any other unknown key a photographer's client sends (never public: the public payload is an allowlist). A stricter "reject unknown keys" needs the frontend blocks (watermark, downloads, privacy, coverPhoto) listed first | 6.2-A | 9C-1 |
| 119 | A gallery that already holds an out-of-vocabulary value for a presentation key (the API accepted anything before 6.2-A) cannot save the Design page until the photographer picks a valid value, because the page re-sends every key. No such row is known; not queried in production | 6.2-A | 13-C (data check before release) **DONE in 6.2-B (frontend)**: the Design page checks every stored key against the vocabulary (`normalizeDesignSettings`), shows the app default as selected and sends only valid values; a gallery stored with invalid typography/layout/grid values saved normally in the browser (Free and Pro) |

## P. Raised by 6.2-B (typography Design tab and hero)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 120 | `frontend/nginx.conf` CSP (three copies) still allows `https://fonts.googleapis.com` in `style-src` and `https://fonts.gstatic.com` in `font-src`. Nothing loads from them any more; leaving them widens the policy for no reason | 6.2-B | 15-A (with row 95, the CSP audit) |
| 121 | A client gallery still downloads the app UI fonts besides its style font: Outfit 300/400/500 and Cormorant Garamond 400 (4 files, about 65 KB in total, measured as the 4 non-style woff2 requests) because the gallery chrome (buttons, dialogs, footer) uses them. Only ONE of the six style fonts loads | 6.2-B | 9A-3 (client UI pass: decide system fonts or one weight) |
| 122 | The font files are the Latin subset: a title with Devanagari or other non-Latin letters is drawn with the system font of the stack, not the chosen family (readable, but the style is not visible for those letters) | 6.2-B | product decision (add a subset per script, or accept) |
| 123 | Collection Defaults (Settings) still has a "Save defaults" button instead of autosave with the "Collection updated" toast required by the settings rules; only its Typography dropdown was changed in 6.2-B | 6.2-B | 9C-1 |
| 124 | 6.2-B browser QA (six styles, Free and Pro, desktop and 390, blocked font, invalid stored value) ran as throwaway puppeteer scripts outside the repo; only the pure helpers (`typography.test.js`) are in the repo | 6.2-B | QA-A |

## Accepted (no fix needed)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 64 | A watermark or quality setting can make a small photo's Web Size larger; there is no upscaling | 6-D | Accepted (no fix needed) |
| 65 | This only happens when the original is already within 3600 px, so High Resolution gives the same size | 6-D | Accepted (no fix needed) |
| 66 | A stopped worker is an incident, with alerting handled in 11-D / 15-B | 6-D | Accepted (no fix needed) |
| 34 | A drop of more than 200 videos is not a realistic use; the server still checks every file | VID-C | Accepted (no fix needed) |
- Row 32: The admin form cannot set a plan's `max_collections` to 0; empty = unlimited, and the minimum cap is 1 by design.
- Old download rows show "-" for set names (no data existed).
- Video short-preview file does not exist (dead code removed earlier); poster + 1080p MP4 is enough.
- Video limit is per account, not per collection (owner decision made).

## Rule for the agent rules file

```
No "good enough for beta". If you leave any known gap, add a row to docs/KYAPTURE_PRODUCTION_DEBT.md
(gap, chunk that raised it, owning chunk). Never write "beta is fine" in a report.
```