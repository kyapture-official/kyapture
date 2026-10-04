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

Images: **22**; total original bytes: **49,365,970**.
Reference long edge: at most **3600px**; no upscaling. References use EXIF orientation, best-effort ICC-to-sRGB conversion, RGB pixels, and no metadata.

| Dataset statistic | Value |
|---|---:|
| Original bytes min / median / max | 1143189 / 2133354.00 / 3721478 |
| Reference dimensions | 1536x2048, 1723x2558, 1920x2560, 2025x3600, 2448x3264, 2700x3600, 3264x1836, 3264x2448, 3600x2102, 3600x2700 |

## C–E. Method results

The comparison table below uses threshold **88** when available. Current is the production helper called on the same normalized reference; MozJPEG/jpegli rows are the lowest tested encoder quality passing the threshold, with a neighborhood verification.

| Encoder | Images | Median size | Median SSIMULACRA2 | Worst SSIMULACRA2 | P95 encode ms | Median reduction |
|---|---:|---:|---:|---:|---:|---:|
| current | 22 | 818500 | 82.55 | 79.46 | 14423.25 | 61.87% |
| jpegli | 22 | 1313646 | 88.42 | 88.07 | 853.61 | 38.87% |
| jpegli | 22 | 1313646 | 88.42 | 88.07 | 853.61 | 38.87% |
| mozjpeg | 22 | 1278324 | 88.56 | 88.02 | 5651.43 | 41.35% |
| mozjpeg | 22 | 1278324 | 88.56 | 88.02 | 5651.43 | 41.35% |

## F. SSIMULACRA2 threshold comparison

| Method | Threshold | Total input bytes | Total output bytes | Bytes saved | Median reduction | p5 SSIM2 | Worst SSIM2 | Total encode seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current |  | 49,365,970 | 19,110,714 | 30,255,256 | 61.87% | 79.96 | 79.46 | 207.68 |
| jpegli | 88.0 | 49,365,970 | 31,539,787 | 17,826,183 | 38.87% | 88.08 | 88.07 | 11.03 |
| jpegli | 80.0 | 49,365,970 | 14,336,474 | 35,029,496 | 74.02% | 80.10 | 80.04 | 8.10 |
| jpegli | 85.0 | 49,365,970 | 22,530,566 | 26,835,404 | 56.15% | 85.08 | 85.06 | 9.10 |
| jpegli | 88.0 | 49,365,970 | 31,539,787 | 17,826,183 | 38.87% | 88.08 | 88.07 | 11.03 |
| jpegli | 90.0 | 49,365,970 | 46,245,771 | 3,120,199 | 18.83% | 90.05 | 90.01 | 13.29 |
| mozjpeg | 88.0 | 49,365,970 | 31,577,684 | 17,788,286 | 41.35% | 88.02 | 88.02 | 73.60 |
| mozjpeg | 80.0 | 49,365,970 | 14,414,750 | 34,951,220 | 72.30% | 80.05 | 80.00 | 53.40 |
| mozjpeg | 85.0 | 49,365,970 | 21,725,538 | 27,640,432 | 58.28% | 85.01 | 85.00 | 67.29 |
| mozjpeg | 88.0 | 49,365,970 | 31,577,684 | 17,788,286 | 41.35% | 88.02 | 88.02 | 73.60 |
| mozjpeg | 90.0 | 49,365,970 | 43,566,995 | 5,798,975 | 15.36% | 90.02 | 90.02 | 110.67 |

## G. Worst-case and pairwise analysis

### current: 10 lowest available SSIMULACRA2 scores

| File | SSIM2 | Output bytes | Reduction | Status |
|---|---:|---:|---:|---|
| 20240514_100852.jpg | 79.46 | 1061296 | 62.04% | selected |
| 20240514_100830.jpg | 79.95 | 1107452 | 61.09% | selected |
| 20141003_202621.jpg | 80.20 | 801574 | 62.41% | selected |
| 20140927_093336.jpg | 81.33 | 1759103 | 52.30% | selected |
| 20241006_131126.jpg | 81.39 | 784854 | 62.86% | selected |
| 20140927_093337.jpg | 81.40 | 1772991 | 52.36% | selected |
| 20240308_155412.jpg | 81.50 | 712064 | 60.46% | selected |
| Copy (2) of Picture 330.jpg | 82.06 | 1189495 | 55.92% | selected |
| 2013-10-14 10.29.22.jpg | 82.22 | 405558 | 67.82% | selected |
| 20241006_142857.jpg | 82.43 | 857416 | 62.50% | selected |

