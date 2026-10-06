# KYAPTURE compression calibration (chunk 6-A)

Scope: measurement only. No production code, no `benchmark/` edit, no 103-image run. Raw logs and candidate files were kept in the scratchpad, not in the repo.

Owner quality floor: Free clients get High Resolution (3600 px) and Web Size, both compressed; Pro gets the real Original (byte-identical). Compression touches only the Download Master / derivatives, must look the same to a photographer, and must not make speed or UX worse.

## 1. Audit: upload -> original -> derivatives -> Download Master -> single / ZIP

| Step | Where | Finding |
|------|-------|---------|
| Upload | `photos/views.py:228` `strip_exif_gps` -> `MediaAsset.original_file` | Bytes stored as uploaded. Only if the file carries EXIF GPS is the APP1 segment rewritten with `piexif.insert` (pixel data never decoded). No GPS = same bytes. |
| Derivatives | `photos/tasks.py:196` `process_image_pipeline` | Reads the original (`seek(0)` afterwards), writes only `display/medium/thumbnail/download_file/blurhash` via `save(update_fields=...)`. Never writes `original_file`. |
| Download Master | `core/utils.py:466-550` `_make_download_master` | Normalise to sRGB, thumbnail to 3600 px, then **11 Pillow encodes + a PSNR check each**, smallest with PSNR >= 35 wins. Returns `None` if every candidate is larger than the original. |
| Client single | `clients/views.py:226` `_get_client_download_source` | `effective_high_res_mode == 'original'` (Pro) -> `original_file`; else `download_file`; falls back to `original_file` only when no master exists. |
| Client ZIP | `clients/download_jobs.py:149-221` | Same resolver (`_resolve_zip_source`), streamed with `ZIP_STORED`, no re-encode. |
| Web Size | `clients/web_size.py` | Derived per request from the master: Pillow q90, baseline, `optimize=True`. |

Evidence that originals stay untouched (run on 10 real files, `strip_exif_gps` + `process_image_pipeline` + `process_download_master` + `regenerate_display_derivatives`): SHA-256 of the stored original is identical before and after in 10/10. Upload bytes equal the source file in 8/10; the 2 that differ carry EXIF GPS (privacy strip, by design). Existing tests: `test_image_pipeline`, `test_single_photo_download_1r5d`, `test_download_policy_1r6`: 67 tests OK (`CELERY_TASK_ALWAYS_EAGER=true`).

## 2. Calibration

Method: 10 JPEGs from `benchmark/data/jpeg_real`: portrait/skin (landscape and portrait), 2 low-light, foliage, sky gradient (720x1600, small), 2 sources > 3600 px (4248x2898 scan, 2988x5312), outdoor kids/skin, 1600 px small. Reference = oriented, sRGB-normalised, Lanczos to 3600 px (exactly what the helper encodes). Encoders: current helper called as production calls it; Pillow `optimize+progressive` 4:2:0; MozJPEG 5.0.0 `cjpeg -optimize -progressive`; jpegli (google/jpegli 031a0077) `cjpegli --progressive_level=2`. Score: SSIMULACRA2 (benchmark build) of the PPM reference vs the candidate JPEG. Time: median of 3 (current: 1 run). CLI times include process start and are measured on the Windows host; Linux is in section 3.

Sky gradient: its original (121 KB) is smaller than every re-encode, so the current helper makes no master (serves the original). Table rows use the other 9 images; the sky image is in Appendix A.

| Encoder (4:2:0 unless noted) | Total KB (9 imgs) | vs current | SSIMULACRA2 mean / min | SS2 delta vs current (min / mean / max) | Encode ms median / max |
|---|---|---|---|---|---|
| **Current helper** | 8498 | - | 83.19 / 81.30 | - | 6168 / 12533 |
| Pillow q85 | 8778 | +3.3% | 83.88 / 81.84 | +0.54 / +0.69 / +0.90 | 220 / 375 |
| Pillow q86 | 9283 | +9.2% | 84.38 / 82.59 | - | 167 / - |
| MozJPEG q85 | 6871 | -19.1% | 81.79 / 80.73 | -5.49 / -1.41 / -0.07 | 1603 / 2790 |
| jpegli q85 | 5943 | -30.1% | 80.35 / 79.16 | -6.73 / -2.84 / -1.44 | 254 / 846 |
| jpegli q88 | 7089 | -16.6% | 82.88 / 81.81 | -2.60 / -0.32 / +0.63 | 276 / 397 |
| **jpegli q90 (distance 1.0)** | **8019** | **-5.6%** | **84.41 / 83.20** | **+0.43 / +1.22 / +2.09** | **272 / 376** |
| jpegli q85, 4:4:4 | 7253 | -14.6% | 82.52 / 81.33 | -3.40 / -0.67 / +0.32 | 345 / 483 |
| jpegli q88, 4:4:4 | 8405 | -1.1% | 84.18 / 82.99 | +0.33 / +0.99 / +2.08 | 352 / 498 |
| jpegli q90, 4:4:4 | 9659 | +13.7% | 85.73 / 84.48 | +2.00 / +2.54 / +3.85 | 371 / 537 |

