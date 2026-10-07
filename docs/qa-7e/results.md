# 7-E security regression results (Tasks 1-6 + 7-A..7-D)

Date: 2026-10-07. Branch `feature/landing-page-redesign` at `835133a` (no application code changed in 7-E).
Stack: Docker dev (`localhost:3000` nginx SPA image rebuilt from HEAD, fully cached = current; API `:8000`; real Celery
worker; Mailpit). Summary for readers: [docs/KYAPTURE_SECURITY_REPORT.md](../KYAPTURE_SECURITY_REPORT.md).

## 1. Automated tests

| Run | Command | Result |
|---|---|---|
| Backend, full, fresh test DB (no `--keepdb`), detached in the container | `docker exec -d -e CELERY_TASK_ALWAYS_EAGER=true kyapture-backend-1 sh -c "python manage.py test --noinput > /tmp/full7e.log 2>&1; echo EXIT:$? >> /tmp/full7e.log"` | **1373 tests, OK** (no failures, errors or skips), `EXIT:0`, 3042.8 s |
| Frontend unit tests | `npm test` (node --test) | 121 / 121 pass |
| Frontend build | `vite build` (out dir in the session scratchpad, not `frontend/dist`) | built, no error |

## 2. Browser regression (Chrome headless, `docs/qa-7e/qa-script.mjs`)

One Pro photographer and one reset account were created for this run by `docs/qa-7e/seed_7e.py` (`qa7e-*-<timestamp>@example.invalid`,
Pro = a `UserSubscription` on the existing Pro row; the plan rows were only read) and deleted afterwards by their two
exact ids (count printed and checked first: 2 users; cascade removed 1 gallery, 8 assets, 1 ZIP job, 5 sessions,
5 download logs, 1 favorite list). Their media folder and the one ZIP folder were removed by exact path.
**42 of 42 checks pass** in the final run of each phase. Three checks failed first because of the script itself
(a wrong field name `status` instead of `processing_status`; the password error is an `aria-live` region, not
`role=alert`; the PIN gate text was read after the gate instead of before); each was fixed and its phase re-run.

| Phase | Checks (all PASS) |
|---|---|
| owner (desktop 1366) | O1 login through the UI lands on `/dashboard` · O2 gallery created · O3 8 uploads through the workspace file input, all `202` · O4 the worker made 8/8 READY, 0 failed · O5 workspace: 8/8 thumbnails loaded (7 photos + video poster), no empty box · O6 the photographer's photo viewer shows the 1024 px photo · O7 downloads on (High Resolution = 3600 master), published |
| public (desktop 1366 + 390) | P1 8/8 tiles show their image · P2 video plays in the lightbox (`currentTime` 2.96 s, no media error) · P3 a favorite survives a reload · P4 favorites panel shows the photo · P5 Share > Get direct link gives the plain gallery URL, no token · P6 that link opened in a second browser shows 8/8 images · P7 High Resolution single photo downloads (JPEG, 646,863 B, 2448x3264: the master, not the 2,078,361 B original) · P8 the download page starts a ZIP job (job page with its `key`) · P9 the ZIP downloads (`PK`, 6,140,932 B) · P10 the job link (what the ready email carries) downloads the same ZIP in another browser · P11 no failed image request and no page error · M1 390 px: 8/8 tiles show their image · M2 390 px: video plays · M3 390 px: no horizontal overflow |
| close (unpublish, republish) | C1 unpublished: a visitor sees 0 photos · C2 an image URL seen before closing answers 404 · C3 republished: 8/8 tiles load from NEW URLs (no empty box) · C4 video plays |
| password | W1 owner sets a gallery password · W2 visitor gets the password form, 0 photos · W3 a wrong password is refused ("Incorrect password. Please try again.") · W4 the right one: 8/8 tiles load from new URLs · W5 video plays (stream with the unlock token) · W6 the URL seen before the password answers 404 |
| PIN (password + download PIN) | N1 owner sets a PIN · N2 8/8 tiles load after unlocking · N3 Download asks for the PIN first · N4 after the PIN, High Resolution downloads · N5 video still plays |
| original (Pro) | R1 owner switches High Resolution to Original · R2 the downloaded file is the stored original byte for byte (sha256 match, 2,078,361 B; differs from the master) |
| reset | S1 the reset email reaches Mailpit with a `#token=` link · S2 the new password is accepted · S3 login with it lands on `/dashboard` · S4 the old password is refused (400) |