### jpegli: 10 lowest available SSIMULACRA2 scores

| File | SSIM2 | Output bytes | Reduction | Status |
|---|---:|---:|---:|---|
| 2013-10-14 10.33.46.jpg | 88.07 | 515939 | 59.24% | selected |
| 20240308_155412.jpg | 88.08 | 1235754 | 31.38% | selected |
| DSC04787.JPG | 88.13 | 1234754 | 30.67% | selected |
| Copy (2) of Picture 330.jpg | 88.17 | 2402579 | 10.96% | selected |
| 20241006_131126.jpg | 88.20 | 1220472 | 42.25% | selected |
| 20241006_142857.jpg | 88.21 | 1397407 | 38.88% | selected |
| 20150508_130002-1.jpg | 88.23 | 1047507 | 63.05% | selected |
| 20150508_130700.jpg | 88.23 | 1322074 | 47.83% | selected |
| 20230605_154755.jpg | 88.26 | 1182420 | 42.54% | selected |
| 20241004_055321.jpg | 88.29 | 1018351 | 47.26% | selected |

### mozjpeg: 10 lowest available SSIMULACRA2 scores

| File | SSIM2 | Output bytes | Reduction | Status |
|---|---:|---:|---:|---|
| 20241004_055321.jpg | 88.02 | 998451 | 48.29% | selected |
| 20150508_130002-1.jpg | 88.02 | 971899 | 65.71% | selected |
| 2013-10-14 10.29.22.jpg | 88.02 | 573633 | 54.48% | selected |
| 20240531_091725.jpg | 88.07 | 1253308 | 41.28% | selected |
| 20230605_154755.jpg | 88.11 | 1026454 | 50.12% | selected |
| 20241006_131126.jpg | 88.18 | 1238194 | 41.41% | selected |
| 20141003_202621.jpg | 88.26 | 1356416 | 36.38% | selected |
| Copy of Picture 354.jpg | 88.33 | 1698764 | 35.46% | selected |
| DSC04787.JPG | 88.34 | 1255189 | 29.53% | selected |
| 2013-10-14 10.33.46.jpg | 88.43 | 577692 | 54.36% | selected |

### Explicit pairwise categories

**Images where Current is smaller than MozJPEG**

| File | Current bytes | MozJPEG bytes | jpegli bytes | Bytes advantage |
|---|---:|---:|---:|---:|
| 20240511_184736.jpg | 273251 | 276624 | 383077 | -3373 |
| 2013-10-14 10.33.46.jpg | 415051 | 577692 | 515939 | -162641 |
| 2013-10-14 10.29.22.jpg | 405558 | 573633 | 557669 | -168075 |
| 2013-10-14 10.34.12.jpg | 383090 | 600086 | 524182 | -216996 |
| 20241004_055321.jpg | 767096 | 998451 | 1018351 | -231355 |
| 20230605_154755.jpg | 762121 | 1026454 | 1182420 | -264333 |
| 20150506_192925.jpg | 835425 | 1152546 | 1363972 | -317121 |
| 20150508_130002-1.jpg | 598290 | 971899 | 1047507 | -373609 |
| 20240531_091725.jpg | 841724 | 1253308 | 1305217 | -411584 |
| 20150508_130700.jpg | 861009 | 1301460 | 1322074 | -440451 |

**Images where jpegli is smaller than Current**

| File | Current bytes | MozJPEG bytes | jpegli bytes | Bytes advantage |
|---|---:|---:|---:|---:|
| none | n/a | n/a | n/a | n/a |

**Images where MozJPEG is smaller than jpegli**

