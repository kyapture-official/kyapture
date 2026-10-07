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
| 4 | Upload body is received before the plan check, so a refused file still costs bandwidth | VID-A | VID-C (pre-flight avoids it for honest clients); 7-B for abuse. **PARTLY DONE in VID-C**: honest clients whose browser can read the length no longer upload a refused video. Still OPEN for abusive clients (7-B) and unreadable codecs (row 31). Storage (BILL-C): an honest client skips files that cannot fit at click time and sends no request for them; a direct API call still has its body received before the 403 **7-B: PARTLY DONE** - the upload view refuses a body above the largest file limit (413) or from an account with no storage left (403) from its headers alone, before a byte is read (`photos` 7-B tests use a body that raises when read). Bytes already sent still reach the proxy: `client_max_body_size` is the real stop (plan in docs/KYAPTURE_UPLOAD_LIMITS.md, 14-A/16-A). Unreadable codecs: row 31 |
## B. Security (Task 7, Wave 5)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 5 | Favorites are matched by typed email with no verification: anyone can see another person's favorite list in a gallery | 6.4-B | 7-A (add to its prompt). **DONE in 7-A**: proven by failing tests first (`apps/clients/tests/test_tenancy_7a.py`, 14 failures before the fix), then fixed: a list belongs only to the key that made it (browser `client_uid`, else the unlock token); an email is a label, never a lookup. Cross-device gap: row 129 |
| 6 | original_url is returned in the media API: check it against the private-storage rule (Free user must not reach Original) | VID-A | 7-B **7-B: not exploitable for clients** (the public payload never carries it: `test_public_gallery_payload_never_exposes_a_raw_original_url`); the owner's URL is now a 1-hour signed URL (S3, and signed in dev too) to a key with a random part (row 82). DONE |
| 7 | "Direct API refused" for Free users proven by tests and a raw 403 only (curl check failed on token format) | BILL-B | 7-B / 15-A **7-B: DONE with a real request** (Free user, cookie login on :8000, PATCH of a Pro-only setting answered 403; see the 7-B report). Staging re-check stays with 15-A |
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
| 31 | A video whose length the browser cannot read (verified in Chrome: an MPEG-4 Part 2 `.mp4`) uploads in full before the server's ffprobe check can refuse it, so the bandwidth is still spent. The server stays authoritative; only the early refusal is missing (needs a server-side early probe, e.g. chunked/resumable upload) | VID-C | 7-B (add upload body check for abusive clients) **7-B: still OPEN** (needs a resumable/chunked upload that probes the first chunk; the server cannot judge minutes without the bytes). Re-owned: product decision, then 15-A |
| 33 | No visible "checking videos" state while the browser reads lengths and waits for the pre-flight (4 reads at a time, 5 s timeout each: a drop of hung files can wait several seconds with no feedback) | VID-C | 9A-3 |
| 35 | The pre-flight judges the drop as one batch: if the videos together exceed the plan, none upload (photos still do), even when the first alone would fit. No partial acceptance | VID-C | product decision, leave |
| 36 | Dashboard sidebar footer reads "FREE PLAN" for a user on an active Pro subscription, while Settings > Plan & Billing shows Pro (seen in the VID-C desktop screenshot; cause not investigated) | VID-C | 9A-1 (App shell) — **MUST FIX** |
| 37 | `frontend/nginx.conf` file-header comment (lines 41-45) still says no Content-Security-Policy is added, though one is set below it. Left alone to keep VID-C's nginx diff to `media-src` plus its own comment | VID-C | 13-C (fix the stale CSP comment in frontend/nginx.conf during the config audit) **DONE in 7-B** (comment rewritten) |
| 38 | VID-C browser QA ran as throwaway puppeteer scripts outside the repo (no end-to-end harness in the repo). Upload-request counts are covered in the repo only by unit tests with injected fakes. BILL-C's browser QA (modal, meters, admin edit, delete) was also throwaway scripts | VID-C, BILL-C | QA-A |
| 39 | docs/pixieset-ref screenshots show an IP address and emails: blur before committing | start | owner, before the first push of that folder |
| 40 | Photo storage (GB) limit: is it enforced at upload with an upgrade modal, and what happens to a user already over a lowered limit | BILL-C | BILL-C. **DONE in BILL-C** (403 `storage_limit_reached`, shared modal, partial batches, over-limit state; gaps in rows 41-46) |
| 41 | Usage counts only the original (`MediaAsset.file_size`). The private Download Master, the WebP derivatives, the video poster and the playback MP4 are stored but not metered, so real storage cost is higher than the plan number. Counting them needs their sizes recorded per row | BILL-C | 13-A (owner decides what "storage" means, then a size column + backfill) |
| 42 | `MediaAsset.file_size` is a 32-bit `integer` column (max 2,147,483,647 bytes, checked in Postgres). A video between 2 GiB and the 5 GB ceiling (row 8) fails the insert and the upload answers 500 `upload_processing_error`; such a file also could not be counted. Needs a BigInteger migration (not run against the host dev DB) | BILL-C | 13-C (with row 8). **DONE in DB-A**: migration `photos.0008` -> `PositiveBigIntegerField`, run on the Docker dev DB only (rows 61-62 for what is left) |
| 43 | `get_user_subscription_metrics` selects a subscription by `status='active'` only, while entitlements also require `expires_at` in the future. A lapsed plan keeps its paid storage limit until the sweep flips it (runs every 15 minutes) | BILL-C | 7-B **DONE in 7-B** (`get_user_subscription_metrics` requires `expires_at` in the future, like the entitlements; `PlanEdgeTests`) |
| 44 | Only the storage check is repeated under the per-account row lock. The video-minutes check still uses usage read before it, so two parallel direct-API video uploads can pass it together and exceed the minutes by one batch | BILL-C | 7-B **DONE in 7-B** (minutes re-checked against usage read under the account lock; a parallel upload landing during the probe is refused, `PlanEdgeTests`) |
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
| 75 | The server reads the whole body before it can judge a file, so an image over the pixel limit (up to the size limit) or a file over the size limit still costs its bandwidth up to the proxy limit. The browser pre-checks size only; it never decodes, so a too-large-in-pixels image uploads fully before the refusal | UP-A | 7-B (early body check for abusive clients; see rows 4, 31) **7-B: PARTLY DONE** with row 4 (size ceiling from headers). An image over the PIXEL limit still uploads in full before its header is read (same limit as row 31) |
| 76 | Lowering `max_image_pixels` does not touch photos already stored: the worker, Web Size and ZIP code set Pillow's guard from the new value, which raises above twice it, so an old photo larger than that can fail to process or download after the edit | UP-A | owner decision (13-A), then 13-C |
| 77 | `subscriptions.0009_upload_limits` was applied to the Docker dev DB only; the host dev DB and production are not migrated (the row is also created on first read) | UP-A | 13-C, 15-B |