**Empty image boxes: none** in the workspace, the public grid (desktop and 390 px), the favorites panel, after closing and
reopening, after the password, or after the PIN. Screenshots stayed in the session scratchpad (the test photos show real
people from `benchmark/data/jpeg_real`, so they are not committed).

Not run in this browser pass (covered elsewhere or out of reach): the contact allow-list email code (7-B browser run),
deterrence right-click/drag (7-D, 98 checks), the 7-C reset edge cases (31 checks), a real phone long-press (row 143).

## 3. Upload regression with real JPEGs (debt row 138: fail-closed EXIF)

Source: `benchmark/data/jpeg_real` (read and copied only; nothing in `benchmark/` was changed). 103 real files from
15 camera/software combinations. No PNG, HEIC or DSLR raw-converter export (Lightroom, Capture One) exists in the test media.

**a) All 103 files through `strip_exif_gps` (the exact upload code) inside the backend container: 0 refused**;
84 accepted byte-for-byte unchanged, 19 accepted with location removed (independent re-check: no GPS left, the result
decodes).

| Files | Make / model | Software tag (edits) | GPS |
|---|---|---|---|
| 43 | Samsung SM-M013F (phone, 2023) | MediaTek Camera Application | 0 |
| 12 + 2 | Samsung ES55 (compact camera) | firmware; 2 re-saved by Windows Photo Viewer | 0 |
| 10 + 4 + 3 + 2 | Samsung SM-G7102 (phone) | two firmwares, 3 cropped, 2 Windows Photo Viewer | 16 |
| 7 | Sony DSC-W350 (compact camera) | **Adobe Photoshop 7.0** (edited) | 0 |
| 6 + 3 | Samsung GT-S5570 (phone) | firmware; 3 Windows Photo Viewer | 0 |
| 3 + 1 | Samsung SM-G900A (Galaxy S5) | Windows Photo Viewer; 1 cropped | 3 |
| 4 | none (no EXIF at all: scan/export) | — | 0 |
| 2 + 1 | Nokia C3-00, Nokia 206 (feature phones) | firmware | 0 |

**b) 7 of them plus a video uploaded for real through the browser workspace** (phase owner above): all `202`, all READY.
Stored originals compared with the source files (sha256):

| Uploaded as | Source kind | Stored original |
|---|---|---|
| 1-phone-samsung-m01-2023.jpg | phone, no GPS | byte-identical |
| 2-phone-samsung-g7102-gps.jpg | phone with GPS | GPS removed (3,687,720 -> 3,687,074 B), pixels untouched |
| 3-phone-galaxy-s5-gps-edited-winviewer.jpg | phone with GPS, re-saved in Windows Photo Viewer | GPS removed (2,534,246 -> 2,530,058 B) |
| 4-camera-samsung-es55.jpg | compact camera | byte-identical |
| 5-camera-sony-w350-photoshop.jpg | camera, edited in Photoshop 7.0 | byte-identical |
| 6-no-exif-scan-or-edit.jpg | no EXIF | byte-identical |
| 7-phone-nokia-c3.jpg | feature phone | byte-identical |
| 8-video.mp4 | ffmpeg test pattern + audio, 6 s | byte-identical (no location atom) |

Result: the fail-closed rule refused **no** normal photo in this set. Still unknown: PNG files and other cameras (row 138
stays with 15-A for that).

## 4. Final status of every finding