Reading it:
- jpegli q90 4:2:0 is the only row that is at least as good as current on every image (SS2 +0.43 minimum) and smaller in total (-5.6%). At the same SS2 as jpegli q90, Pillow needs q86 and +15.8% more bytes than jpegli (9283 vs 8019 KB).
- Encode time: current 5.5-12.5 s per image (Celery worker CPU, per upload), every fixed encoder 0.2-0.4 s; current/jpegli ratio 13x-33x (median 24x), CLI start included.
- jpegli q85 is smaller but below the current quality on every image (-1.4 to -6.7 SS2): it breaks the floor. 4:4:4 buys quality at a size cost and is not needed.
- Visual check at 100% on the skin crop (reference / current / jpegli q90 / jpegli q85): no visible difference between reference, current and q90.
- Your directional figures (jpegli@85 ~917 KB / 85.6) do not reproduce on this set with 4:2:0 (jpegli q85: 660 KB average, 80.4). jpegli q90 4:4:4 here is 1073 KB average at 85.7, so your run probably used another chroma mode or a threshold search. I did not run the 103 set (not allowed), so this is a gap between two configurations, not an error I can pin down.
- Web Size (same 10 images at 2048 px, informational, not part of the recommendation): current Pillow q90 baseline 5296 KB / SS2 86.18; jpegli q90 3833 KB (-28%) / 84.60; jpegli q85 2953 KB / 80.76.

## 3. Linux Docker image check

Image `kyapture-backend` = `python:3.12-slim` on Debian 13 trixie x86_64.
- Debian `libjxl-tools` (0.11.2) ships `cjxl/djxl/jxlinfo` only, **no `cjpegli`**. `pyjpegli` 0.3.1 wheel exists but exposes only `quality` (no subsampling or progressive control) and is a single-maintainer beta: not used.
- Built `cjpegli` from the pinned google/jpegli source in a throwaway container (cmake + ninja, Release, static jpegli, `-DBUILD_SHARED_LIBS=OFF`): 124 s, stripped binary 1.1 MB. Its only shared libs (`libpng16`, `libz`, `libstdc++`, `libgcc_s`, `libm`, `libc`) already resolve in the runtime image with no extra apt packages.
- Ran inside the runtime image on the 10 samples: 10/10 encode and decode in Pillow; same input gives byte-identical output over 3 runs; Linux q90 output is within 0.01% of Windows size and the same SS2 (p450: 84.59 vs 84.57); Linux encode median 516 ms / max 683 ms per 3600 px image; peak RSS of the encoder process 193 MB.
- Stress: 80 encodes of a 3600x2700 image, 4 in parallel: 80/80 OK, one unique output size, wall 38.7 s (about 1.9 s each under 4-way contention on 12 cores, p95 3.8 s). A truncated input exits non-zero and writes no file (so the caller can detect failure).
Verdict: jpegli runs reliably in the Docker image. No blocker.

## 4. Recommendation (one fixed encode, no search)

**Download Master for JPEG sources: one fixed jpegli encode, quality 90 (distance 1.0), 4:2:0, `--progressive_level=2`, after the existing sRGB normalise + 3600 px Lanczos resize.** Production runs no SSIMULACRA2, no candidate search, no PSNR loop.

Deterministic guard (not a search), max 2 encodes in the worst case:
1. Encode q90. If the output is <= the original size, use it.
2. Otherwise encode q85 once. If that is <= the original size, use it.
3. Otherwise: if the source long edge is <= 3600 px, make no master (existing behaviour: the original is served; it is smaller and the same pixels). If the source long edge is > 3600 px, **keep the q85 master anyway**: the 3600 px cap is what the Free tier is promised, and serving a >3600 px original there would leak resolution (see debt row 50).

Pro Original stays untouched. PNG sources keep the current lossless path.

