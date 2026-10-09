<!--C:\Users\LENOVO\Desktop\kyapture\API_DOCS.md 
Kyapture API v1 — Core Contract Specifications

API documentation

All API endpoints are prefixed with /api/v1/, except the public total-users endpoint, which is registered at /api/total-users.

Request and response payloads are strictly formatted as JSON. For file uploads, use multipart/form-data.

🔐 1. Authentication App (apps/users)

All protected endpoints require the following header:

Authorization: Bearer <access_token>

Register

POST /api/v1/auth/register/

Creates a new photographer account.

Authentication: None (authentication_classes = [])

Request Body — JSON

{
  "email": "photographer@test.com",
  "username": "kroman",
  "display_name": "Kroman Studios",
  "password": "SecurePassword123!",
  "password2": "SecurePassword123!"
}

Success Response — 201 Created

{
  "user": {
    "id": "0190100d-9b1d-7eb4-8fd2-90113c231718",
    "email": "photographer@test.com",
    "username": "kroman",
    "display_name": "Kroman Studios",
    "bio": "",
    "avatar": null,
    "is_active_plan": false,
    "created_at": "2026-06-13T10:30:00Z"
  },
  "access": "jwt_access_token_string",
  "refresh": "jwt_refresh_token_string"
}

Error Response — 400 Bad Request

{
  "error": "Invalid field 'username': Username is already taken.",
  "details": {
    "username": [
      "This username is already taken."
    ]
  }
}

Login

POST /api/v1/auth/login/

Authenticates credentials and returns JWT session tokens.

Authentication: None (authentication_classes = [])

Request Body — JSON

{
  "email": "photographer@test.com",
  "password": "SecurePassword123!"
}

Success Response — 200 OK

{
  "user": {
    "id": "0190100d-9b1d-7eb4-8fd2-90113c231718",
    "email": "photographer@test.com",
    "username": "kroman",
    "display_name": "Kroman Studios",
    "bio": "",
    "avatar": null,
    "is_active_plan": false,
    "created_at": "2026-06-13T10:30:00Z"
  },
  "access": "jwt_access_token_string",
  "refresh": "jwt_refresh_token_string"
}

Logout

POST /api/v1/auth/logout/

Blacklists the active refresh token.

Authentication: Required (IsAuthenticated)

Request Body — JSON

{
  "refresh": "jwt_refresh_token_string"
}

Success Response — 200 OK

{
  "message": "Logged out successfully."
}

Refresh Access Token

POST /api/v1/auth/token/refresh/

Generates a new short-lived access token from an active refresh token.

Authentication: None

Request Body — JSON

{
  "refresh": "jwt_refresh_token_string"
}

Success Response — 200 OK

{
  "access": "new_jwt_access_token_string"
}

Current User

GET /api/v1/auth/me/

Returns the active photographer's profile details.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

{
  "id": "0190100d-9b1d-7eb4-8fd2-90113c231718",
  "email": "photographer@test.com",
  "username": "kroman",
  "display_name": "Kroman Studios",
  "bio": "Fine art wedding photographer.",
  "avatar": "http://localhost:8000/media/avatars/kroman_avatar.jpg",
  "is_active_plan": true,
  "created_at": "2026-06-13T10:30:00Z"
}

Update Profile

PUT /api/v1/auth/me/

Partially updates photographer profile data, such as bio or avatar.

Authentication: Required (IsAuthenticated)

Request Body — multipart/form-data

display_name: "Kroman Wedding Fine Art"
bio: "Wedding fine art based in Nepal."
avatar: [File] (Optional image up to 2MB)

Success Response — 200 OK

Returns the updated user profile object.

Change Password

PUT /api/v1/auth/change-password/

Updates the authenticated user's password safely.

Authentication: Required (IsAuthenticated)

Request Body — JSON

{
  "old_password": "SecurePassword123!",
  "new_password": "BrandNewPassword2026!",
  "new_password2": "BrandNewPassword2026!"
}

Success Response — 200 OK

{
  "message": "Password changed successfully."
}

Total Users

GET /api/total-users

Public dashboard/landing page registered user count counter.

Important: This endpoint is intentionally not under /api/v1/ and has no trailing slash.

Authentication: None (authentication_classes = [])

Success Response — 200 OK

{
  "total_count": 47,
  "latest_users": []
}

🖼 2. Galleries App (apps/galleries)

List Galleries

GET /api/v1/galleries/

Lists all active (non-soft-deleted) collections created by the photographer.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

[
  {
    "id": "0190101b-944f-7f32-84b2-c0e86b0317e2",
    "title": "Sita and Hari Wedding",
    "slug": "sita-and-hari-wedding",
    "branding_color": "#1ABC9C",
    "cover_url": "http://localhost:8000/media/photographers/.../thumbnails/cover_thumb.webp",
    "photo_count": 142,
    "is_downloadable": true,
    "is_active": true,
    "is_published": true,
    "has_password": true,
    "created_at": "2026-06-13T12:00:00Z",
    "updated_at": "2026-06-13T14:30:00Z"
  }
]