Statuses: **FIXED** (commit), **ACCEPTED** (reason), **DEFERRED** (named chunk). "Re-checked 7-E" = confirmed in the
current code or in the browser run above. Commits: 7-A `8608e04`; 7-B `bdca0e9`; 7-C `a2b214f` + `9d7e039`;
7-D `10470f3` + `ce63161`.

### 4.1 Threat-model findings (docs/security/threat-model.md)

| ID | Finding | Status |
|---|---|---|
| SEC-01 / SEC-24 | Throttle identity and stored IP from client `X-Forwarded-For` | **FIXED** `bdca0e9` (`REST_FRAMEWORK['NUM_PROXIES']`, `apps/core/request_ip.client_ip`). The production proxy must overwrite XFF: **DEFERRED** 14-A/16-A (block in `docs/KYAPTURE_UPLOAD_LIMITS.md`) |
| SEC-02 | Favorites by typed email | **FIXED** `8608e04`; re-checked 7-E (P3/P4) |
| SEC-03 | Contact allow-list trusted a typed email | **FIXED** `bdca0e9` (emailed one-time code) |
| SEC-04 | No PIN/password failure lockout | **FIXED** `bdca0e9` (`apps/clients/lockout.py`); W3 shows the refusal. Thresholds and minimum lengths: **DEFERRED** 13-A (row 135) |
| SEC-05 | Original key derivable from a display URL | **FIXED** in code `bdca0e9` (128-bit random key part). Bucket policy / Block Public Access: **DEFERRED** 15-A |
| SEC-06 | DEBUG `/media/` served private files | **FIXED** `bdca0e9` (public names only; private = signed 1 h URL). Dev ports: SEC-11 |
| SEC-07 | Video stream fell back to the original | **FIXED** `bdca0e9`; P2/M2/C4/W5/N5 play the playback MP4 |
| SEC-08 (row 6) | Owner `original_url` | **FIXED** `bdca0e9` (1 h signed URL, random key; never in public payloads) |
| SEC-09 | Public derivative URLs permanent | **FIXED** for password and unpublish `bdca0e9`; re-checked 7-E (C2, W6: old URL 404, new URLs load). Expiry sweep **DEFERRED** 11-D, CDN invalidation **DEFERRED** 15-A (row 134) |
| SEC-10 | `.env` in the backend image | **FIXED** `bdca0e9` (`backend/.dockerignore`) |
| SEC-11 | Dev DB password in compose, Redis without auth, ports on all interfaces | **DEFERRED** 13-C (row 87). Re-checked 7-E: still 6 published ports on all interfaces |
| SEC-12 | Insecure `SECRET_KEY` fallback in base settings | **ACCEPTED**: production refuses to boot with it (`production.py`); dev only |
| SEC-13 | One signing key, no rotation | **FIXED** `bdca0e9` (`SECRET_KEY_FALLBACKS`, `JWT_SIGNING_KEY`, runbook). Separate IAM principals for S3/SES: **DEFERRED** 13-C (row 88) |
| SEC-14 | Unlock tokens in plaintext, accepted in URLs | Hashing **FIXED** `bdca0e9`. Query-string transport: **ACCEPTED** in 7-E (row 133, section 4.3) |
| SEC-15 | Admin hardening | Login throttle/lock and hidden hashes **FIXED** `bdca0e9`. MFA **DEFERRED** 13-C, network restriction on `/admin/` **DEFERRED** 15-A (row 90) |
| SEC-16 | No email verification at registration | **DEFERRED** RS0-D (row 91; decision recorded in 7-C) |
| SEC-17 | Refresh in the anon 100/day bucket | **FIXED** `bdca0e9` (`token_refresh` 60/h per user) |
| SEC-18 | ffmpeg without timeout | **FIXED** `bdca0e9`. Celery `time_limit` on video/Web Size/ZIP tasks: **DEFERRED** 15-B (row 139) |
| SEC-19 | GPS strip fail-open, video location kept | **FIXED** `bdca0e9`; real-photo check in section 3 (0 of 103 refused). PNG / other cameras: **DEFERRED** 15-A (row 138). Video metadata loss: **DEFERRED** 13-A (row 137, owner decision) |
| SEC-20 | CSP allows `http://localhost:8000` and `'unsafe-inline'`; no `server_tokens off` | **DEFERRED** 15-A (row 95). Re-checked 7-E: still in all copies of `frontend/nginx.conf` |
| SEC-21 | Root container, tag-pinned images, unpinned `bcrypt`/`django-ses`, no CVE audit | **DEFERRED** 15-A (row 96). Re-checked 7-E: still true; no CVE audit was run in 7-E either |
| SEC-22 | No security event logging / alerting | **DEFERRED** 15-A (row 97). Only the gallery lockout bell notification exists (7-B) |
| SEC-23 | Personal-data lifecycle | **DEFERRED** 13-C (row 98) |
| SEC-25 / SEC-26 | QA gallery password/PIN in `docs/qa-1r5e/qa-script.js`; `test_s3_connection` prints a presigned URL | **DEFERRED** 13-C (row 102). Re-checked 7-E: still present |
| SEC-27 | Non-READY download, Web Size fell back to the original | **FIXED** `bdca0e9` |
| SEC-28 | Cookies scoped to `.kyapture.com` | **DEFERRED** 15-A (row 100) |
| SEC-29 | Reference screenshots already pushed | **DEFERRED** 13-C (row 101) |
| SEC-30 | Ready/file links outlived a password/PIN change | **FIXED** `8608e04` |
| SEC-31 | Oversized `client_uid` gave a 500 | **FIXED** `8608e04` |
| 7-C P1-P8 and the rest of section 12 | Access tokens alive after reset/change/logout-all, old links alive, 3-day links, uid oracle, no per-address limit, timing oracle, token in URL path, admin password change, no notice, mixed password policy | **FIXED** `a2b214f` + `9d7e039`; re-checked 7-E (S1-S4). P8 (Host poisoning): not exploitable |
| 7-D | Casual saving (right-click, drag, long-press) | **FIXED** as deterrence `10470f3` + `ce63161`; "not protection" is **ACCEPTED** (row 146). Hero cover / portfolio **DEFERRED** 9B-1 (row 141); real phone long-press **DEFERRED** QA-A (row 143) |

