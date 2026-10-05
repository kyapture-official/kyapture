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
| 4 | Upload body is received before the plan check, so a refused file still costs bandwidth | VID-A | VID-C (pre-flight avoids it for honest clients); 7-B for abuse. **PARTLY DONE in VID-C**: honest clients whose browser can read the length no longer upload a refused video. Still OPEN for abusive clients (7-B) and unreadable codecs (row 31) |

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
| 31 | A video whose length the browser cannot read (verified in Chrome: an MPEG-4 Part 2 `.mp4`) uploads in full before the server's ffprobe check can refuse it, so the bandwidth is still spent. The server stays authoritative; only the early refusal is missing (needs a server-side early probe, e.g. chunked/resumable upload) | VID-C | Unassigned (proposed: upload-pipeline chunk, with 7-B) |
| 32 | The admin form cannot set a plan's `max_collections` to 0 (`MinValueValidator(1)`; empty = unlimited). A "no new collections" plan, and so the empty-state button at the cap, is reachable only by a direct row edit. VID-C's real-data test set Free to 0 with a row update (restored to 10) after confirming the form refuses 0. Owner decides whether 0 is a valid cap | VID-C | Unassigned (owner decision, then the plans/limits chunk) |
| 33 | No visible "checking videos" state while the browser reads lengths and waits for the pre-flight (4 reads at a time, 5 s timeout each: a drop of hung files can wait several seconds with no feedback) | VID-C | Unassigned (proposed: 9A-3 upload UI) |
| 34 | The pre-flight rejects a drop of more than 200 videos (HTTP 400); the page then lets the uploads go ahead and the per-file server check decides, so such a batch has no early refusal | VID-C | Unassigned |
| 35 | The pre-flight judges the drop as one batch: if the videos together exceed the plan, none upload (photos still do), even when the first alone would fit. No partial acceptance | VID-C | Unassigned (product decision) |
| 36 | Dashboard sidebar footer reads "FREE PLAN" for a user on an active Pro subscription, while Settings > Plan & Billing shows Pro (seen in the VID-C desktop screenshot; cause not investigated) | VID-C | Unassigned (proposed: 9A-2) |
| 37 | `frontend/nginx.conf` file-header comment (lines 41-45) still says no Content-Security-Policy is added, though one is set below it. Left alone to keep VID-C's nginx diff to `media-src` plus its own comment | VID-C | Unassigned |
| 38 | VID-C browser QA ran as throwaway puppeteer scripts outside the repo (no end-to-end harness in the repo). Upload-request counts are covered in the repo only by unit tests with injected fakes | VID-C | QA-A |

## Accepted (no fix needed)

- Old download rows show "-" for set names (no data existed).
- Video short-preview file does not exist (dead code removed earlier); poster + 1080p MP4 is enough.
- Video limit is per account, not per collection (owner decision made).

## Rule for the agent rules file

```
No "good enough for beta". If you leave any known gap, add a row to docs/KYAPTURE_PRODUCTION_DEBT.md
(gap, chunk that raised it, owning chunk). Never write "beta is fine" in a report.
```