Implementation notes for the next chunk (6-B, not done here): multi-stage `Dockerfile` that builds `cjpegli` at the pinned commit (build stage only, copy the stripped binary to the runtime stage); call it with `subprocess.run([...], timeout=60)` on a temp PPM; on missing binary, non-zero exit or timeout, log a warning and fall back to Pillow `quality=86, optimize, progressive, subsampling=4:2:0` (measured: SS2 84.38 mean, +15.8% bytes vs jpegli, ~170 ms); tests must cover the fallback.

## 5. 6-B result (encoder implemented)

Implemented as recommended in section 4: `apps/core/utils.py` `_make_download_master` -> `_make_jpeg_master_bytes` -> `_encode_jpegli` (cjpegli at `/usr/local/bin/cjpegli`, fixed argv, `shell=False`, 60 s timeout, private temp dir removed in `finally`, stderr logged server-side only). q90 -> q85 once -> (uncapped source: no master, original served; capped source: keep the q85 master). Unusable cjpegli (missing, non-zero exit, timeout, undecodable or wrong-size output) -> one Pillow q86 encode under the same rule. PNG stays lossless; a PNG above 3600 px now also keeps its capped master (same leak as row 50). The 11-encode + PSNR search is gone.

Measured in the rebuilt `kyapture-backend` image (Linux, dev host), 12 real JPEGs (`benchmark/data/jpeg_real`, every 9th file, copied out read-only), entry point `process_download_master` as the Celery task path calls it; old = the helper at `HEAD`; SSIMULACRA2 against the oriented, sRGB, 3600 px Lanczos reference:

| | old helper | new (jpegli q90) |
|---|---|---|
| Total size (12 files) | 11102 KB | 10835 KB (-2.4%; originals 25317 KB, -57.2%) |
| SSIMULACRA2 mean / min | 82.94 / 80.60 | 84.66 / 82.55 |
| SS2 delta per image | - | min +0.37, mean +1.73, max +2.84 (no image worse) |
| Encode time median / max | 6113 / 9222 ms | 484 / 1492 ms (median of 3) |

Per image the size moves from -33.2% to +7.0% (two files grew: +6.6% at SS2 +2.45, +7.0% at SS2 +1.68). Every master is at least as good as the old one and 12.6x faster at the median.

Limits: 12 files, largest 3648 px, no 24 MP+ DSLR; Linux dev-host timings (row 51). No visual crop review was repeated in 6-B; the 6-A 100% skin-crop check used the same encoder settings.

## 6. 6-C result (Web Size: encoder decision, exact-px cache)

### 6.1 Encoder decision (debt row 49): Pillow q90 stays

Method: the 12-file sample of 6-B (`benchmark/data/jpeg_real`, every 9th file, copied out read-only). Each file went through `process_download_master` (the real jpegli q90 master), then the master was resized with Lanczos to 2048 / 1024 / 640 px (what Web Size does). Reference = that resized RGB image (PPM). Candidates: the current Pillow q90 baseline (`optimize`, not progressive) and `cjpegli` (Linux, backend image, 4:2:0, progressive level 2) at q78-q96. Score: SSIMULACRA2 (benchmark build). Rule: use jpegli only at a quality whose score is >= the Pillow q90 score on EVERY image and saves >= 10% bytes.

| px | Pillow q90 total KB / SS2 mean / min | lowest jpegli q with SS2 >= Pillow on all 12 | its size vs Pillow | smaller jpegli rows |
|---|---|---|---|---|
| 2048 | 6903 / 87.01 / 83.93 | q95 (min delta +0.07) | **+12.3%** (7751 KB) | q94 +0.1% (worse on 1, min -1.66), q93 -6.1% (worse on 1, min -2.42), q92 -14.2% (worse on 6), q90 -23.7% (worse on 10, min -4.96) |
| 1024 | 2227 / 85.04 / 81.09 | q96 (q95 is -0.02 on one image) | **+30.7%** (2911 KB) | q93 -1.7% (worse on 1), q92 -10.6% (worse on 2, min -3.87), q90 -21.4% (worse on 11) |
| 640 | 967 / 84.48 / 80.34 | q95 (min delta +0.17) | **+20.6%** (1167 KB) | q93 +0.7%, q92 -8.2% (worse on 2), q90 -18.9% (worse on 10) |

Median encode time per image: Pillow 40 / 11 / 5 ms (2048 / 1024 / 640); cjpegli 168-204 / 52-62 / 26-31 ms (process start + PPM write included).