### 4.2 Attack-surface and checklist items without a SEC id

| Item | Status |
|---|---|
| `/health/` has no throttle | **ACCEPTED**: one `SELECT 1`, needed by container probes; edge rate limiting is the proxy's job (14-A/16-A) |
| Logout needs a valid access token, so an expired access cookie skips the blacklist | **ACCEPTED**: the SPA's 401 handler refreshes and retries the logout (`frontend/src/api/axiosInstance.js`, logout is not an excluded auth route); a caller with no valid refresh token has nothing left to blacklist. Not browser-tested in 7-E |
| Every `design_settings` key validated | **ACCEPTED** (verified 7-E): presentation keys, `watermark`, `downloads`, `privacy`, `coverPhoto` are validated; the PUBLIC payload is an allow-list re-validated on read (`apps/clients/serializers.py::get_design_settings`), so nothing else reaches a visitor. Unknown top-level keys from the owner are stored as sent (owner-only data) |
| A `downloads` block PATCHed without some keys resets them (`require_email` back to on, `restrict_contacts` off, `allowed_emails` emptied) | New in 7-E, owner-only via the direct API (the settings screen always sends the whole block, `GallerySettingsPage.jsx`). **DEFERRED** 7R (new row 152) |
| Registration abuse (no CAPTCHA) | `register` 10/h per address **FIXED** `bdca0e9`; verification **DEFERRED** RS0-D |
| CSP on Django-served admin HTML | **DEFERRED** 15-A with row 95 (Django sends `X-Frame-Options: DENY`, nosniff, `Referrer-Policy: same-origin`) |
| Uploaded files served as HTML from the API origin | **FIXED** `bdca0e9` for dev (`/media/` serves public derivative names only; receipts are private + signed); production serves media from S3, another origin |
| Proxy overwrites XFF; TLS; body limit; production manifest; gunicorn timeout | **DEFERRED** 14-A/16-A (rows 54, 73) and 15-A (row 72) |
| DB least privilege and TLS | **DEFERRED** 15-A (row 103) |
| Encryption at rest, media durability, secret manager | **DEFERRED** 15-A / 13-C (rows 82, 88) |
| Disk-space guard for video processing | **DEFERRED** 11-D (alert/quota), 15-A (measure) (row 71) |
| Backups and tested restore | **DEFERRED** 13-C / 15-B (rows 27, 61, 67, 77) |
| Terms / Privacy pages, account deletion, data export | **DEFERRED** 13-B (row 25), 13-C (row 98) |
| Payment approval alerting | **DEFERRED** 15-A with row 97 |
| Host header trust (`USE_X_FORWARDED_HOST`) | **DEFERRED** 14-A/16-A (the proxy must set `Host`, block in `docs/KYAPTURE_UPLOAD_LIMITS.md`) |

