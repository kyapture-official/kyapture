# KYAPTURE quick-screen execution report

Elapsed seconds: **3508.4**
Images completed: **22/24**
Projected 103-image time at this observed throughput: **273.8 minutes**

The screen uses transparent image-stat strata as a deterministic proxy for the requested scene categories; it does not assert semantic labels. SSIMULACRA2 remains primary.

| Encoder | Threshold | Images | Median bytes | Median SSIM2 | P5 SSIM2 | Worst SSIM2 | P95 encode ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 88 | 22 | 818499.50 | 82.55 | 79.96 | 79.46 | 14423.25 |
| current | 80 | 22 | 818499.50 | 82.55 | 79.96 | 79.46 | 14423.25 |
| current | 85 | 22 | 818499.50 | 82.55 | 79.96 | 79.46 | 14423.25 |
| current | 88 | 22 | 818499.50 | 82.55 | 79.96 | 79.46 | 14423.25 |
| current | 90 | 22 | 818499.50 | 82.55 | 79.96 | 79.46 | 14423.25 |
| mozjpeg | 88 | 22 | 1278324.50 | 88.56 | 88.02 | 88.02 | 5651.43 |
| mozjpeg | 80 | 22 | 579717.00 | 80.42 | 80.05 | 80.00 | 3990.46 |
| mozjpeg | 85 | 22 | 897177.50 | 85.70 | 85.01 | 85.00 | 5352.26 |
| mozjpeg | 88 | 22 | 1278324.50 | 88.56 | 88.02 | 88.02 | 5651.43 |
| mozjpeg | 90 | 22 | 1847077.00 | 90.37 | 90.02 | 90.02 | 7801.81 |
| jpegli | 88 | 22 | 1313645.50 | 88.42 | 88.08 | 88.07 | 853.61 |
| jpegli | 80 | 22 | 563143.50 | 80.46 | 80.10 | 80.04 | 567.08 |
| jpegli | 85 | 22 | 916564.00 | 85.63 | 85.08 | 85.06 | 586.59 |
| jpegli | 88 | 22 | 1313645.50 | 88.42 | 88.08 | 88.07 | 853.61 |
| jpegli | 90 | 22 | 1942824.50 | 90.25 | 90.05 | 90.01 | 923.15 |

## Elimination gate

No encoder is safely eliminated by this screen unless it is consistently no smaller, no better in worst-case SSIMULACRA2, and no faster than its alternative. The conservative result is: **retain Current, MozJPEG, and jpegli for Phase B** unless a clearly dominant and consistent result is measured.

## Incomplete images

- Dad....jpg: missing SSIMULACRA2 for current 
- FB_IMG_1688025634095.jpg: missing SSIMULACRA2 for current 

## Selected strata

| File | Strata | Dimensions | Bytes |
|---|---|---:|---:|
| 20150508_130002-1.jpg | portrait_skin | 1723x2558 | 2834749 |
| 20240511_184736.jpg | low_light_high_iso_proxy | 3264x2448 | 1143189 |
| 20140927_093337.jpg | foliage_proxy | 3264x1836 | 3721478 |
| 20240514_100852.jpg | sky_gradient_proxy | 3264x2448 | 2795880 |
| 20140927_093336.jpg | fine_texture_proxy | 3264x1836 | 3687720 |
| 20240531_091725.jpg | architecture_proxy | 3264x2448 | 2134510 |
| 20241004_055321.jpg | bright_highlights | 3264x2448 | 1930930 |
| 20241006_131126.jpg | dark_shadows | 3264x2448 | 2113372 |
| 2013-10-14 10.29.22.jpg | landscape_orientation | 2048x1536 | 1260268 |
| 2013-10-14 10.33.46.jpg | portrait_orientation | 1536x2048 | 1265684 |
| Dad....jpg | small_original | 614x641 | 71940 |
| 20150508_130700.jpg | large_original | 2988x5312 | 2534246 |
| 2013-10-14 10.34.12.jpg | deterministic_fill | 2048x1536 | 1199359 |
| 20141003_202621.jpg | deterministic_fill | 3264x1836 | 2132198 |
| 20150506_192925.jpg | deterministic_fill | 2448x3264 | 2132094 |
| 20230605_154755.jpg | deterministic_fill | 3264x2448 | 2057898 |
| 20240308_155412.jpg | deterministic_fill | 2560x1920 | 1800947 |
| 20240514_100830.jpg | deterministic_fill | 3264x2448 | 2846153 |
| 20240904_163240.jpg | deterministic_fill | 3264x2448 | 2377522 |
| 20241006_142857.jpg | deterministic_fill | 3264x2448 | 2286364 |
| Copy (2) of Picture 330.jpg | deterministic_fill | 3648x2736 | 2698409 |
| Copy of Picture 354.jpg | deterministic_fill | 2736x3648 | 2631911 |
| DSC04787.JPG | deterministic_fill | 4110x2400 | 1781089 |
| FB_IMG_1688025634095.jpg | deterministic_fill | 640x1370 | 69611 |
