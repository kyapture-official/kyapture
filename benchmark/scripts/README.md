# KYAPTURE JPEG download benchmark

This directory is benchmark-only. The harness does not modify production image code, application dependencies, the database, existing media, or existing Download Masters.

Run it from the repository root with the project virtualenv:

```powershell
.\.venv\Scripts\python.exe benchmark\scripts\jpeg_download_benchmark.py `
  --input-dir C:\path\to\real-photographer-jpegs `
  --output-dir benchmark-artifacts\jpeg-download `
  --contact-sheet
```

Optional tool paths can be supplied explicitly:

```powershell
.\.venv\Scripts\python.exe benchmark\scripts\jpeg_download_benchmark.py `
  --input-dir C:\path\to\real-photographer-jpegs `
  --mozjpeg-bin C:\tools\mozjpeg\cjpeg.exe `
  --jpegli-bin C:\tools\jpegli\cjpegli.exe `
  --ssimulacra2-bin C:\tools\ssimulacra2.exe `
  --butteraugli-bin C:\tools\butteraugli.exe
```

Pixieset observations are optional and are never treated as a reproduced encoder. For a downloaded Pixieset folder, run strict preflight first:

```powershell
.\.venv\Scripts\python.exe benchmark\scripts\jpeg_download_benchmark.py `
  --input-dir C:\path\to\originals `
  --pixieset-dir "C:\path\to\pixieset download" `
  --output-dir benchmark-artifacts\pixieset-preflight `
  --preflight-only
```

The preflight pairs exact filenames first, then uses only a deterministic whitespace-normalized filename key when it is unique. It never pairs by arbitrary ordering. Any duplicate, invalid JPEG, unmatched filename, or count mismatch stops the benchmark after writing `preflight.md`, `preflight.csv`, and `preflight.json`.

Alternatively, manually measured Pixieset observations may be supplied and are never treated as a reproduced encoder:

```csv
filename,original_bytes,pixieset_bytes
IMG_1234.jpg,3510000,1730000
IMG_5678.jpg,6330000,1370000
```

Pass that file with `--pixieset-reference path\to\pixieset.csv` (JSON is also accepted). The filename must match a source filename for the comparison table to align.

Outputs:

- `report.md`: tool audit, dataset summary, threshold tables, worst cases, timing, storage totals, Pixieset observations, and a data-qualified recommendation.
- `preflight.md`, `preflight.csv`, `preflight.json`: strict original/Pixieset filename pairing, JPEG validation, dimensions, bytes, missing/duplicate files, and the expected no-upscale/3600px dimension-contract check.
- `results.csv`: Current plus selected MozJPEG/jpegli rows for each SSIMULACRA2 threshold.
- `candidate-results.csv`: every tested external-encoder quality/subsampling candidate.
- `summary.csv`: aggregate statistics including total bytes, p5/p95, worst score, and encode time.
- `pairwise.csv`: filename-aligned Current/MozJPEG/jpegli size and score comparisons at `--worst-threshold`, including the requested winner flags.
- `worst-cases.csv`: lowest scores and largest size regressions at `--worst-threshold`.
- `references/`: normalized, metadata-free PNG and PPM references.
- `outputs/`: benchmark-only selected JPEGs and optional contact sheet inputs.
- `visual-crops/`: native-pixel side-by-side high-variance crops emitted with `--contact-sheet`.

The reference is produced once per source by applying EXIF orientation, best-effort ICC-to-sRGB conversion, RGB conversion, and a maximum 3600px long edge with no upscaling. Every encoder starts from that reference. JPEG metadata is intentionally excluded consistently from benchmark candidates; no product metadata decision is made.

SSIMULACRA2 is required for a trustworthy perceptual comparison. If it is missing, the harness still records Current and any available encoder smoke tests/PSNR, but the report explicitly refuses to make a production recommendation. PSNR is never used as the primary decision criterion.

MozJPEG uses `-sample 2x2`, optimized, progressive JPEG first. jpegli uses `--chroma_subsampling=420`, progressive, optimized output first. For each requested threshold, quality search uses a binary-search-style probe and verifies a ±2 quality neighborhood. If 4:2:0 cannot pass, the harness searches 4:4:4. Raw quality numbers are only recorded within each encoder; they are not compared across encoders.

The intended workflow is: supply 50–100 real JPEGs, run the harness, inspect `report.md`, inspect the worst-case CSV/contact sheet, and stop at the benchmark result. Do not use this script as a production processing path.
