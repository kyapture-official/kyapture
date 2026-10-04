# KYAPTURE quick-screen execution report

Elapsed seconds: **47.1**
Images completed: **1/1**
Projected 103-image time at this observed throughput: **80.9 minutes**

The screen uses transparent image-stat strata as a deterministic proxy for the requested scene categories; it does not assert semantic labels. SSIMULACRA2 remains primary.

| Encoder | Threshold | Images | Median bytes | Median SSIM2 | P5 SSIM2 | Worst SSIM2 | P95 encode ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 88 | 1 | 598290.00 | 82.94 | 82.94 | 82.94 | 6403.63 |
| current | 80 | 1 | 598290.00 | 82.94 | 82.94 | 82.94 | 6403.63 |
| current | 85 | 1 | 598290.00 | 82.94 | 82.94 | 82.94 | 6403.63 |
| current | 88 | 1 | 598290.00 | 82.94 | 82.94 | 82.94 | 6403.63 |
| current | 90 | 1 | 598290.00 | 82.94 | 82.94 | 82.94 | 6403.63 |
| mozjpeg | 88 | 1 | 971899.00 | 88.02 | 88.02 | 88.02 | 1791.20 |
| mozjpeg | 80 | 1 | 426150.00 | 80.18 | 80.18 | 80.18 | 1170.95 |
| mozjpeg | 85 | 1 | 641640.00 | 85.35 | 85.35 | 85.35 | 1879.71 |
| mozjpeg | 88 | 1 | 971899.00 | 88.02 | 88.02 | 88.02 | 1791.20 |
| mozjpeg | 90 | 1 | 1643863.00 | 90.53 | 90.53 | 90.53 | 2554.12 |
| jpegli | 88 | 1 | 1047507.00 | 88.23 | 88.23 | 88.23 | 220.32 |
| jpegli | 80 | 1 | 426606.00 | 80.67 | 80.67 | 80.67 | 178.68 |
| jpegli | 85 | 1 | 733114.00 | 85.90 | 85.90 | 85.90 | 226.25 |
| jpegli | 88 | 1 | 1047507.00 | 88.23 | 88.23 | 88.23 | 220.32 |
| jpegli | 90 | 1 | 1973107.00 | 90.84 | 90.84 | 90.84 | 249.29 |

## Elimination gate

No encoder is safely eliminated by this screen unless it is consistently no smaller, no better in worst-case SSIMULACRA2, and no faster than its alternative. The conservative result is: **retain Current, MozJPEG, and jpegli for Phase B** unless a clearly dominant and consistent result is measured.

## Selected strata

| File | Strata | Dimensions | Bytes |
|---|---|---:|---:|
| 20150508_130002-1.jpg | portrait_skin | 1723x2558 | 2834749 |
