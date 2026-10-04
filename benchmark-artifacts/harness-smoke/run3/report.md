# KYAPTURE JPEG download compression benchmark

Read-only benchmark. No production code, database rows, existing media, or download masters were modified.

## A. Tool availability

Metadata policy: all benchmark candidates are newly encoded, metadata-free JPEGs; references are metadata-free PNG/PPM. EXIF/copyright policy is not decided here.

| Tool | Status | Path/command | Version/detail |
|---|---|---|---|
| Pillow/Python image pipeline | available | `C:\Users\LENOVO\Desktop\kyapture\.venv\Scripts\python.exe` | Pillow 12.2.0 (C:\Users\LENOVO\Desktop\kyapture\.venv\Scripts\python.exe) |
| MozJPEG cjpeg | available | `C:\Users\LENOVO\Desktop\kyapture\benchmark\tools\build\mozjpeg-ninja\cjpeg.exe` | C:\Users\LENOVO\Desktop\kyapture\benchmark\tools\build\mozjpeg-ninja\cjpeg.exe: unknown option '-version' |
| jpegli cjpegli | available | `C:\Users\LENOVO\Desktop\kyapture\benchmark\tools\build\jpegli-msvc\tools\cjpegli.exe` | Unknown argument: --version |
| SSIMULACRA2 | available | `C:\Users\LENOVO\Desktop\kyapture\benchmark\tools\build\ssimulacra2\ssimulacra2.exe` | SSIMULACRA 2.1 [AVX2,SSE4,SSSE3,SSE2] |
| Butteraugli | MISSING | `butteraugli` |  |
| Docker host | available | `C:\Program Files\Docker\Docker\resources\bin\docker.EXE` | Docker version 29.8.1, build 4a63305 |

Missing tools are not emulated. In particular, PSNR is only a diagnostic; a run without SSIMULACRA2 cannot support a perceptual-quality production decision.

## B. Dataset summary

Images: **1**; total original bytes: **1,260,268**.
Reference long edge: at most **3600px**; no upscaling. References use EXIF orientation, best-effort ICC-to-sRGB conversion, RGB pixels, and no metadata.

| Dataset statistic | Value |
|---|---:|
| Original bytes min / median / max | 1260268 / 1260268 / 1260268 |
| Reference dimensions | 1536x2048 |

## C–E. Method results

The comparison table below uses threshold **88** when available. Current is the production helper called on the same normalized reference; MozJPEG/jpegli rows are the lowest tested encoder quality passing the threshold, with a neighborhood verification.

| Encoder | Images | Median size | Median SSIMULACRA2 | Worst SSIMULACRA2 | P95 encode ms | Median reduction |
|---|---:|---:|---:|---:|---:|---:|
| current | 1 | 405558 | 82.22 | 82.22 | 2001.03 | 67.82% |
| jpegli | 1 | 557669 | 88.54 | 88.54 | 184.84 | 55.75% |
| mozjpeg | 1 | 573633 | 88.02 | 88.02 | 839.74 | 54.48% |

## F. SSIMULACRA2 threshold comparison

| Method | Threshold | Total input bytes | Total output bytes | Bytes saved | Median reduction | p5 SSIM2 | Worst SSIM2 | Total encode seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current |  | 1,260,268 | 405,558 | 854,710 | 67.82% | 82.22 | 82.22 | 2.00 |
| jpegli | 80.0 | 1,260,268 | 294,948 | 965,320 | 76.60% | 80.92 | 80.92 | 0.13 |
| jpegli | 85.0 | 1,260,268 | 396,695 | 863,573 | 68.52% | 85.06 | 85.06 | 0.18 |
| jpegli | 88.0 | 1,260,268 | 557,669 | 702,599 | 55.75% | 88.54 | 88.54 | 0.18 |
| jpegli | 90.0 | 1,260,268 | 735,928 | 524,340 | 41.61% | 90.61 | 90.61 | 0.16 |
| mozjpeg | 80.0 | 1,260,268 | 321,701 | 938,567 | 74.47% | 80.82 | 80.82 | 0.57 |
| mozjpeg | 85.0 | 1,260,268 | 457,916 | 802,352 | 63.67% | 85.72 | 85.72 | 0.66 |
| mozjpeg | 88.0 | 1,260,268 | 573,633 | 686,635 | 54.48% | 88.02 | 88.02 | 0.84 |
| mozjpeg | 90.0 | 1,260,268 | 822,564 | 437,704 | 34.73% | 90.41 | 90.41 | 0.90 |

## G. Worst-case and pairwise analysis

### current: 10 lowest available SSIMULACRA2 scores

| File | SSIM2 | Output bytes | Reduction | Status |
|---|---:|---:|---:|---|
| smoke.jpg | 82.22 | 405558 | 67.82% | selected |

### jpegli: 10 lowest available SSIMULACRA2 scores

| File | SSIM2 | Output bytes | Reduction | Status |
|---|---:|---:|---:|---|
| smoke.jpg | 88.54 | 557669 | 55.75% | selected |

### mozjpeg: 10 lowest available SSIMULACRA2 scores

| File | SSIM2 | Output bytes | Reduction | Status |
|---|---:|---:|---:|---|
| smoke.jpg | 88.02 | 573633 | 54.48% | selected |

### Explicit pairwise categories

**Images where Current is smaller than MozJPEG**

| File | Current bytes | MozJPEG bytes | jpegli bytes | Bytes advantage |
|---|---:|---:|---:|---:|
| smoke.jpg | 405558 | 573633 | 557669 | -168075 |

**Images where jpegli is smaller than Current**

| File | Current bytes | MozJPEG bytes | jpegli bytes | Bytes advantage |
|---|---:|---:|---:|---:|
| none | n/a | n/a | n/a | n/a |

**Images where MozJPEG is smaller than jpegli**

| File | Current bytes | MozJPEG bytes | jpegli bytes | Bytes advantage |
|---|---:|---:|---:|---:|
| none | n/a | n/a | n/a | n/a |

**Potential visual-QA queue:** smoke.jpg, smoke.jpg, smoke.jpg. A near-threshold score is not proof of an artifact; inspect the contact sheet/crops.

Largest regressions and wins, pairwise flags, and all per-image values are exported in `worst-cases.csv` and `pairwise.csv`. A `near_threshold_review` flag means a score passed but was close to the requested threshold; it is a human-visual-QA queue, not proof of an artifact.

## H–I. Encode time and storage/bandwidth

See the threshold table above for total input/output bytes, savings, median reduction, total CPU time, and p95 encode time. `candidate_bytes_ge_original=true` is the explicit original-size safety signal.

## J. Pixieset reference comparison

No `--pixieset-reference` file was supplied.

## K. Recommendation

This run has complete SSIMULACRA2 coverage. Use the threshold table and worst-case CSV together with deployment/compatibility review; the lowest median file is not sufficient by itself.
Measured size leader at threshold 88: **jpegli**. This is a benchmark result only; it does not authorize a production change.