Result: no jpegli quality satisfies "not worse on any image" AND "saves >= 10%". The only qualities that are not worse anywhere are LARGER than Pillow q90 (+12% to +31%). Row 49's earlier "-28%" compared jpegli q90 at a lower SSIMULACRA2 (84.60 vs 86.18). **Decision: Web Size keeps Pillow q90 baseline; no cjpegli call and therefore no cjpegli fallback path exists for Web Size.** Pillow is also 4-6x faster per image.

### 6.2 Exact-px cache

`apps/clients/web_size.py`: one private-storage object per (photo, px, watermark state, source), `photographers/<id>/galleries/<id>/web_size/<asset id>/<px>-<watermark signature or "clean">-<source fingerprint>.jpg`. The source fingerprint is the Download Master (or original when no master) name + byte size + encoder settings, so a master re-encoded in place never serves a stale size. Derived from the Download Master, at the exact px (never upscaled), standard baseline JPEG. A single download asks the `generate_web_size` Celery task on a miss (queue `websize`, worker `--concurrency=2`, so at most 2 encodes at a time); a ZIP job is already a Celery task and encodes inline on a miss. A worker that does not answer within `WEB_SIZE_WAIT_SECONDS` (25) gives 503 `web_size_preparing`, never a wrong-size file.

Which downloads are watermarked: **Web Size: yes** (the gallery's current watermark, the same as the web tiers; cache key changes with the watermark state). **High Resolution: no** (the 3600 px Download Master is the clean deliverable, `apps/core/watermark.py` contract, unchanged). **Original (Pro): never** (byte-identical file).

### 6.3 Cold vs warm, 20-photo Web Size ZIP (2048 px)

Docker dev stack, 12 cores, 20 real JPEGs from `jpeg_real` (41.2 MB uploaded through the real API, real masters), Free plan, time from the prepare POST until the job reports `ready` (poll every 50 ms), ZIP = 20 entries / 10.38 MB in every run.

| | runs (s) | median |
|---|---|---|
| Before 6-C (HEAD, every ZIP re-encodes) | 6.54, 6.66, 7.00 | 6.66 |
| 6-C cold (cache emptied) | 5.28, 6.15, 6.85, 7.33, 8.87 | 6.85 |
| 6-C warm (cache hit) | 0.12, 0.13, 0.15, 0.21, 0.23 | 0.15 |

Single photo (2048 px, through the real `websize` worker): cold preflight 131-276 ms (3 runs), warm preflight 20-26 ms, warm download 34-47 ms; worker task 97-164 ms.

Cold is the same as before within noise (+3% at the median); warm is 44x faster. Outliers, reported as measured: four warm runs taken in the same shortage window read 0.37, 0.83, 0.94 and 2.61 s (not in the table); the first three cold runs right after the worker restart took 27, 46 and 63 s of task time, and one later run took 41 s end to end with a 6.9 s task, while the host was short on memory (Claude Code killed a background docker build for it in the same period). Direct in-container timing of the same 20 cold builds was 7.43 s, and 5 clean runs afterwards were 5.3-8.9 s. I did not find another cause.

## 7. 6-D result (all download paths with the new master + acceptance)

Scope: proof, plus the fixes the proof forced. Encoder unchanged from 6-B/6-C.

### 7.1 Acceptance: 9 real photos, old vs new Download Master

Photos: `benchmark/data/jpeg_real` (copied out read-only): skin/hair/jewellery, long hair on a portrait, EXIF-rotated phone shots (orientation 6), a water reflection with hard edges, two ICC-tagged scans above 3600 px, a 2988x5312 tall file, a 720x1600 sky/tea-garden gradient, a wire cage on sand (thin lines), a low-light child shot. Script: `backend/scripts/acceptance_download_master.py` (run in the backend container; old = `apps/core/utils.py` at 9e17cdc, the helper before 6-B). Idle dev host, Linux container. Encode time = `process_download_master` end to end (decode, sRGB, resize, encode, output check): new = median of 3, old = one run. SS2 = SSIMULACRA2 of the oriented sRGB 3600 px reference vs the file.

| # | Photo | Original KB / px | Old KB | New KB | New px | New ms (old ms) | SS2 old / new | Pillow fallback KB / ms |
|---|---|---|---|---|---|---|---|---|
| 1 | Copy of Picture 450.jpg | 2712 / 3648x2736 | 1546 | 1533 | 3600x2700 | 1200 (9033) | 82.71 / 84.59 | 1669 / 617 |
| 2 | Copy of Picture 354.jpg | 2632 / 2736x3648 | 1215 | 1101 | 2700x3600 | 945 (7319) | 82.82 / 84.07 | 1330 / 635 |
| 3 | 20241004_055321.jpg | 1931 / 3264x2448 | 767 | 732 | 2448x3264 | 418 (5040) | 83.9 / 85.71 | 834 / 241 |
| 4 | DSC04784.JPG | 2251 / 4248x2898 | 893 | 810 | 3600x2456 | 1243 (6318) | 81.95 / 83.38 | 989 / 1092 |
| 5 | DSC04790.JPG | 1989 / 2888x3968 | 893 | 786 | 2620x3600 | 1090 (6834) | 82.81 / 83.56 | 990 / 994 |
| 6 | 20150508_130700.jpg | 2534 / 2988x5312 | 861 | 789 | 2025x3600 | 676 (5210) | 83.72 / 84.69 | 942 / 635 |
| 7 | FB_IMG_1688025554368.jpg | 124 / 720x1600 | none | none (original served) | 720x1600 | 110 (294) | - | none |
| 8 | 20240511_184817.jpg | 3078 / 3264x2448 | 1280 | 1275 | 2448x3264 | 487 (6326) | 80.8 / 83.35 | 1405 / 368 |
| 9 | 20230605_154750.jpg | 2078 / 3264x2448 | 779 | 647 | 2448x3264 | 341 (5450) | 82.78 / 83.56 | 864 / 245 |

Totals over the 8 photos that get a master: old 8233 KB, new 7673 KB (-6.8%). SSIMULACRA2 new > old on all 8 (+0.7 to +2.5). Encode time: median 676 ms vs 5450 ms (old 5.0-9.0 s, new 0.34-1.24 s).

Gate results:
- Originals intact: SHA-256 of every source file identical before/after (9/9, `original_intact: true`); in the browser run the Pro Original downloads are byte-identical to the uploads (4/4 single and ZIP).
- 3600 rule / no upscale: every new master is <= 3600 px on the long edge and never larger than its source. Orientation: both EXIF-6 files come out upright (2448x3264) with no orientation tag left.
- Colour: mean RGB shift against the reference is -0.04 to +0.08 levels per channel on all 8 (mean abs diff 0.9-1.6); the two ICC scans are in sRGB with no shift.
- Fallbacks: with cjpegli pointed at nothing, all 8 still produce a valid <= 3600 px master through the Pillow q86 path (1.1-1.4x bigger than jpegli, 241-1092 ms). A source whose re-encode is larger than itself (photo 7) gets no master; the 124 KB original is served (same pixels, smaller).
- Reproducible: three runs of the new encoder gave byte-identical output on 8/8; the same bytes (1,533,111 B for photo 1, 809,538 B for photo 4) came out of the live Docker stack through the upload pipeline and the browser download.
- Visual (100% crops, reference | old | new, 4 tiles per photo: most detail, smoothest gradient, darkest area, hardest edge; 32 tiles reviewed by eye): no difference visible between the three columns in skin, hair, foliage, gradients, shadows, thin wires, jewellery edges; no ringing, blocking, banding or colour shift seen; the stripes in photo 3's reflection are in the source and identical in all three. This is my own viewing of the crops, not a blind panel; the SS2 and shift numbers are the objective check. The crop strips stay out of the repo (they show people).

### 7.2 What the proof forced (fixed in 6-D)

1. Job reuse ignored the settings: an identical request (same gallery/size/email) reused a READY ZIP for 7 days, so after the watermark was switched on, a Web Size px was changed, or a Pro plan lapsed, a returning visitor got the old ZIP (found by the new tests). `DownloadJob.variant` (migration `clients.0012`) now records Web px + watermark state, or the High Resolution mode; only a job with the same variant is reused.
2. A ZIP could ship short: a photo that failed while being written was skipped quietly. Now the job fails (`prepare_failed`), every stored part and temp file is removed, and nothing is served.
3. `render_web_jpeg` falls back to a stored tier only when no source can be DECODED; a failure after a good decode (resize, watermark, JPEG save) raises, so a ZIP fails cleanly and a single download answers 503 `web_size_preparing`, never a differently sized file.
4. A failed master re-encode used to fall back to the original even above 3600 px (a Free client would get the full-size file). The original now stands in only when it is itself <= 3600 px; otherwise 503 `download_master_unavailable` (single, preflight too) or a failed job (ZIP).
5. `Retry-After` was invisible to the browser (cross-origin): `CORS_EXPOSE_HEADERS = ['Retry-After']`; its value is `WEB_SIZE_RETRY_AFTER_SECONDS` (3). The single-photo preflight timeout (15 s) was shorter than the server's 25 s worker wait, so a cold size read as a network error; that call now waits 40 s.

### 7.3 Browser run (real Chrome, Docker stack, real worker; the 2 QA users were deleted by exact id afterwards)

Free gallery, 4 photos (3648x2736, 4248x2898 ICC, EXIF-rotated 3264x2448, the 720x1600 sky): single download and ZIP at High Resolution and at Web Size 2048 / 1024 / 640, files opened and measured. High Resolution: 3600x2700 / 3600x2456 / 2448x3264 / 720x1600 (original served, no master). Web Size long edge exactly 2048 / 1024 / 640 (a 720x1600 photo stays 720x1600 at 2048). Every single file equals its ZIP entry byte for byte; ZIPs pass `testzip`. Pro gallery: High Resolution single and ZIP = the uploads byte for byte (SHA-256, 4/4, up to 4248x2898); watermark ON: Web Size single and ZIP carry "KYAPTURE QA" and differ from the clean files, Original unchanged; OFF again: the ZIP is the clean one again (same hashes as the Free run). Free account: saving Original in settings -> 403 `original_download_requires_upgrade`; `resolution=original` on the public API -> 400; `resolution=download` -> the 3600 px master (1,533,111 B).

503 UI (websize worker stopped, cold Web Size 2048, single photo, desktop): "Preparing your download…" at 1.2 s, worker started at about 41 s, download completed at 42.7 s with no click. Worker stopped throughout (390 px): "Preparing your download…" for 109 s (4 tries, `PREPARING_MAX_ATTEMPTS`), then "Your download is taking longer than usual to prepare. Please try again." and a "Try again" button; worker started, "Try again" delivered the file in 3.8 s. A ZIP Web Size with the websize worker stopped still finished (a ZIP job encodes inside its own Celery task). The set-download page handles the same 503 through the same helper; the real ZIP prepare never answers it, so that path was proven with an intercepted response (2x 503 then success; always 503 -> 4 tries, then the same message and "Start Download" back). The favorites list has no download control (nothing to cover); a photo opened from the grid or lightbox uses the single-photo flow.

## Appendix A: per-image, jpegli q90 vs current (KB / SS2)

| Image | Source px -> master | Original KB | Current | jpegli q90 | Pillow q85 |
|---|---|---|---|---|---|
| portrait/skin landscape | 3648x2736 -> 3600 | 2648 | 1509 / 82.71 | 1497 / 84.57 | 1552 / 83.28 |
| portrait/skin portrait | 2736x3648 -> 3600 | 2570 | 1186 / 82.82 | 1074 / 84.07 | 1225 / 83.41 |
| low-light | 2448x3264 | 2038 | 787 / 83.29 | 667 / 84.12 | 814 / 84.12 |
| low-light 2 | 2448x3264 | 2009 | 744 / 82.50 | 606 / 83.20 | 772 / 83.40 |
| foliage | 2448x3264 | 2084 | 821 / 83.43 | 792 / 84.83 | 848 / 84.06 |
| >3600 landscape (scan) | 4248x2898 -> 3600 | 2197 | 871 / 81.95 | 790 / 83.38 | 904 / 82.60 |
| >3600 tall portrait | 2988x5312 -> 3600 | 2474 | 840 / 83.72 | 770 / 84.69 | 868 / 84.29 |
| outdoor kids/skin | 3264x2448 | 3225 | 1346 / 81.30 | 1406 / 83.39 | 1398 / 81.84 |
| small 1600 px | 1600x1200 | 478 | 388 / 87.00 | 411 / 87.43 | 393 / 87.89 |
| sky gradient (small) | 720x1600 | 121 | none (original served) | 152 / 89.18 (> original) | 148 / 88.53 (> original) |

## Limits of this calibration

- 10 images, all phone or scanned-print JPEGs up to 5312 px; no 24 MP+ DSLR file, one wide-gamut (ICC) source. The 103-image run was out of scope.
- SSIMULACRA2 reference is the already-lossy upload (what the master is made from), not a camera RAW.
- CLI timings were taken on Windows with process start included; the Linux numbers are from the 12-core Docker host, not production hardware.
