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

## Early refusal of an oversized body (7-B, debt rows 4, 31, 75)

What the app does (tested in `backend/apps/photos/tests/test_security_7b.py::EarlyBodyRefusalTests`, with a request body that raises
if it is read): before authentication (the cookie-auth CSRF check reads the POST body, and DRF spools the whole multipart stream to
temp files the moment `request.data` is touched), `PhotoListUploadView.dispatch` looks only at the headers:

- `Content-Length` above `max(max_image_mb, max_video_mb)` + 1 MB of multipart framing → `413 request_too_large`. The app sends one
  file per request, so nothing honest is larger.
- An account (not staff) that has no storage left at all → `403 storage_limit_reached`, whatever the body holds.

What it cannot do: the bytes a client already sent still reach the server. Behind nginx with request buffering on (its default),
nginx receives the **whole** body before Django sees the headers, so **`client_max_body_size` is the only real early stop**. A video
whose length the browser cannot read (row 31) still uploads in full before ffprobe can refuse it on minutes; refusing that early needs
a resumable/chunked upload that probes the first chunk (not built).

### Production proxy and gunicorn values (plan; not testable in this repo)

These go into the staging/production manifests (14-A / 16-A). Defaults: `max_image_mb` 100, `max_video_mb` 2048.

```nginx
# server block that proxies the API (api.kyapture.com)
client_max_body_size    2100m;   # >= max_video_mb + 50 MB; raise together with max_video_mb in admin
client_body_timeout     600s;
proxy_request_buffering on;      # nginx absorbs slow clients; gunicorn only sees complete bodies
proxy_read_timeout      900s;    # > the gunicorn timeout below
proxy_send_timeout      900s;

# The client address DRF throttles and the PIN/password lockout count on
# (REST_FRAMEWORK NUM_PROXIES = 1 in production.py). Overwrite, never append a
# client-sent value: with exactly one trusted proxy either works, but overwriting
# keeps the header to one entry.
proxy_set_header X-Forwarded-For   $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Host              $host;

# Unlock / download / file tokens can sit in query strings (<a href>, <video src>):
# keep them out of the access log.
log_format kyapture_noargs '$remote_addr - [$time_local] "$request_method $uri" $status $body_bytes_sent $request_time';
access_log /var/log/nginx/api.access.log kyapture_noargs;
```

gunicorn (`backend/Dockerfile` CMD today: 3 workers, default `--timeout 30`): with nginx buffering the request, gunicorn reads a
2 GB body from the local socket in seconds, but the view also runs ffprobe (up to 60 s) and saves the original to storage
(S3: a multi-GB PUT). Plan: `--timeout 900 --graceful-timeout 60` on the API service (a sync worker blocked longer than that is
killed and the upload answers 502), and `FILE_UPLOAD_TEMP_DIR` on a volume with room for several of the largest file at once.
Measuring a real 2 GB upload on staging hardware stays with 15-A (rows 62, 72).

## Tests

`backend/apps/photos/tests/test_upload_limits.py`: exactly at and one byte/pixel over each limit; a 29952 x 29952 PNG header refused
with `ImageFile.load` mocked to fail (asserted not called); a video over `max_video_mb` refused before ffprobe; an admin form edit changing
the next upload; mixed batches; garbage files never a 500. `frontend/src/utils/planLimitFlow.test.js`: the browser pre-check.
