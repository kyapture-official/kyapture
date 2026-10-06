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
