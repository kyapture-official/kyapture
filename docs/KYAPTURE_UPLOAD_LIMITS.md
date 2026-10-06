# KYAPTURE per-file upload limits (chunk UP-A)

Per-file limits that protect the server (CPU, memory, disk). They are **global safety limits, not plan values**: the plan's
storage (GB) and video minutes are separate and unchanged. Reference behaviour: Pixieset refuses a 117 MB, 29952 x 29952
image with "Size exceeds 100MB limit".

## Where they live

One row, `UploadLimits` (table `upload_limits`), edited in Django admin: **Subscriptions > Upload limits**. The row is
created with the defaults below the first time it is read. It is read **at request time** (one primary-key query per
upload request), so an admin edit applies to the next upload with no restart and no deploy. Nothing else in code carries
these numbers.

| Field | Default | Meaning |
|-------|---------|---------|
| `max_image_mb` | 100 | An image larger than this is refused before anything is read or processed |
| `max_image_pixels` | 144,000,000 | An image with more pixels (width x height) is refused from its header, before it is decoded |
| `max_video_mb` | 2048 | A video larger than this is refused before ffprobe or storage |

1 MB = 1024 x 1024 bytes everywhere (server, API, browser). A file of exactly the limit is accepted, one byte over is refused.
The limits apply to staff accounts too (a staff account only skips the plan's storage and video-minute checks).

## What the API answers

Upload (`POST /api/v1/photos/<gallery>/upload/`), checked per file before the plan check, ffprobe, storage or any decoding:

- `400 {"code": "file_too_large", "message": "Size exceeds 100 MB limit", "limit_mb", "limit_bytes", "size_bytes", "file_name", "media_type"}`
- `400 {"code": "image_too_many_pixels", "message": "Image is 29,952 x 29,952 px, above the 144,000,000 pixel limit", "limit_pixels", "width", "height", "pixels", "file_name"}`
  (width/height are left out when Pillow's own decompression-bomb guard fires first, i.e. above twice the limit.)
- Every such answer also carries `"rejected": [...]` (one entry per refused file, same fields).
- A batch with some good files and some refused ones answers `202 {"uploaded": [...], "rejected": [...]}`: the good files are stored, the others are reported.
  (`refused` / `storage` still mean the plan's storage, as before.)
- Never a 500 for these cases, including when Pillow's decompression-bomb error is raised later in the request.

Usage (`GET /api/v1/galleries/dashboard/stats/`) returns `upload_limits: {max_image_mb, max_image_pixels, max_video_mb}` for every
account (Free, paid and staff), so the browser can pre-check a file's size before sending it. The upload page lists a file over
the size limit with its reason ("Size exceeds 100 MB limit"), sends no request for it, and uploads the rest. The pixel limit is
judged by the server only: the browser never decodes a huge image.

Pillow's `Image.MAX_IMAGE_PIXELS` is set from the row (`apply_pillow_pixel_guard`) when an upload is judged and at the start of
`process_photo_asset`, `generate_web_size` and `prepare_download_job`.

## nginx / reverse proxy (staging and production)

The repo's `frontend/nginx.conf` serves the static SPA only; uploads go straight to the API host (`api.kyapture.com`, `localhost:8000`
in dev), so **the proxy that fronts Django is where the body limit must be set**. That proxy is not in this repo (dev uses
`runserver`, no body limit). On staging and production, in the `server` (or the `location` that proxies to Django) block:

```nginx
client_max_body_size 2100m;      # max_video_mb (2048) + about 50 MB for multipart overhead and form fields
client_body_timeout  600s;       # a slow 2 GB upload must not be cut mid-way
proxy_read_timeout   600s;
proxy_send_timeout   600s;
```

Rule: `client_max_body_size` >= `max_video_mb` + about 50 MB. **If the owner raises `max_video_mb` in admin, raise this value in the same change**, or nginx
answers a bare `413` (an HTML page, not the JSON above) before Django sees the file. The image limit (100 MB default) is always below it.
Also needed for a real 2 GB body (not set anywhere in the repo today, see docs/KYAPTURE_PRODUCTION_DEBT.md): a gunicorn `--timeout` longer than the
upload (the Dockerfile uses the 30 s default), and free temp disk for nginx's `client_body_temp_path`, Django's `FILE_UPLOAD_TEMP_DIR`, the stored
original and the FFmpeg output at once (several times the file's size).

## Tests

`backend/apps/photos/tests/test_upload_limits.py`: exactly at and one byte/pixel over each limit; a 29952 x 29952 PNG header refused
with `ImageFile.load` mocked to fail (asserted not called); a video over `max_video_mb` refused before ffprobe; an admin form edit changing
the next upload; mixed batches; garbage files never a 500. `frontend/src/utils/planLimitFlow.test.js`: the browser pre-check.