### 4.3 Debt rows owned by 7-A, 7-B, 7-C, 7-D or 7-E

| Row | Final status |
|---|---|
| 4, 75 | **FIXED** (part) `bdca0e9`: 413 / storage-full 403 from headers before the body. The rest (body already sent; pixel limit needs the bytes) **DEFERRED** 14-A/16-A (`client_max_body_size`) |
| 5, 79 | **FIXED** `8608e04` |
| 6 | **FIXED** `bdca0e9` |
| 7 | **FIXED** `bdca0e9` (real 403); staging re-check **DEFERRED** 15-A |
| 31 | **DEFERRED** product decision, then 15-A (needs a chunked/resumable upload) |
| 37, 120 | **FIXED** `bdca0e9` |
| 43, 44 | **FIXED** `bdca0e9` |
| 78 | **FIXED** `bdca0e9` (proxy part: 14-A/16-A) |
| 80, 81, 83, 84, 85, 86, 92, 93, 94, 99, 108 | **FIXED** `bdca0e9` (remainders are their own rows: 134-140) |
| 82 | **FIXED** in code `bdca0e9`; bucket checks **DEFERRED** 15-A |
| 88 | **FIXED** `bdca0e9`; IAM split **DEFERRED** 13-C |
| 89 | **FIXED** `bdca0e9`; transport = row 133 |
| 90 | **FIXED** (part) `bdca0e9`; MFA **DEFERRED** 13-C, `/admin/` network restriction **DEFERRED** 15-A |
| 132 | **FIXED** `8608e04` |
| 133 | **ACCEPTED** in 7-E. Re-evaluated: the only real fix is short-lived per-file grants minted by a new API, which changes every gallery download and video play (not small). Reasons it is acceptable now: (1) `Referrer-Policy` keeps the tokens on their own origin: the SPA sends `strict-origin-when-cross-origin` (`frontend/nginx.conf`) and every API response sends `same-origin` (Django default, checked on `:8000`), and the video redirect and file links are on the API origin; (2) every bearer that grants a FILE is short: ZIP file links and private signed URLs live one hour, the download token two hours; (3) the 30-day unlock token is SHA-256 at rest, dies on any password change, is only in the visitor's own browser history/download list (the same device already holds it in `sessionStorage`), and the production access log format drops query strings (`docs/KYAPTURE_UPLOAD_LIMITS.md`). Residual: dev `runserver` prints full request lines; a shared computer's history keeps the unlock token up to 30 days |
| 150 | Owner is 7R (not this chunk); unchanged |

Rows raised by 7-x and owned elsewhere (129-131, 134-149, 151) keep their owners; none changed in 7-E.