## L. Raised by SEC-0 (security docs, docs/security/; SEC-xx ids in docs/security/threat-model.md)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 78 | SEC-01: `NUM_PROXIES` is a top-level setting (`production.py:242`) but DRF reads it only from `REST_FRAMEWORK`, so throttles key on the raw client-supplied `X-Forwarded-For`; a new header value per request bypasses login, unlock/PIN and reset throttles. `_get_client_ip` (`clients/views.py:135`, `clients/serializers.py:390`) also stores the left-most XFF as the client IP. Needs a proxy that overwrites XFF plus a test | SEC-0 | 7-B **DONE in 7-B**: `REST_FRAMEWORK['NUM_PROXIES']` (0 dev, 1 production); one helper `apps/core/request_ip.client_ip` for every stored/counted IP. Proven: a new X-Forwarded-For per request no longer earns a fresh bucket for login, gallery password and PIN (`users` 7-B `ThrottleIdentityTests`). The proxy must overwrite XFF (block in docs/KYAPTURE_UPLOAD_LIMITS.md, 14-A/16-A) |
| 79 | SEC-02 (widens row 5): a claimed `?email=` also lets any visitor rename, delete and add photos to another visitor's favorite lists (`favorite_lists.py:87-128, 217-222`; `clients/views.py:926-970`) | SEC-0 | 7-A. **DONE in 7-A** (with row 5): read, rename, delete, add-to-list, un-heart, guest-merge and list-name probing via a typed email or an unlock-session email all proven, then refused (404 / own empty list); one email still has one default list |
| 80 | SEC-03: "Restrict Downloads to Specific Contacts" accepts any typed, unverified email that is on the list (`download_access.py:224-229`) | SEC-0 | 7-B **DONE in 7-B**: an address on the list first receives a one-time 6-digit code (10 min, 5 tries, 3 sends per 10 min); only the code earns the token; a PIN use counts once per granted token. Browser-verified (download page, desktop and 390) |
| 81 | SEC-04: download PIN 4-8 digits and gallery password min 4 chars, with no per-gallery failed-attempt counter, backoff or alert; only the per-IP throttle (see row 78) | SEC-0 | 7-B **DONE in 7-B** (`apps/clients/lockout.py`): per client 5 failures / 15 min, per gallery 50 / hour (gate paused 1 h, bell notification `security`); a success clears the client count; a new PIN or password resets. Clear 429 messages in the client UI (browser-verified). Unlock tokens never outlive a password change on any path (the gallery PATCH did keep them alive: fixed). Trade-offs: row 135 |
| 82 | SEC-05: originals and public derivatives share one bucket and the same key prefix; the original's key is derivable from a public display URL, so privacy depends only on per-object ACL. Bucket policy / Block Public Access / Object Ownership not in repo; verify on staging | SEC-0 | 7-B (verify in 15-A) **DONE in 7-B (code)**: originals and Download Masters carry a 128-bit random key part, the image extension follows the bytes. Bucket policy / Block Public Access / Object Ownership still to verify on staging (15-A) |
| 83 | SEC-06: with `DEBUG=True`, `config/urls.py:37-38` serves all of `MEDIA_ROOT` without auth (originals, Download Masters, receipts) and compose publishes `:8000` on all interfaces | SEC-0 | 7-B **DONE in 7-B**: `/media/` (DEBUG) serves public derivative names only; private files need the signed 1-hour URL `SignedFileSystemStorage` hands out. Published dev ports stay with row 87 |
| 84 | SEC-07: `PublicVideoStreamView` redirects to a signed URL of the private original when no playback MP4 exists, and ignores `allow_download` (`clients/views.py:1742-1753`) | SEC-0 | 7-B **DONE in 7-B**: playback MP4 only, else 409 `video_processing` (dev used to 302 to the private original) |
| 85 | SEC-09: public derivatives (WebP tiers, posters, playback MP4) are public-read with permanent URLs and 1-year immutable cache; adding a password, unpublishing or expiry does not revoke URLs already seen | SEC-0 | 7-B **DONE in 7-B** for password added/changed and unpublish: every public file moves to a new random `media_token` segment (Celery `rotate_public_media`), old objects deleted. Expiry and caches: row 134 |
| 86 | SEC-10: no `backend/.dockerignore`; `COPY . .` (`backend/Dockerfile:50`) puts `backend/.env`, `venv/`, `media/`, `logs/` into the image. Not inspected (no build in SEC-0) | SEC-0 | 13-C **DONE in 7-B**: `backend/.dockerignore`; the old image held `/app/.env` and `logs/`, a rebuilt image holds neither (checked with `docker run`); the build passes `CACHE_REDIS_URL` as a placeholder for collectstatic |
| 87 | SEC-11: dev DB password hardcoded in `docker-compose.yml` (5 places) and `development.py:14`, equal to the DB name, in history since the first commit; Postgres, Redis (no auth), Mailpit and Django published on all host interfaces | SEC-0 | 13-C |
| 88 | SEC-13: one `SECRET_KEY` signs JWTs, download/job/file tokens and reset links; no separate JWT key, no `SECRET_KEY_FALLBACKS`, no rotation runbook; S3 and SES share one AWS key pair | SEC-0 | 13-C **7-B: DONE** for `SECRET_KEY_FALLBACKS`, a separate `JWT_SIGNING_KEY` and the runbook (docs/security/secrets.md section 7.1). Still OPEN for 13-C: separate IAM principals for S3 and SES |
| 89 | SEC-14: gallery unlock tokens stored in plaintext (`clients/models.py:61`), visible in admin, and accepted in `?token=` URLs (logs, history) | SEC-0 | 7-B **7-B: DONE** for hashing (SHA-256 at rest, migration `clients.0013` on the Docker dev DB only; favorites keyed by a token moved to the hash; admin hides it). Query-string transport: row 133 |
| 90 | SEC-15: Django admin at the default `/admin/` with no login throttle/lockout, no MFA, no network restriction; gallery admin form shows password/PIN hashes | SEC-0 | 7-B **7-B: PARTLY DONE**: admin login throttle/lock (`apps/core/admin_login.py`), hashes and tokens excluded from admin forms. Still OPEN (13-C / 15-A): MFA (plan in secrets.md 7.2) and a network restriction on `/admin/` |
| 91 | SEC-16: no email verification at registration | SEC-0 | 7-C |
| 92 | SEC-17: token refresh has no own throttle and falls under `anon` 100/day per IP (~96 refreshes/day per active user); several users behind one NAT can be logged out. Not runtime-tested | SEC-0 | 7-B **DONE in 7-B**: `token_refresh` 60/h per verified user id (3 users behind one address: 102 refreshes, no 429) |
| 93 | SEC-18: ffmpeg poster/transcode `subprocess.run` has no timeout (`core/utils.py:868, 895`); no Celery time limits | SEC-0 | 7-B **DONE in 7-B**: every ffmpeg/ffprobe call has a timeout (transcode 600 s + 3 s per video second); `process_photo_asset` soft/hard 600/660 s. Video task limit: row 139 |
| 94 | SEC-19: GPS strip fails open (`core/utils.py:329`); video location metadata is never stripped and video originals are served to clients | SEC-0 | 7-B **DONE in 7-B**: photos fail closed (400 `location_strip_failed`), EXIF GPS + XMP GPS + PNG eXIf; video originals remuxed without location (stream copy, fail closed), poster/playback made with `-map_metadata -1`. Side effects: rows 137, 138 |
| 95 | SEC-20: one `nginx.conf` CSP for every build allows `http://localhost:8000` and `style-src 'unsafe-inline'`; no `server_tokens off` | SEC-0 | 15-A |
| 96 | SEC-21: backend container runs as root; base images by tag not digest (`redis:alpine`, `mailpit:latest` float); `bcrypt` and `django-ses` unpinned; no CI dependency audit; CVE status of current versions not checked | SEC-0 | 15-A |
| 97 | SEC-22: no security event logging (failed login/unlock/PIN, 429s, payment approvals), no off-host log shipping, no error tracking or alerting | SEC-0 | 15-A |
| 98 | SEC-23: no account deletion or data export; client IP + email kept 365 days (DownloadLog) and 30 days (ClientSession); retention not decided by the owner | SEC-0 | 13-C |
| 99 | SEC-27: single-photo download does not require READY; for a non-READY image `resolution=web` can fall back to the original (`clients/views.py:1838, 1919-1922`). Needs the asset UUID; not reproduced | SEC-0 | 7-B **DONE in 7-B**: READY required; Web Size never falls back to the original |
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
| 108 | The per-user feedback throttle (and every other DRF throttle) uses Django's default cache. No `CACHES` is configured, so it is the per-process local-memory cache: with several gunicorn workers each worker counts separately, so the real limit is higher than `feedback: 5/hour`. Needs a shared cache (Redis is already in the stack) | 6.3-A | 7-B **DONE in 7-B**: Redis cache (`CACHE_REDIS_URL`; compose db 2, `manage.py test` db 3); production refuses to boot without it. Proven with 2 gunicorn workers: before 9 of 20 logins passed a 5/min limit, after exactly 5. Production manifests must set it on web and every worker (14-A/16-A) |
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
| 120 | `frontend/nginx.conf` CSP (three copies) still allows `https://fonts.googleapis.com` in `style-src` and `https://fonts.gstatic.com` in `font-src`. Nothing loads from them any more; leaving them widens the policy for no reason | 6.2-B | 15-A (with row 95, the CSP audit) **DONE in 7-B** (both hosts removed from the three CSP copies; `frontend/src/security/nginxCsp.test.js`) |
| 121 | A client gallery still downloads the app UI fonts besides its style font: Outfit 300/400/500 and Cormorant Garamond 400 (4 files, about 65 KB in total, measured as the 4 non-style woff2 requests) because the gallery chrome (buttons, dialogs, footer) uses them. Only ONE of the six style fonts loads | 6.2-B | 9A-3 (client UI pass: decide system fonts or one weight) |
| 122 | The font files are the Latin subset: a title with Devanagari or other non-Latin letters is drawn with the system font of the stack, not the chosen family (readable, but the style is not visible for those letters) | 6.2-B | 6.2-C **DONE for Devanagari in 6.2-C**: Noto Sans/Serif Devanagari, five self-hosted woff2 files behind `unicode-range`, in each style's stack; a Latin-only gallery requests none, a Devanagari title exactly one (60 browser runs, six styles, desktop and 390). Other scripts and the Latin Extended letters: row 126 |
| 123 | Collection Defaults (Settings) still has a "Save defaults" button instead of autosave with the "Collection updated" toast required by the settings rules; only its Typography dropdown was changed in 6.2-B | 6.2-B | 9C-1 |
| 124 | 6.2-B browser QA (six styles, Free and Pro, desktop and 390, blocked font, invalid stored value) ran as throwaway puppeteer scripts outside the repo; only the pure helpers (`typography.test.js`) are in the repo. The 6.2-C browser QA (60 hero runs, toolbar, Design tab, Preview) is the same: only `scriptRuns.test.js` and `styles/fonts.test.js` are in the repo | 6.2-B, 6.2-C | QA-A |
| 125 | Devanagari outside a collection title (photographer name, set tabs, descriptions, buttons, the dashboard header and workspace title) is not in a `.ky-type` element, so it uses the UI font stack (Outfit, then a system font); it is readable but not styled | 6.2-C | 9A-3 (client UI pass, with row 121) |
| 126 | Only Latin and Devanagari have a style font. Other scripts (Arabic, CJK, Thai, Cyrillic, Greek) and Latin letters outside the Latin subset (Polish ł, Vietnamese, Turkish ğ) still fall to the system font of the stack | 6.2-C | 9A-3 (add a subset when a photographer needs one; same unicode-range pattern) |
| 127 | In the photographer's Design tab, a Devanagari title makes the browser fetch up to three Devanagari files (about 150 KB, cached afterwards) instead of one: the Live Preview first draws with the app-default look before the style list arrives (serif 400), and its `transition-all` animates the font weight from 400 to the style's weight (sans 400 then 600). The client gallery is not affected (exactly one) | 6.2-C | 9C-1 (Design page pass) |
| 128 | Older browsers show the Devanagari slightly small (no `size-adjust`: Safari before 17) and lines of a mixed title uneven (no `:has()`: Chrome before 105, Firefox before 121). The span-level letter-spacing and line height still apply | 6.2-C | 13-C (browser support decision before release) |