| File | Current bytes | MozJPEG bytes | jpegli bytes | Bytes advantage |
|---|---:|---:|---:|---:|
| 20150506_192925.jpg | 835425 | 1152546 | 1363972 | 211426 |
| 20230605_154755.jpg | 762121 | 1026454 | 1182420 | 155966 |
| 20141003_202621.jpg | 801574 | 1356416 | 1495500 | 139084 |
| Copy of Picture 354.jpg | 1215049 | 1698764 | 1832602 | 133838 |
| 20240514_100852.jpg | 1061296 | 2253944 | 2384671 | 130727 |
| 20240511_184736.jpg | 273251 | 276624 | 383077 | 106453 |
| 20150508_130002-1.jpg | 598290 | 971899 | 1047507 | 75608 |
| 20240531_091725.jpg | 841724 | 1253308 | 1305217 | 51909 |
| 20240904_163240.jpg | 910750 | 1379065 | 1427646 | 48581 |
| 20150508_130700.jpg | 861009 | 1301460 | 1322074 | 20614 |

**Potential visual-QA queue:** 2013-10-14 10.29.22.jpg, 2013-10-14 10.29.22.jpg, 2013-10-14 10.29.22.jpg, 2013-10-14 10.33.46.jpg, 2013-10-14 10.33.46.jpg, 2013-10-14 10.33.46.jpg, 2013-10-14 10.34.12.jpg, 2013-10-14 10.34.12.jpg, 2013-10-14 10.34.12.jpg, 20140927_093336.jpg, 20140927_093336.jpg, 20140927_093336.jpg, 20140927_093337.jpg, 20140927_093337.jpg, 20140927_093337.jpg, 20141003_202621.jpg, 20141003_202621.jpg, 20141003_202621.jpg, 20150506_192925.jpg, 20150506_192925.jpg. A near-threshold score is not proof of an artifact; inspect the contact sheet/crops.

Largest regressions and wins, pairwise flags, and all per-image values are exported in `worst-cases.csv` and `pairwise.csv`. A `near_threshold_review` flag means a score passed but was close to the requested threshold; it is a human-visual-QA queue, not proof of an artifact.

## H–I. Encode time and storage/bandwidth

See the threshold table above for total input/output bytes, savings, median reduction, total CPU time, and p95 encode time. `candidate_bytes_ge_original=true` is the explicit original-size safety signal.

## J. Pixieset reference comparison

Pixieset values below are supplied observations only; this benchmark does not reproduce Pixieset's private algorithm.