Create Gallery

POST /api/v1/galleries/

Creates a new gallery collection. Limits are enforced dynamically from the photographer's current subscription metrics.

Authentication: Required (IsAuthenticated / IsPhotographer)

Note: This endpoint does not enforce a separate IsSubscribed permission class. Standard authenticated photographer access is required, and the backend checks the current plan limits (such as gallery count) at request time before allowing creation.

Request Body — JSON

{
  "title": "Sita and Hari Wedding",
  "description": "Fine art wedding coverage.",
  "branding_color": "#1ABC9C",
  "is_password_protected": true,
  "password": "sita_hari_pass",
  "is_downloadable": true,
  "watermark_enabled": false,
  "is_published": false,
  "expires_at": null
}

Success Response — 201 Created

Returns the detailed GalleryDetail object.

Gated Error Response — 403 Forbidden

{
  "error": "Gallery limit reached for your current plan.",
  "code": "gallery_limit_reached",
  "details": {
    "current_count": 3,
    "plan_limit": 3,
    "plan_name": "Basic",
    "message": "You have used 3 of 3 galleries on the Basic plan. Upgrade your plan to create more."
  }
}

Get Gallery

GET /api/v1/galleries/{slug}/

Retrieves detailed parameters for a specific gallery.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

{
  "id": "0190101b-944f-7f32-84b2-c0e86b0317e2",
  "title": "Sita and Hari Wedding",
  "slug": "sita-and-hari-wedding",
  "description": "Fine art wedding coverage.",
  "branding_color": "#1ABC9C",
  "cover_url": "http://localhost:8000/media/photographers/.../display/cover_display.webp",
  "photo_count": 142,
  "is_downloadable": true,
  "is_active": true,
  "is_published": true,
  "has_password": true,
  "created_at": "2026-06-13T12:00:00Z",
  "updated_at": "2026-06-13T14:30:00Z"
}

Update Gallery

PUT /api/v1/galleries/{slug}/

Updates settings or cover photo UUID for a specific gallery.

Authentication: Required (IsAuthenticated)

Request Body — JSON

Supports partial updates.

{
  "title": "Sita and Hari Anniversary",
  "cover_photo": "0190104f-124b-723a-a4f2-90ab12f127a4",
  "branding_color": "#000000"
}

Success Response — 200 OK

Returns the updated detailed gallery object.

Delete Gallery

DELETE /api/v1/galleries/{slug}/

Soft-deletes a gallery by flipping is_active = False. Files are kept intact to prevent accidental loss.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

{
  "message": "Gallery deleted successfully."
}

Dashboard Statistics

GET /api/v1/galleries/dashboard/stats/

Single-pass optimized aggregate statistics of the photographer's account.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK (flat; storage fields shown, collection and video fields omitted)

{
  "plan_name": "Free",
  "photos_used": 120,
  "storage_used_bytes": 3221225472,
  "storage_used_gb": 3.0,
  "plan_storage_limit_bytes": 1073741824,
  "plan_storage_limit_gb": 1.0,
  "storage_remaining_bytes": 0,
  "storage_remaining_gb": 0.0,
  "storage_percent_used": 300.0,
  "storage_state": "over",
  "storage_warning_percent": 90
}

storage_state is decided by the backend: "ok", "warning" (used is at least storage_warning_percent of the limit; the threshold is the single constant STORAGE_WARNING_FRACTION in apps/subscriptions/entitlements.py), "full" (used equals the limit) or "over" (a plan was lowered below what the account already stores: nothing is deleted, uploads are refused, viewing, downloading and deleting keep working). The limit is the plan row's storage_gb, read on every request. Staff accounts have no limit: the limit fields are null.

📷 3. Photos/Media Assets App (apps/photos)

List Gallery Media

GET /api/v1/photos/{gallery_slug}/

Lists all photos and video assets inside an active gallery, sorted by manual order.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

[
  {
    "id": "0190104f-124b-723a-a4f2-90ab12f127a4",
    "media_type": "image",
    "title": "Procession Entrance",
    "original_name": "DSC_4031.jpg",
    "file_size": 15428640,
    "order": "1.0000000000",
    "original_url": "http://localhost:8000/media/photographers/.../photos/..._original.jpg",
    "display_url": "http://localhost:8000/media/photographers/.../photos/..._display.webp",
    "thumbnail_url": "http://localhost:8000/media/photographers/.../thumbnails/..._thumb.webp",
    "blurhash": "LKO2?U%2Tw=w]~RBVZRi};RPxuwH",
    "width": 6000,
    "height": 4000,
    "stream_url": null,
    "poster_url": null,
    "preview_url": null,
    "duration": null,
    "processing_status": "ready",
    "created_at": "2026-06-13T12:30:00Z"
  }
]

Upload Media

POST /api/v1/photos/{gallery_slug}/upload/

Processes single or bulk uploads. Storage, video, and per-gallery limits are enforced by backend subscription metrics at upload time.

Authentication: Required (IsAuthenticated / IsPhotographer)