## Q. Raised by 7-A (tenancy, docs/security/threat-model.md section 9)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 130 | Lists made on a protected gallery BEFORE 7-A are keyed by an old unlock token. They move to the browser's `client_uid` on the first call that carries both (same tab); once that tab is closed nothing links them to the visitor any more (the photographer still sees them). Also: an emailed ready link issued before 7-A on a gallery that has a password or PIN now reads as expired (no gate fingerprint): the visitor prepares the download again | 7-A | 13-A (release notes) |
| 131 | A deactivated photographer's published galleries stay public: `PublicGalleryView` and the other public lookups do not check `photographer.is_active` (only the portfolio does). Their API tokens stop at once (tested). Decision: when an owner is suspended or deactivated, their galleries stop being public (404) and downloads stop; reactivation restores them. | 7-A | 7.5-A |
| 132 | `GET /photos/{slug}/status/?ids=not-a-uuid` on one's OWN gallery answered 500 (ORM ValidationError); proven by `test_a_malformed_id_in_a_query_is_a_clean_answer_not_a_500` | 7-A | 7-A. **DONE in 7-A**: malformed ids are ignored like unknown ones |

## R. Raised by 7-B (downloads, throttles, headers, uploads; docs/security/threat-model.md section 10)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 133 | The unlock token (30 days), the download token (2 h) and file tokens still travel in query strings where the browser cannot send a header (`<a href>` downloads, `<video src>`): they land in browser history and the download manager. Hashed at rest and kept out of the app's own logs; the proxy log format without query strings is in docs/KYAPTURE_UPLOAD_LIMITS.md. Needs short-lived per-file URL grants minted by the API | 7-B | 7-C |
| 134 | Public URLs move on password/unpublish only: a gallery that EXPIRES keeps its public URLs until purge, and copies already in a browser cache or a CDN edge stay up to a year (`immutable`). Needs an expiry sweep that rotates, and a CDN invalidation of the old prefix when a rotation runs. 7-D audit: confirmed, a public derivative URL is never short-lived (only private originals, masters and ZIP links are, at one hour) | 7-B | 11-D (sweep), 15-A (CDN) |
| 135 | The gallery-level lockout (50 wrong PINs or passwords per hour pauses the gate for everyone for 1 h) can be triggered on purpose by anyone with the link; the photographer is told and can reset by changing the secret. PIN stays 4-8 digits and the password 4+ characters | 7-B | 13-A (owner: thresholds and minimum lengths) |
| 136 | The email-code step sends mail synchronously in the request (`EMAIL_TIMEOUT` 10 s); a slow SES answer delays the form. It also still tells someone who passed the PIN whether an address is on the list (403 vs 202), as before | 7-B | 15-A |
| 137 | Removing a video's location remuxes the original: video and audio packets are byte-identical, but all container metadata (creation date, camera tags) and data/timed-metadata tracks are dropped when a location is found, and `file_size` changes slightly | 7-B | 13-A (owner decision) |
| 138 | A JPEG/PNG whose EXIF cannot be parsed is now refused (fail closed) even if it has no GPS; the rate on real camera files is unknown | 7-B | 15-A (run a real photo set) |
| 139 | `process_video_asset`, the Web Size and ZIP tasks have no Celery `time_limit` (video is bounded by the ffmpeg timeouts, which grow with the video's length) | 7-B | 15-B |
| 140 | `clients.0013` (hash unlock tokens), `clients.0014`, `galleries.0010` (`media_token`) and `users.0008` were applied to the Docker dev DB only; host dev DB and production are not migrated. `clients.0013` is not reversible (a hash cannot become the token again) | 7-B | 13-C, 15-B |

## S. Raised by 7-D (client-gallery deterrence, docs/security/threat-model.md section 11)

7-D owned no OPEN rows when it started (rows 91 and 133 belong to 7-C).

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 141 | The client gallery's hero cover image (the same watermarked derivative as a tile) has no right-click/drag deterrence: 7-D's scope was the photo and video tiles, lightbox and slideshow. The portfolio page (`ClientHomePage`) photos were not touched either | 7-D | product decision (13-A), then 9A-3 |
| 142 | A grid tile (the `div` with the click handler) has no `tabindex` or role: a keyboard user can Tab to the heart, download and share buttons of each tile but cannot open the lightbox from the grid (checked in a browser; the toolbar slideshow button opens it at photo 1 only). Not caused by 7-D; the tile controls were also invisible while focused on desktop, fixed in 7-D | 7-D | 9A-3 |
| 143 | A real long-press on a phone was not exercised: headless Chrome fires no `contextmenu` for a held touch. Proven only: the handler cancels a `contextmenu` on a tile, `-webkit-touch-callout: none` and `user-drag: none` are set, the photo is `pointer-events: none` so the tile is the touch target, and touch scrolling still works from a tile. The iOS Safari and Android Chrome menus need a real device | 7-D | QA-A, 15-A |
| 144 | In touch emulation a raw rightward swipe in the lightbox is taken by Chrome's history-back gesture and navigates away (the pre-7-D build does the same, proven by building it from `b06280c`). The lightbox stage sets no `touch-action`; `pan-y` would keep vertical scroll and leave horizontal swipes to the app. Not checked on a real phone | 7-D | 9A-3 |
| 145 | The 7-D browser QA script is in `docs/qa-7d/qa-script.mjs`, but the seeding (real upload through the worker of 8 images with a watermark and one video) was a throwaway script outside the repo. Same pattern as rows 38, 114 and 124 | 7-D | QA-A |

## Accepted (no fix needed)

| # | Gap | Raised in | Owner chunk |
|---|-----|-----------|-------------|
| 64 | A watermark or quality setting can make a small photo's Web Size larger; there is no upscaling | 6-D | Accepted (no fix needed) |
| 65 | This only happens when the original is already within 3600 px, so High Resolution gives the same size | 6-D | Accepted (no fix needed) |
| 66 | A stopped worker is an incident, with alerting handled in 11-D / 15-B | 6-D | Accepted (no fix needed) |
| 34 | A drop of more than 200 videos is not a realistic use; the server still checks every file | VID-C | Accepted (no fix needed) |
| 129 | Favorites no longer follow a typed email across devices: a typed email no longer links two devices; linking needs email verification | 7-A | Accepted (no fix needed) |
| 146 | Deterrence is not protection: a visitor can still take a screenshot, read the network tab, copy a public derivative or playback URL, use the native video controls (playback speed, picture-in-picture, cast) and use any download the photographer allows. The deterrence only removes the right-click menu, drag and long-press callout on the media. No copy may say otherwise (enforced by `frontend/src/security/honestCopy.test.js`) | 7-D | Accepted (inherent; no fix possible short of DRM) |
- Row 32: The admin form cannot set a plan's `max_collections` to 0; empty = unlimited, and the minimum cap is 1 by design.
- Old download rows show "-" for set names (no data existed).
- Video short-preview file does not exist (dead code removed earlier); poster + 1080p MP4 is enough.
- Video limit is per account, not per collection (owner decision made).

## Rule for the agent rules file

```
No "good enough for beta". If you leave any known gap, add a row to docs/KYAPTURE_PRODUCTION_DEBT.md
(gap, chunk that raised it, owning chunk). Never write "beta is fine" in a report.
```