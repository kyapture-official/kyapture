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

Success Response — 200 OK

{
  "plan": {
    "name": "Basic",
    "expires_at": "2026-07-13T10:30:00Z",
    "days_remaining": 29
  },
  "storage": {
    "used_bytes": 524288000,
    "limit_bytes": 5368709120,
    "percentage_used": 9.77
  },
  "metrics": {
    "total_galleries_used": 2,
    "max_galleries_allowed": 3,
    "total_views": 184
  }
}

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

Success Response — 201 Created

Returns an array of successfully serialized asset objects.

Gated Error Response — 400 Bad Request

{
  "error": "Storage quota limit exceeded.",
  "code": "storage_limit_reached",
  "details": {
    "current_storage_mb": "4950.0",
    "upload_batch_mb": "120.4",
    "plan_limit_gb": "5.0",
    "message": "This upload of 120.4 MB would push your account past your 5.0 GB plan storage limit."
  }
}

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

Download All Public Gallery Media

GET /api/v1/public/{username}/{slug}/download-all/?token=<access_token>

Streams a ZIP of READY media when downloads are enabled. JPEG and PNG images
use the private, full-resolution Download Master; videos and legacy/special
images without a master retain their original source. Pass `resolution=original`
to the existing POST download endpoint for an authorized original archive.
Password-protected galleries require the active unlock token. Galleries with a
download PIN continue to use the existing POST download flow so the PIN can be
verified before a browser download starts. The response is an attachment named
`{gallery-slug}.zip` and creates a gallery `DownloadLog` entry.

Error Response — 401 Unauthorized

{
  "error": "Incorrect password.",
  "details": {
    "password": "Incorrect password."
  }
}

💳 5. Billing & Subscription App (apps/subscriptions)

List Subscription Plans

GET /api/v1/subscriptions/plans/

Lists available platforms and billing rules.

Authentication: None (authentication_classes = [])

Success Response — 200 OK

[
  {
    "id": "0190106a-ef1a-7b3c-b2f2-10e82f1217e9",
    "name": "Basic",
    "price": "19.99",
    "max_galleries": 3,
    "max_photos_per_gallery": 100,
    "storage_gb": 5,
    "storage_bytes": 5368709120
  }
]

My Subscription

GET /api/v1/subscriptions/my-subscription/

Retrieves the authenticated photographer's subscription limits and usage metrics.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

Identical structure to the /stats/ mapping.

Submit Manual Payment

POST /api/v1/subscriptions/payments/

Submits bank, eSewa, or Khalti transaction screenshot receipts for review.

Authentication: Required (IsAuthenticated)

Important: The registered endpoint is /api/v1/subscriptions/payments/, not /api/v1/subscriptions/pay/.

Request Body — multipart/form-data
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

Lists available platforms and billing rules.

Authentication: None (authentication_classes = [])

Success Response — 200 OK

[
  {
    "id": "0190106a-ef1a-7b3c-b2f2-10e82f1217e9",
    "name": "Basic",
    "price": "19.99",
    "max_galleries": 3,
    "max_photos_per_gallery": 100,
    "storage_gb": 5,
    "storage_bytes": 5368709120
  }
]

My Subscription

GET /api/v1/subscriptions/my-subscription/

Retrieves the authenticated photographer's subscription limits and usage metrics.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

Identical structure to the /stats/ mapping.

Submit Manual Payment

POST /api/v1/subscriptions/payments/

Submits bank, eSewa, or Khalti transaction screenshot receipts for review.

Authentication: Required (IsAuthenticated)

Important: The registered endpoint is /api/v1/subscriptions/payments/, not /api/v1/subscriptions/pay/.

Request Body — multipart/form-data

plan: "0190106a-ef1a-7b3c-b2f2-10e82f1217e9"
amount: "19.99"
payment_proof: [File] (Receipt screenshot up to 5MB)
notes: "Transacted via eSewa transaction ID 9831..."

Success Response — 201 Created

{
  "message": "Payment receipt submitted successfully. Admin review pending."
}

List Payment History

GET /api/v1/subscriptions/payments/

Lists payment history. Photographers see their own history; administrative staff see the entire global review queue.

Authentication: Required (IsAuthenticated)

Success Response — 200 OK

Returns an array of submitted payment objects.

Review Manual Payment

POST /api/v1/subscriptions/payments/{payment_id}/review/

Admin-only approval or rejection of submitted manual payments.

Authentication: Required (IsAdminUser)

Request Body — JSON

{
  "action": "approve",
  "admin_note": "Verified amount. Transacted via transaction ID 9831."
}

Success Response — 200 OK

{
  "message": "Payment approved. Subscription activated.",
  "payment": {
    "status": "approved",
    "notes": "..."
  },
  "subscription": {
    "status": "active",
    "days_remaining": 29
  }
}

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

/api/v1/subscriptions/payments/{payment_id}/review/

Admin

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