Note: There is no strict IsSubscribed permission gate for this endpoint. Authenticated photographers are allowed through, and their current plan limits are evaluated dynamically before the upload is accepted.

Request Body — multipart/form-data

image: [File] (One or many files; JPEGs/PNGs up to 25MB)
title: "Anniversary Prep" (Optional metadata)

Success Response — 202 Accepted

Everything fit: an array of the stored asset objects. If only part of a batch fit the plan's storage, the files that fit are stored and the response is
{ "uploaded": [asset, ...], "refused": [{ "name", "size_bytes", "code": "storage_limit_reached" }], "storage": { ...the 403 body below... } }.
Files are taken in the order sent (images, then videos) while they still fit; landing exactly on the limit fits.

Gated Error Response — 403 Forbidden (nothing in the batch fits the plan's storage)

{
  "error": "Storage is full.",
  "code": "storage_limit_reached",
  "message": "You have used 0.99 GB of the 1 GB your Free plan includes. Delete files or upgrade your plan to upload more.",
  "plan_name": "Free",
  "used_gb": 0.99,
  "plan_limit_gb": 1,
  "used_bytes": 1063256064,
  "plan_limit_bytes": 1073741824,
  "refused_count": 3,
  "refused_bytes": 52428800
}

Usage is the sum of the account's original files (trashed collections included until purged); generated copies are not counted.

Get Media Asset

GET /api/v1/photos/photo/{photo_id}/

Retrieves metadata of a single asset.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

Returns a single asset JSON object.

Delete Media Asset

DELETE /api/v1/photos/photo/{photo_id}/

Purges an asset from the database and automatically triggers background signals to erase all physical variants (Original, display WebP, thumbnail WebP) from disk or AWS S3.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

{
  "message": "Media asset deleted successfully."
}

Bulk Delete Media

POST /api/v1/photos/{gallery_slug}/delete-bulk/

Deletes multiple media assets (both photos and videos) inside a target gallery in a single request.

Authentication: Required (IsAuthenticated)

Request Body — JSON

{
  "photo_ids": [
    "0190104f-124b-723a-a4f2-90ab12f127a4",
    "0190104f-944f-7f32-84b2-c0e86b0317e2"
  ]
}

Success Response — 200 OK

Returns the count of successfully deleted records. S3 files are automatically purged via background signals.

{
  "deleted_count": 2
}

Reorder Media

PATCH /api/v1/photos/{gallery_slug}/reorder/

Updates the manual drag-and-drop sequencing of all assets inside a gallery. Sets clean, sequential decimal order coordinates.

Authentication: Required (IsAuthenticated)

Request Body — JSON

{
  "ordered_ids": [
    "0190104f-944f-7f32-84b2-c0e86b0317e2",
    "0190104f-124b-723a-a4f2-90ab12f127a4"
  ]
}

Success Response — 200 OK

{
  "success": true,
  "ordered_ids": [
    "0190104f-944f-7f32-84b2-c0e86b0317e2",
    "0190104f-124b-723a-a4f2-90ab12f127a4"
  ]
}

Photo Sets

Every new gallery has a `Highlights` set. All Photo Sets endpoints require authentication and return `404 Not Found` for galleries that are inactive or owned by another photographer.

List sets

GET /api/v1/photos/{gallery_slug}/sets/

Returns ordered set metadata. `photo_count` is the current number of assets in each set.

[
  {
    "id": "0190104f-124b-723a-a4f2-90ab12f127a4",
    "name": "Highlights",
    "description": "Featured moments",
    "order": "1.0000000000",
    "photo_count": 12
  }
]

Create a set

POST /api/v1/photos/{gallery_slug}/sets/

Request body: `{ "name": "Ceremony", "description": "Optional, up to 500 characters" }`. Names are required, unique within their gallery, and limited to 100 characters.

Update a set

PATCH /api/v1/photos/{gallery_slug}/sets/{set_id}/

Accepts either or both `name` and `description`.

Delete a set

DELETE /api/v1/photos/{gallery_slug}/sets/{set_id}/

Assets are never deleted. Assets in the deleted set move atomically to the first remaining set. The final remaining set cannot be deleted (`400 Bad Request`).

Reorder sets

PATCH /api/v1/photos/{gallery_slug}/sets/reorder/

Request body: `{ "ordered_ids": ["<set-uuid>", "<set-uuid>"] }`.

Move assets to a set

PATCH /api/v1/photos/{gallery_slug}/move/

Request body: `{ "set_id": "<set-uuid>", "photo_ids": ["<asset-uuid>"] }`. Use `set_id: null` to remove an asset from its set.

Upload and list integration

`POST /api/v1/photos/{gallery_slug}/upload/` accepts optional multipart `set_id`; it must belong to the gallery. When omitted, uploaded assets are assigned to the first set. `GET /api/v1/photos/{gallery_slug}/?set=<set-uuid>` returns only assets in that gallery-owned set. Media asset payloads expose `photo_set` as its set UUID (or `null`).

👥 4. Public Clients App (apps/clients)

These endpoints are configured with empty authentication classes. They ignore stale user header tokens.

Public Gallery

GET /api/v1/public/{username}/{slug}/

Main public gateway. Scoped by subdomain (username) and gallery name (slug).

Authentication: None (authentication_classes = [])

Success Response — 200 OK — No Password / Unlocked

{
  "id": "0190101b-944f-7f32-84b2-c0e86b0317e2",
  "title": "Sita and Hari Wedding",
  "description": "Fine art wedding coverage.",
  "slug": "sita-and-hari-wedding",
  "branding_color": "#1ABC9C",
  "photographer_name": "Kroman Studios",
  "allow_download": true,
  "watermark_enabled": false,
  "is_password_protected": false,
  "photos": [
    {
      "id": "0190104f-124b-723a-a4f2-90ab12f127a4",
      "media_type": "image",
      "title": "Procession Entrance",
      "display_url": "http://localhost:8000/media/photographers/.../photos/..._display.webp",
      "thumbnail_url": "http://localhost:8000/media/photographers/.../thumbnails/..._thumb.webp",
      "blurhash": "LKO2?U%2Tw=w]~RBVZRi};RPxuwH",
      "width": 6000,
      "height": 4000,
      "stream_url": null,
      "poster_url": null,
      "preview_url": null,
      "duration": null
    }
  ]
}

Success Response — 200 OK — Password Gate Required

This is used to render the full-screen lock screen without throwing a 401.

{
  "requires_password": true,
  "title": "Sita and Hari Wedding",
  "branding_color": "#1ABC9C"
}

Unlock Public Gallery

POST /api/v1/public/{username}/{slug}/unlock/

Verifies the guest password and scopes a session token on success.

Authentication: None (authentication_classes = [])

Request Body — JSON

{
  "password": "sita_hari_pass",
  "email": "guest@weddingguests.com"
}

Success Response — 200 OK

The client saves this access_token in sessionStorage. To query the private gallery data, append it as a query parameter:

/api/v1/public/{username}/{slug}/?token=<access_token>

{
  "access_token": "CSPRNG_high_entropy_session_token_hash",
  "has_download_access": true
}

Authorize a Download (explicit client action)

POST /api/v1/public/{username}/{slug}/download-access/

Opening or browsing a gallery never requires a download PIN or email. A client
authorizes a download only when they choose Download. The gallery password and
the download PIN are separate gates: a password-protected gallery still needs
its unlock token (`Authorization: Bearer <access_token>` or `token` in the body).
Throttled like the unlock endpoint (5/minute) because it is where a PIN can be
guessed.

The PIN is enforced only when a PIN hash is saved (`POST /galleries/{slug}/set-download-pin/`)
AND `design_settings.downloads.pin_enabled` is not `false` (the Download-tab toggle; a
missing value counts as on). Toggle on without a saved PIN enforces nothing; toggle off
stops enforcement but keeps the stored hash. The public `has_download_pin` reflects the
enforced state. Neither the PIN nor its hash is ever returned.

Request Body — JSON

{
  "email": "guest@example.com",   // required unless the unlock session already has one
  "pin": "4821"                   // required only while the gallery's download PIN is enforced
}

Success Response — 200 OK

{
  "download_token": "<signed, short-lived>",
  "expires_in": 7200,
  "email": "guest@example.com",
  "pin_verified": true
}

The `download_token` is a signed token bound to this gallery and to the current
PIN (changing or clearing the PIN invalidates it), valid for
`DOWNLOAD_ACCESS_TTL_SECONDS` (default 2 hours). Pass it as `download_token` to
the download endpoints below so email/PIN are asked once per visit, not per
photo. Errors use `{ "error": "...", "code": "..." }` with codes: `pin_required`,
`invalid_pin`, `email_required`, `invalid_email`, `session_required`,
`downloads_disabled`, `download_access_expired`.

Download One Photo

GET /api/v1/public/{username}/{slug}/photo/{photo_id}/download/?download_token=<token>&resolution=download|web|original

Streams one file as an attachment. `resolution` defaults to `download` (the
Download Master, shown to clients as "High Resolution"); `web` is the display
derivative. A raw `?pin=` is still accepted for scripted callers but is held to
the 5/minute PIN-guess throttle. The activity log records the email carried by
the token.

Download a Gallery or Set (prepared in the background)

Gallery and set ZIPs are never streamed straight from a click. Three steps:

1. POST /api/v1/public/{username}/{slug}/download/

Body: `{ "download_token": "...", "resolution": "download|web", "set_id": "<photo_set_id>", "token": "<unlock>" }`
(`asset_ids` — a list of this gallery's asset ids — is also accepted.) Every
gate runs here first — gallery published/active/unexpired, `allow_download`,
the unlock session of a password-protected gallery, the download token (email
and PIN), the size policy and the size limits — and only then is a job queued.
Nothing is queued for a refused request. An identical request that is still
preparing or ready is reused. An unknown/foreign/malformed `set_id` is a 404,
never widened to the whole gallery. Throttled with the 5/minute PIN scope.

Response — 202 Accepted

{ "job_id": "<uuid>", "state": "preparing", "status_url": ".../download-jobs/<uuid>/" }

2. GET /api/v1/public/{username}/{slug}/download-jobs/{job_id}/?download_token=<token>[&token=<unlock>]

{ "state": "preparing", "files": [] }
{ "state": "ready", "files": [ { "name": "my-gallery-photo-download-1of1.zip", "size_bytes": 5173859, "url": ".../files/0/?file_token=..." } ] }
{ "state": "failed", "code": "no_media|download_too_large|prepare_failed|prepare_timeout|download_expired", "error": "...", "files": [] }

The same download token that created the job is required, and its email must be
the job's (another visitor's token, or another gallery's, reads as not found).
Each `url` carries a signed `file_token` bound to this one job; it is good for
`DOWNLOAD_FILE_URL_TTL_SECONDS` (default 24 hours, the job's own lifetime), so the
link keeps working repeatedly until the download expires. A ready response also
carries `expires_at`. The status endpoint checks the stored file still exists
before it says `ready`; if it vanished the state is `failed` / `file_missing`. The archive is always one part:
`{gallery-slug}-photo-download-1of1.zip` (ZIP_STORED; the backend does not split).
A job that stays `preparing` longer than `DOWNLOAD_JOB_STALE_SECONDS` reads as failed.

3. GET /api/v1/public/{username}/{slug}/download-jobs/{job_id}/files/{index}/?file_token=<signed>[&token=<unlock>]

A file token issued for a different job/file answers 404 `download_not_found`; a
missing/tampered one 403; an expired job 410 `download_expired`. When the caller
is a browser navigating to the URL (`Accept: text/html`), those "prepare it again"
failures redirect to `/g/{username}/{slug}/download?link=expired` (a friendly page
with a Prepare again button) instead of showing JSON.

Streams the ZIP from private storage as an attachment. The signed file token,
the live gallery gates (published, `allow_download`, unlock session), the job's
gallery binding, its expiry and the PIN fingerprint are checked on every request.
The first request for a file writes the Download Activity row (email, set,
resolution, pin_verified and the real attachment `filename`); a retry of the same
file within 60 seconds from the same visitor is not a second download.
Prepared files and their jobs expire after `DOWNLOAD_JOB_TTL_SECONDS` (default
24 hours) and are purged hourly (Celery Beat: `purge-expired-download-jobs`).
When an email was captured, the visitor is also emailed a link back to
`/g/{username}/{slug}/download?job={job_id}` (it carries no credential).

`GET .../download-all/` is retired and always answers 410
`download_requires_preparation`.

The photographer's bell reads "Gallery downloaded by <email>" /
"Photo downloaded by <email>" (one notification per real download).

Error Response — 401 Unauthorized

{
  "error": "Incorrect password.",
  "details": {
    "password": "Incorrect password."
  }
}

⚙️ Settings, Security & Account (apps/users)

GET / PATCH /api/v1/auth/settings/

Notification preferences, privacy and Collection Defaults for the signed-in
photographer. Scoped to the caller — there is no id in the URL or body. Unknown
keys are rejected with 400 (never silently ignored). The response is always the
full stored state.

{
  "notifications": { "downloads": false, "favorites": false, "payments": true },
  "privacy": { "portfolio_public": true },
  "collection_defaults": {
    "is_published": true, "is_downloadable": true, "watermark_enabled": false,
    "expires_in_days": 30,
    "design": { "typography": "bold", "colorPalette": "sea", "layout": "center",
                "gridStyle": "vertical", "thumbSize": "regular", "gridSpacing": 16 }
  }
}

- Each notification flag gates an email that is really sent: a client download or
  favorite (coalesced to one email per collection per 15 minutes) and a payment
  approved/rejected.
- `portfolio_public: false` makes /api/v1/public/{username}/ return the same 404
  as a nonexistent photographer; individual gallery links are unaffected.
- Collection Defaults apply once, at collection creation, only to fields the
  create request did not set. They never change an existing gallery.
  `watermark_enabled: true` needs a Pro+ plan (403 watermark_requires_upgrade).

PUT /api/v1/auth/me/ — profile (display_name, username, bio, phone, website,
avatar, logo, branding_color). The email is read-only. Avatar and logo uploads are
validated and re-encoded; `{"avatar": null}` removes the picture.

PUT /api/v1/auth/change-password/ — { old_password, new_password, new_password2 }.
Enforces the password policy (8+ characters, not too common, not all numeric, not
similar to the account's username/email), is throttled per user (10/hour), revokes
every outstanding refresh token, and returns fresh cookies for the calling device.

POST /api/v1/auth/logout-all/ — blacklists every outstanding refresh token for the
account and clears this browser's cookies. Access tokens already issued live up to
15 minutes.

🔔 Share, Activity & Notifications

Canonical share link — `share_url`

Both the public gallery payload (after any unlock) and the owner's gallery detail
include `share_url`: `{FRONTEND_URL}/g/{username}/{slug}`. It carries no credential
of any kind (no unlock/session token, download token or PIN, signed or storage
URL), so sharing it can never bypass a gallery's own gates — whoever opens it meets
the normal published / expiry / password checks. A password-protected gallery's
locked response does not include it.

The web app does not display this field: it builds the link it shows and copies from
the origin it is actually served from (`frontend/src/utils/appUrl.js`), because
`FRONTEND_URL` defaults to the Vite dev port (`http://localhost:5173`), which is not
where the Docker stack serves the app (`http://localhost:3000`).

Download Activity — GET /api/v1/galleries/{slug}/download-logs/?type=gallery|photo|video&page=N

Owner-only (404 for any other account or an unknown slug, 401 unauthenticated).
`type` filters one tab (an unknown value is 400 `invalid_type`); the response adds
`counts: { gallery, photo, video }` for every tab. Rows add `scope` ("Entire
gallery", "Set: X", "Single photo", "Single video"), `media_asset_name`, the
asset's set in `photo_set_name`, and `pin_state` ("verified" | "not_required").

Favorite Activity — GET /api/v1/galleries/{slug}/favorites/

- `?group=client` — one row per client's favorite LIST: `{ id, email, photo_count,
  created_at, updated_at }`, most recently updated first. `id` is an opaque HMAC of
  (gallery, client); the client's key / session token is never returned.
- `?list=<id>` — the photos in that list. An unknown, foreign or malformed id is 404.
- no params — the flat per-photo activity (unchanged).

Notifications (the dashboard bell) — all owner-scoped, 401 unauthenticated

- GET  /api/v1/notifications/?page=N&unread=1 → { results, unread_count, count, next, previous }
- GET  /api/v1/notifications/unread-count/ → { unread_count } (one indexed COUNT; safe to poll)
- POST /api/v1/notifications/{id}/read/ → { id, is_read, unread_count } (idempotent; a foreign
  or random id is 404 `not_found`)
- POST /api/v1/notifications/read-all/ → { marked, unread_count }

A notification is a short pointer to a recent event — `{ id, kind, message, count,
is_read, timestamp, link, gallery_slug }` — and never the source of truth: the
durable record stays in Download/Favorite Activity, Billing, and asset status.
Events: client download, client favorite, payment approved/rejected, gallery
published, media processing complete / failed (after retries). Bursts coalesce into
one unread row with a count. Read notifications are pruned after 30 days, unread
after 90 (daily Celery task).

💳 5. Billing & Subscription App (apps/subscriptions)

List Subscription Plans

GET /api/v1/subscriptions/plans/

Lists available platforms and billing rules, all read from the plan table (Django admin). `max_collections` / `video_minutes`: null = unlimited (video 0 = none). `estimated_photos` is an estimate of photos that fit in `storage_gb` (average photo size = `average_photo_size_mb`).

Authentication: None (authentication_classes = [])

Success Response — 200 OK

[
  {
    "id": "0190106a-ef1a-7b3c-b2f2-10e82f1217e9",
    "key": "free",
    "name": "Free",
    "price": "0.00",
    "is_free": true,
    "storage_gb": 3,
    "storage_bytes": 3221225472,
    "estimated_photos": 1000,
    "average_photo_size_mb": 3,
    "max_collections": 10,
    "video_minutes": 0,
    "features": [{"key": "watermark", "label": "Watermark", "included": false}]
  }
]

My Subscription

GET /api/v1/subscriptions/my-subscription/

Retrieves the authenticated photographer's subscription limits and usage metrics.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

Identical structure to the /stats/ mapping, plus (7.5-C) a `lifecycle` block that says where the paid period stands. It is computed
on the server in the billing time zone (Asia/Kathmandu), the same way every entitlement is: an ended period reads `expired` whether
or not the daily job has run.

  "lifecycle": {
    "state": "active" | "expiring" | "expired" | "none",   (expiring = live and inside the reminder window)
    "days_left": 20,                                       (calendar days; 0 = ends today; negative once ended; null for none)
    "period_end": "2026-10-28T18:01:45Z",
    "reminder_days": 3,                                    (admin-edited: Subscriptions > Subscription lifecycle)
    "grace_days": 3
  }

A user with no subscription gets `"status": "no_subscription"` and `"lifecycle": {"state": "none", ...}`. The daily job itself has no
HTTP endpoint (`manage.py run_subscription_lifecycle [--dry-run]`, docs/KYAPTURE_SUBSCRIPTION_LIFECYCLE.md).

Submit Manual Payment

POST /api/v1/subscriptions/payments/

Reports a bank or eSewa payment with a transaction ID and a proof file, for staff review (chunk 7.5-B, docs/KYAPTURE_PAYMENTS.md).

Authentication: Required (IsAuthenticated). Throttle: payment_submit, 10/hour per user.

Important: The registered endpoint is /api/v1/subscriptions/payments/, not /api/v1/subscriptions/pay/.

Request Body — multipart/form-data

plan: "0190106a-ef1a-7b3c-b2f2-10e82f1217e9"
amount: "1499.00"            (must equal the plan's price right now; the price is frozen on the payment row)
reference: "FT24-ABC/9"      (the transaction ID: 4-64 characters, letters, digits and . _ / - ; unique across all payments, compared trimmed and lower-cased)
payment_proof: [File]        (PNG, JPEG, WEBP or PDF, judged by its bytes, up to the server's limit; stored privately)
notes: "Paid by eSewa"       (optional, plain text, 500 characters)

Success Response — 201 Created

{
  "message": "Payment submitted. We will review it shortly.",
  "payment": { "id": "...", "plan_name": "Pro", "amount": "1499.00", "currency": "NPR", "reference": "FT24-ABC/9",
               "status": "pending", "has_proof": true, ... }
}

Refusals — 400 { "error": "<message>", "code": "<code>", "errors": { "<field>": ["<message>"] } }

reference_required / reference_invalid / reference_taken / reference_already_submitted, amount_mismatch,
proof_empty / proof_too_large / proof_invalid, too_many_pending, duplicate_pending. 429 past the throttle.

List Payment History

GET /api/v1/subscriptions/payments/

The signed-in user's OWN payments, newest first (staff included: the review queue is under /api/v1/staff/payments/).
Keys: id, plan_name, amount, currency, reference, status, created_at, reviewed_at, rejection_reason, period_end,
has_proof, notes. No proof file or link is ever returned to the user.

Authentication: Required (IsAuthenticated)

Payment Instructions

GET /api/v1/subscriptions/payment-instructions/

Where to send the money: the admin-edited PaymentInstructions row (account_name, esewa_id, bank_name,
bank_account_number, bank_branch, note, qr_url) plus currency, period_days (days one approved payment buys),
proof_max_mb and max_pending. Authentication: Required.

Review Manual Payments (staff only: 401 anonymous, 403 for anyone who is not is_staff)

GET  /api/v1/staff/payments/?status=pending|approved|rejected|all&page=      the queue (pending oldest first, 25 per page)
POST /api/v1/staff/payments/{payment_id}/approve/                            approve (idempotent)
POST /api/v1/staff/payments/{payment_id}/reject/   { "reason": "..." }       reject (reason required, 1-300 characters)
POST /api/v1/staff/payments/{payment_id}/proof-link/                         { "url", "expires_in", "content_type" }
GET  /api/v1/staff/payments/{payment_id}/proof/?s=<signed link>              the proof file (staff sign-in AND the link)

Approve / reject answer 200 { "changed": true|false, "code", "message", "payment": { ... } }. A repeat answers
"changed": false and changes nothing; an approve after a reject (or a reject after an approve) is 409
already_rejected / already_approved; staff cannot review their own payment (403 cannot_review_own).
The two routes this replaces (GET /subscriptions/admin/payments/ and POST /subscriptions/payments/{id}/review/) no longer exist.

Endpoint Quick Reference

Method

Endpoint

Authentication

Purpose

POST

/api/v1/auth/register/

None

Register photographer

POST

/api/v1/auth/login/

None

Login

POST

/api/v1/auth/logout/

Required

Logout

POST

/api/v1/auth/token/refresh/

None

Refresh JWT

GET

/api/v1/auth/me/

Required

Get profile

PUT

/api/v1/auth/me/

Required

Update profile

PUT

/api/v1/auth/change-password/

Required

Change password

GET

/api/total-users

None

Public user count

GET

/api/v1/galleries/

Required

List galleries

POST

/api/v1/galleries/

Required

Create gallery

GET

/api/v1/galleries/{slug}/

Required

Get gallery

PUT

/api/v1/galleries/{slug}/

Required

Update gallery

DELETE

/api/v1/galleries/{slug}/

Required

Delete gallery

GET

/api/v1/galleries/dashboard/stats/

Required

Dashboard statistics

GET

/api/v1/photos/{gallery_slug}/

Required

List media

POST

/api/v1/photos/{gallery_slug}/upload/

Required

Upload media

GET

/api/v1/photos/photo/{photo_id}/

Required

Get media

DELETE

/api/v1/photos/photo/{photo_id}/

Required

Delete media

POST

/api/v1/photos/{gallery_slug}/delete-bulk/

Required

Bulk delete

PATCH

/api/v1/photos/{gallery_slug}/reorder/

Required

Reorder media

GET

/api/v1/public/{username}/{slug}/

None

Public gallery

POST

/api/v1/public/{username}/{slug}/unlock/

None

Unlock gallery

GET

/api/v1/subscriptions/plans/

None

List plans

GET

/api/v1/subscriptions/my-subscription/

Required

Get subscription

GET

/api/v1/subscriptions/payments/

Required

List payments

POST

/api/v1/subscriptions/payments/

Required

Submit payment

POST

/api/v1/subscriptions/payment-instructions/

Required

Payment instructions

GET

/api/v1/staff/payments/

Staff

Payment review queue

POST

/api/v1/staff/payments/{payment_id}/approve/ | reject/ | proof-link/

Staff

Review payment

⚠️ Important Endpoint Corrections

The following two routes are the corrected registered routes:

1. Total Users

GET /api/total-users

Not:

GET /api/v1/auth/total-users/

2. Manual Payments

POST /api/v1/subscriptions/payments/

Not:

POST /api/v1/subscriptions/pay/

The payments endpoint is also used for:

GET /api/v1/subscriptions/payments/

to list payment history.

## Performance notes (Task 5)

- **Public gallery cover tiers.** `GET /api/v1/public/{username}/{slug}/` now also returns `cover_medium_url` — the 1280px WebP of the same cover as `cover_url` (2048px) — or `null` when the cover is a video poster or has no medium derivative. The client page uses the pair as a `srcset` so phones/small windows don't download the 2048px file.
- **Malformed `?set=`.** On both `GET /api/v1/public/{username}/{slug}/` and `.../photos/`, a `set` value that is not a UUID is treated like a set that doesn't exist: an empty page (HTTP 200), never a 500.
- **JSON compression.** `application/json` responses are gzip-encoded when the client sends `Accept-Encoding: gzip` (`Vary: Accept-Encoding`). File downloads, ZIP streams and media are never content-encoded.
- **Query behaviour (guarded by `apps/galleries/tests/test_query_efficiency.py`).** The dashboard gallery list/search, the public portfolio, the owner gallery detail and the public gallery page issue a constant number of queries regardless of how many galleries/photos exist.

## Visitor favorites and Favorite Activity (Task 1R.3)

Visitor side (no accounts; identity = the gallery unlock token for protected
galleries, else the browser's `client_uid`; it is never returned by any endpoint):

- `POST .../favorites/` `{ media_asset_id, client_uid, email?, name?, list_id? }` — adds the
  photo to the visitor's default "My Favorites" list (created on first use) and stores
  their email; a malformed email is 400 `invalid_email`. `GET .../favorites/` returns
  `{ favorited_ids, email }` (the email the visitor already gave, so it is asked once).
  `DELETE .../favorites/` removes the photo from one list (`list_id`) or from all of the
  visitor's lists; the response says whether it is still favorited elsewhere.
- `GET|POST .../favorites/lists/` — the visitor's own lists (`?sort=newest|oldest`) /
  create one `{ name }` (1-80 chars, unique per visitor, max 20 lists).
- `GET|PATCH|DELETE .../favorites/lists/{list_id}/` — photos of the list (paginated) /
  rename / delete the list (the photos stay in the gallery). Another visitor's, another
  gallery's, unknown or malformed ids are all a plain 404.

Photographer side — `GET /api/v1/galleries/{slug}/favorites/`:

- `?group=visitor[&email=][&sort=newest|oldest|email]` — lists grouped by visitor (real
  email, or `null` = Guest), each with its lists (name, `photo_count`, `thumbnail_url`,
  `created_at`, `updated_at`).
- `?group=client` — one row per list; `?list=<uuid>` — the photos of one list (real file
  names + thumbnails). Notifications read "<email> favorited N photos".

Download Activity rows now also carry `photo_count` (gallery ZIPs), `thumbnail_url`
(single photos) and the stored attachment `filename`.

## Permanent deletes, covers and photographer favorites (Task 5.1)

**Delete is permanent.** `DELETE /api/v1/galleries/{slug}/` (collection),
`DELETE /api/v1/photos/photo/{id}/` and `POST /api/v1/photos/{slug}/delete-bulk/` (photos) and
`DELETE /api/v1/photos/{slug}/sets/{set_id}/` (a set **and its photos**; the last set cannot be deleted;
the response carries `deleted_photos`) remove the database rows immediately and every stored object
(original, Download Master, display/medium/thumbnail derivatives, video poster/preview/playback, prepared
download ZIPs, and for a collection everything under its storage prefix) through ONE idempotent Celery task
queued with `transaction.on_commit` (retried with backoff; a permanent failure is logged with the object
names). Storage usage and quota drop at once because they are computed from live rows. `deleted_count`
counts photos only. Activity: a deleted photo's download history is kept without the photo link; a deleted
collection's activity is deleted with it. Owner-only; foreign or malformed ids are 404.
`manage.py purge_orphans [--dry-run] [--delete] [--min-age-minutes N]` lists (default) or removes storage
objects no row refers to; it only looks under `photographers/*/galleries/` and `download_jobs/` and skips
recent files.

**Cover.** The first photo to reach READY becomes the cover when there is none (one conditional UPDATE,
safe under concurrent uploads and Celery retries; a manual cover is never overwritten). Deleting the cover
falls back to the next READY photo by order, else none. The cover changes manually only via
`PATCH /api/v1/galleries/{slug}/ {cover_photo}` ("Set as cover").

**Photographer favorites** (the heart on a workspace tile; unrelated to the cover and to visitors' favorites):
`PUT /api/v1/photos/photo/{id}/favorite/ {"is_favorite": true|false}` (booleans only, idempotent) and
`GET /api/v1/photos/favorites/all/` (paginated, newest first, each row also has `gallery_slug`,
`gallery_title`). Photo payloads include `is_favorite`.

