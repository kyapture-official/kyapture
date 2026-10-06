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
| 8 | Hard ceilings 25 MB per image and 5 GB per video are not plan values: owner decision | VID-A | 13-C (owner decides) |
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
| 23 | Multi-part ZIP bell notification only covered by tests, never seen in a browser | 6.4-B | 6-D and QA-A |
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
| 34 | The pre-flight rejects a drop of more than 200 videos (HTTP 400); the page then lets the uploads go ahead and the per-file server check decides, so such a batch has no early refusal | VID-C | Unassigned |
| 35 | The pre-flight judges the drop as one batch: if the videos together exceed the plan, none upload (photos still do), even when the first alone would fit. No partial acceptance | VID-C | product decision, leave |
| 36 | Dashboard sidebar footer reads "FREE PLAN" for a user on an active Pro subscription, while Settings > Plan & Billing shows Pro (seen in the VID-C desktop screenshot; cause not investigated) | VID-C | 9A-1 (App shell) — **MUST FIX** |
| 37 | `frontend/nginx.conf` file-header comment (lines 41-45) still says no Content-Security-Policy is added, though one is set below it. Left alone to keep VID-C's nginx diff to `media-src` plus its own comment | VID-C | Unassigned |
| 38 | VID-C browser QA ran as throwaway puppeteer scripts outside the repo (no end-to-end harness in the repo). Upload-request counts are covered in the repo only by unit tests with injected fakes. BILL-C's browser QA (modal, meters, admin edit, delete) was also throwaway scripts | VID-C, BILL-C | QA-A |
| 39 | docs/pixieset-ref screenshots show an IP address and emails: blur before committing | start | owner, before the first push of that folder |
| 40 | Photo storage (GB) limit: is it enforced at upload with an upgrade modal, and what happens to a user already over a lowered limit | BILL-C | BILL-C. **DONE in BILL-C** (403 `storage_limit_reached`, shared modal, partial batches, over-limit state; gaps in rows 41-46) |
| 41 | Usage counts only the original (`MediaAsset.file_size`). The private Download Master, the WebP derivatives, the video poster and the playback MP4 are stored but not metered, so real storage cost is higher than the plan number. Counting them needs their sizes recorded per row | BILL-C | 13-A (owner decides what "storage" means, then a size column + backfill) |
| 42 | `MediaAsset.file_size` is a 32-bit `integer` column (max 2,147,483,647 bytes, checked in Postgres). A video between 2 GiB and the 5 GB ceiling (row 8) fails the insert and the upload answers 500 `upload_processing_error`; such a file also could not be counted. Needs a BigInteger migration (not run against the host dev DB) | BILL-C | 13-C (with row 8) |
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
| 59 | Cold single Web Size can return 503 web_size_preparing; the client UI shows a generic error | 6-C | 6-D (Preparing state + Retry-After auto-retry) |

Row 36 note: The sidebar label comes from `frontend/src/components/layout/DashboardLayout.jsx`, which maps `user?.is_active_plan` to "Pro Plan" or "Free Plan".
Plan & Billing gets the plan and subscription from `frontend/src/hooks/useSubscription.js` and checks for an active subscription before showing the plan.
Yes, a real paid user can see different labels if the auth-store flag and the live subscription response disagree or one is stale.

## Accepted (no fix needed)

- Row 32: The admin form cannot set a plan's `max_collections` to 0; empty = unlimited, and the minimum cap is 1 by design.
- Old download rows show "-" for set names (no data existed).
- Video short-preview file does not exist (dead code removed earlier); poster + 1080p MP4 is enough.
- Video limit is per account, not per collection (owner decision made).

## Rule for the agent rules file

```
No "good enough for beta". If you leave any known gap, add a row to docs/KYAPTURE_PRODUCTION_DEBT.md
(gap, chunk that raised it, owning chunk). Never write "beta is fine" in a report.
```