| File | Original | Pixieset | Current | Current Δ | MozJPEG | MozJPEG Δ | jpegli | jpegli Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2013-10-14 10.29.22.jpg | 1260268 | 471462 | 405558 | -65904 | 573633 | 102171 | 557669 | 86207 |
| 2013-10-14 10.33.46.jpg | 1265684 | 525347 | 415051 | -110296 | 577692 | 52345 | 515939 | -9408 |
| 2013-10-14 10.34.12.jpg | 1199359 | 439841 | 383090 | -56751 | 600086 | 160245 | 524182 | 84341 |
| 2013-10-14 10.35.36.jpg | 1289934 | 523472 | n/a | n/a | n/a | n/a | n/a | n/a |
| 2013-11-09 09.10.00.jpg | 1947892 | 715567 | n/a | n/a | n/a | n/a | n/a | n/a |
| 2013-11-25 19.34.13.jpg | 874964 | 371280 | n/a | n/a | n/a | n/a | n/a | n/a |
| 2013-11-25 19.34.45.jpg | 865645 | 364095 | n/a | n/a | n/a | n/a | n/a | n/a |
| 2014-07-05 09.50.04.jpg | 2254493 | 963329 | n/a | n/a | n/a | n/a | n/a | n/a |
| 2014-07-05 09.50.56.jpg | 1891920 | 731168 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20140927_093336.jpg | 3687720 | 1979299 | 1759103 | -220196 | 2973645 | 994346 | 2712181 | 732882 |
| 20140927_093337.jpg | 3721478 | 1999765 | 1772991 | -226774 | 2995599 | 995834 | 2739368 | 739603 |
| 20140927_093407-1.jpg | 2247438 | 693823 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20140927_093409-1.jpg | 2111943 | 638367 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20141003_202621.jpg | 2132198 | 860709 | 801574 | -59135 | 1356416 | 495707 | 1495500 | 634791 |
| 20141004_073108.jpg | 2232149 | 1061048 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20141004_073113.jpg | 2321801 | 1107513 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20141006_133007.jpg | 2946949 | 1489184 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20141006_133009.jpg | 3200073 | 1650505 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20141006_133121.jpg | 2566581 | 1273313 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20141006_133213.jpg | 2625730 | 1318119 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20141006_133312.jpg | 2696776 | 1356942 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20150506_162440.jpg | 3303188 | 1607751 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20150506_192925.jpg | 2132094 | 890021 | 835425 | -54596 | 1152546 | 262525 | 1363972 | 473951 |
| 20150508_130002-1.jpg | 2834749 | 636657 | 598290 | -38367 | 971899 | 335242 | 1047507 | 410850 |
| 20150508_130700.jpg | 2534246 | 940079 | 861009 | -79070 | 1301460 | 361381 | 1322074 | 381995 |
| 20150508_130916.jpg | 2364441 | 826314 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20150508_133146.jpg | 3276966 | 1121932 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20150508_172715.jpg | 2467610 | 1158681 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20150608_165558-1.jpg | 2537889 | 572295 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20150608_165623.jpg | 2595204 | 1180460 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20160826_191705.jpg | 2133079 | 883583 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20160826_193230.jpg | 1514666 | 594738 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20230605_154750.jpg | 2078361 | 744677 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20230605_154755.jpg | 2057898 | 723640 | 762121 | 38481 | 1026454 | 302814 | 1182420 | 458780 |
| 20230605_154800.jpg | 1892908 | 664489 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20230805_091818.jpg | 2286245 | 895871 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20230805_091823.jpg | 2546701 | 1035126 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20230805_091849.jpg | 2314095 | 941262 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20230805_101520.jpg | 2667299 | 1077916 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20231206_085233.jpg | 2247957 | 824406 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240101_105327.jpg | 2099613 | 950485 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240308_155412.jpg | 1800947 | 762591 | 712064 | -50527 | 1419583 | 656992 | 1235754 | 473163 |
| 20240401_121036.jpg | 2022178 | 727936 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240408_100528.jpg | 352650 | 164925 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240408_100541.jpg | 303846 | 137745 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240511_184736.jpg | 1143189 | 304494 | 273251 | -31243 | 276624 | -27870 | 383077 | 78583 |
| 20240511_184817.jpg | 3078456 | 1225450 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240511_184828.jpg | 3350700 | 1367177 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240511_184852.jpg | 1532987 | 584120 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240514_100106.jpg | 1822998 | 647993 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240514_100316.jpg | 1967533 | 762499 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240514_100830.jpg | 2846153 | 1213182 | 1107452 | -105730 | 2307070 | 1093888 | 2236445 | 1023263 |
| 20240514_100852.jpg | 2795880 | 1165498 | 1061296 | -104202 | 2253944 | 1088446 | 2384671 | 1219173 |
| 20240517_124328.jpg | 2665157 | 1072785 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240531_091725.jpg | 2134510 | 889669 | 841724 | -47945 | 1253308 | 363639 | 1305217 | 415548 |
| 20240816_144737.jpg | 2117912 | 740574 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240816_144742.jpg | 2335961 | 885343 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240904_094648.jpg | 2060572 | 697531 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240904_094654.jpg | 2089072 | 709908 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240904_094703.jpg | 2180901 | 780430 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240904_094708.jpg | 2042740 | 683023 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20240904_163240.jpg | 2377522 | 948137 | 910750 | -37387 | 1379065 | 430928 | 1427646 | 479509 |
| 20241004_055321.jpg | 1930930 | 810823 | 767096 | -43727 | 998451 | 187628 | 1018351 | 207528 |
| 20241004_055322.jpg | 1955859 | 787475 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20241004_055332.jpg | 1938778 | 787068 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20241004_055345.jpg | 1937001 | 803803 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20241004_073022.jpg | 3200060 | 1295255 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20241004_073025.jpg | 1457716 | 441784 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20241006_131126.jpg | 2113372 | 784308 | 784854 | 546 | 1238194 | 453886 | 1220472 | 436164 |
| 20241006_134227.jpg | 2147275 | 824330 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20241006_134259.jpg | 2087476 | 777107 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20241006_142857.jpg | 2286364 | 924342 | 857416 | -66926 | 1493930 | 569588 | 1397407 | 473065 |
| 20241006_142910.jpg | 2225775 | 960874 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20241006_142917.jpg | 1887525 | 807135 | n/a | n/a | n/a | n/a | n/a | n/a |
| 20241012_200117.jpg | 2327117 | 831302 | n/a | n/a | n/a | n/a | n/a | n/a |
| Baba chori kali mandir ma.jpg | 235562 | 298857 | n/a | n/a | n/a | n/a | n/a | n/a |
| Childrens.jpg | 490358 | 495951 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy (2) of Picture 325.jpg | 2741121 | 1360203 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy (2) of Picture 327.jpg | 2739114 | 1940901 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy (2) of Picture 330.jpg | 2698409 | 1315217 | 1189495 | -125722 | 2474132 | 1158915 | 2402579 | 1087362 |
| Copy (2) of Picture 351.jpg | 2641903 | 1361559 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy (2) of Picture 352.jpg | 2684226 | 1421230 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy (2) of Picture 353.jpg | 2691689 | 1319803 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy of Picture 275.jpg | 2661181 | 1270633 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy of Picture 276.jpg | 2651998 | 1435265 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy of Picture 282.jpg | 2621323 | 1588596 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy of Picture 354.jpg | 2631911 | 1368769 | 1215049 | -153720 | 1698764 | 329995 | 1832602 | 463833 |
| Copy of Picture 359.jpg | 2644497 | 952378 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy of Picture 447.jpg | 2519846 | 1173787 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy of Picture 448.jpg | 2577654 | 1166442 | n/a | n/a | n/a | n/a | n/a | n/a |
| Copy of Picture 450.jpg | 2711894 | 1754931 | n/a | n/a | n/a | n/a | n/a | n/a |
| DSC04783.JPG | 1789127 | 1317203 | n/a | n/a | n/a | n/a | n/a | n/a |
| DSC04784.JPG | 2250526 | 1022027 | n/a | n/a | n/a | n/a | n/a | n/a |
| DSC04786.JPG | 1320079 | 600877 | n/a | n/a | n/a | n/a | n/a | n/a |
| DSC04787.JPG | 1781089 | 858208 | 796055 | -62153 | 1255189 | 396981 | 1234754 | 376546 |
| DSC04789.JPG | 1976291 | 894562 | n/a | n/a | n/a | n/a | n/a | n/a |
| DSC04790.JPG | 1989292 | 990212 | n/a | n/a | n/a | n/a | n/a | n/a |
| DSC04791.JPG | 1917902 | 925075 | n/a | n/a | n/a | n/a | n/a | n/a |
| Dad....jpg | 71940 | 87686 | n/a | n/a | n/a | n/a | n/a | n/a |
| FB_IMG_1677245610496.jpg | 40530 | 59579 | n/a | n/a | n/a | n/a | n/a | n/a |
| FB_IMG_1688025554368.jpg | 124477 | 178101 | n/a | n/a | n/a | n/a | n/a | n/a |
| FB_IMG_1688025634095.jpg | 69611 | 100388 | n/a | n/a | n/a | n/a | n/a | n/a |
| Family.jpg | 540665 | 549930 | n/a | n/a | n/a | n/a | n/a | n/a |

## K. Recommendation

This run has complete SSIMULACRA2 coverage. Use the threshold table and worst-case CSV together with deployment/compatibility review; the lowest median file is not sufficient by itself.
Measured size leader at threshold 88: **mozjpeg**. This is a benchmark result only; it does not authorize a production change.
