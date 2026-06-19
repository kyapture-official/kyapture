Kaypture API v1 — Core Contract Specifications
All API endpoints are prefixed with /api/v1/. Request and response payloads are strictly formatted in JSON. For file uploads, use multipart/form-data.
🔐 1. Authentication App (apps/users)
All protected endpoints require the following header:
Authorization: Bearer <access_token>
POST /api/v1/auth/register/
Description: Public endpoint to create a new photographer account.
Authentication: None (authentication_classes = [])
Request Body (JSON):
code
JSON
{
  "email": "photographer@test.com",
  "username": "kroman",
  "display_name": "Kroman Studios",
  "password": "SecurePassword123!",
  "password2": "SecurePassword123!"
}
Success Response (201 Created):
code
JSON
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
Error Response (400 Bad Request):
code
JSON
{
  "error": "Invalid field 'username': Username is already taken.",
  "details": {
    "username": ["This username is already taken."]
  }
}
POST /api/v1/auth/login/
Description: Authenticates credentials and returns JWT session tokens.
Authentication: None (authentication_classes = [])
Request Body (JSON):
code
JSON
{
  "email": "photographer@test.com",
  "password": "SecurePassword123!"
}
Success Response (200 OK):
code
JSON
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
POST /api/v1/auth/logout/
Description: Blacklists the active refresh token.
Authentication: Required (IsAuthenticated)
Request Body (JSON):
code
JSON
{
  "refresh": "jwt_refresh_token_string"
}
Success Response (200 OK):
code
JSON
{
  "message": "Logged out successfully."
}
POST /api/v1/auth/token/refresh/
Description: Generates a new short-lived access token from an active refresh token.
Authentication: None
Request Body (JSON):
code
JSON
{
  "refresh": "jwt_refresh_token_string"
}
Success Response (200 OK):
code
JSON
{
  "access": "new_jwt_access_token_string"
}
GET /api/v1/auth/me/
Description: Returns the active photographer's profile details.
Authentication: Required (IsAuthenticated)
Success Response (200 OK):
code
JSON
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
PUT /api/v1/auth/me/
Description: Partially updates photographer profile data (e.g. bio, avatar).
Authentication: Required (IsAuthenticated)
Request Body (multipart/form-data):
display_name: "Kroman Wedding Fine Art"
bio: "Wedding fine art based in Nepal."
avatar: [File] (Optional image up to 2MB)
Success Response (200 OK): Updated user profile object.
PUT /api/v1/auth/change-password/
Description: Updates the authenticated user's password safely.
Authentication: Required (IsAuthenticated)
Request Body (JSON):
code
JSON
{
  "old_password": "SecurePassword123!",
  "new_password": "BrandNewPassword2026!",
  "new_password2": "BrandNewPassword2026!"
}
Success Response (200 OK):
code
JSON
{
  "message": "Password changed successfully."
}
GET /api/v1/auth/total-users/
Description: Public dashboard/landing page registered user count counter.
Authentication: None (authentication_classes = [])
Success Response (200 OK):
code
JSON
{
  "total_count": 47,
  "latest_users": []
}
🖼 2. Galleries App (apps/galleries)
GET /api/v1/galleries/
Description: Lists all active (non-soft-deleted) collections created by the photographer.
Authentication: Required (IsAuthenticated)
Success Response (200 OK):
code
JSON
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
POST /api/v1/galleries/
Description: Creates a new gallery collection. Gated by active plan limits.
Authentication: Required (IsAuthenticated & IsSubscribed)
Request Body (JSON):
code
JSON
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
Success Response (201 Created): Returns the detailed GalleryDetail object.
Gated Error Response (403 Forbidden - Limit Reached):
code
JSON
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
GET /api/v1/galleries/{slug}/
Description: Retrieves detailed parameters for a specific gallery.
Authentication: Required (IsAuthenticated)
Success Response (200 OK):
code
JSON
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
PUT /api/v1/galleries/{slug}/
Description: Updates settings or cover photo UUID for a specific gallery.
Authentication: Required (IsAuthenticated)
Request Body (JSON): Supports partial updates.
code
JSON
{
  "title": "Sita and Hari Anniversary",
  "cover_photo": "0190104f-124b-723a-a4f2-90ab12f127a4",
  "branding_color": "#000000"
}
Success Response (200 OK): Updated detailed gallery object.
DELETE /api/v1/galleries/{slug}/
Description: Soft-deletes a gallery (flips is_active = False). Keeps files intact to prevent accidental loss.
Authentication: Required (IsAuthenticated)
Success Response (200 OK):
code
JSON
{
  "message": "Gallery deleted successfully."
}
GET /api/v1/galleries/dashboard/stats/
Description: Single-pass optimized aggregate statistics of the photographer's account.
Authentication: Required (IsAuthenticated)
Success Response (200 OK):
code
JSON
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
GET /api/v1/photos/{gallery_slug}/
Description: Lists all photos and video assets inside an active gallery, sorted by manual order.
Authentication: Required (IsAuthenticated)
Success Response (200 OK):
code
JSON
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
POST /api/v1/photos/{gallery_slug}/upload/
Description: Processes single or bulk uploads. Gated by storage quota and image thresholds.
Authentication: Required (IsAuthenticated & IsSubscribed)
Request Body (multipart/form-data):
image: [File] (One or many files; JPEGs/PNGs up to 25MB)
title: "Anniversary Prep" (Optional metadata)
Success Response (201 Created): Array of successfully serialized asset objects.
Gated Error Response (400 Bad Request - Storage Exceeded):
code
JSON
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
GET /api/v1/photos/photo/{photo_id}/
Description: Retrieves metadata of a single asset.
Authentication: Required (IsAuthenticated)
Success Response (200 OK): Single asset JSON object.
DELETE /api/v1/photos/photo/{photo_id}/
Description: Purges an asset from the database and automatically triggers background signals to erase all physical variants (Original, display WebP, thumbnail WebP) from disk or AWS S3.
Authentication: Required (IsAuthenticated)
Success Response (200 OK):
code
JSON
{
  "message": "Media asset deleted successfully."
}
👥 4. Public Clients App (apps/clients)
These endpoints are configured with empty authentication classes. They ignore stale user header tokens.
GET /api/v1/public/{username}/{slug}/
Description: Main public gateway. Scoped by subdomain (username) and gallery name (slug).
Authentication: None (authentication_classes = [])
Success Response (200 OK - No Password / Unlocked):
code
JSON
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
Success Response (200 OK - Password Gate Required):
David uses this to render the full-screen lock screen without throwing a 401.
code
JSON
{
  "requires_password": true,
  "title": "Sita and Hari Wedding",
  "branding_color": "#1ABC9C"
}
POST /api/v1/public/{username}/{slug}/unlock/
Description: Verifies guest password. Scopes a session token on success.
Authentication: None (authentication_classes = [])
Request Body (JSON):
code
JSON
{
  "password": "sita_hari_pass",
  "email": "guest@weddingguests.com"
}
Success Response (200 OK):
David saves this access_token in sessionStorage. To query the private gallery data, append it as a query parameter: /api/v1/public/{username}/{slug}/?token=<access_token>.
code
JSON
{
  "access_token": "CSPRNG_high_entropy_session_token_hash",
  "has_download_access": true
}
Error Response (401 Unauthorized):
code
JSON
{
  "error": "Incorrect password.",
  "details": {
    "password": "Incorrect password."
  }
}
💳 5. Billing & Subscription App (apps/subscriptions)
GET /api/v1/subscriptions/plans/
Description: Lists available platforms and billing rules.
Authentication: None (authentication_classes = [])
Success Response (200 OK):
code
JSON
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
GET /api/v1/subscriptions/my-subscription/
Description: Retrieves authenticated photographer's subscription limits and usage metrics.
Authentication: Required (IsAuthenticated)
Success Response (200 OK): Identical structure to /stats/ mapping.
POST /api/v1/subscriptions/pay/
Description: Submits bank, eSewa, or Khalti transaction screenshot receipts for review.
Authentication: Required (IsAuthenticated)
Request Body (multipart/form-data):
plan: "0190106a-ef1a-7b3c-b2f2-10e82f1217e9"
amount: "19.99"
payment_proof: [File] (Receipt screenshot up to 5MB)
notes: "Transacted via eSewa transaction ID 9831..."
Success Response (210 Created):
code
JSON
{
  "message": "Payment receipt submitted successfully. Admin review pending."
}
GET /api/v1/subscriptions/payments/
Description: Lists payment history. Photographers see their own history; administrative staff see the entire global review queue.
Authentication: Required (IsAuthenticated)
Success Response (200 OK): Array of submitted payment objects.
POST /api/v1/subscriptions/payments/{payment_id}/review/
Description: Admin-only approval or rejection of submitted manual payments.
Authentication: Required (IsAdminUser)
Request Body (JSON):
code
JSON
{
  "action": "approve",
  "admin_note": "Verified amount. Transacted via transaction ID 9831."
}
Success Response (200 OK):
code
JSON
{
  "message": "Payment approved. Subscription activated.",
  "payment": { "status": "approved", "notes": "..." },
  "subscription": { "status": "active", "days_remaining": 29 }
}

### `POST /api/v1/photos/{gallery_slug}/delete-bulk/`
*   **Description:** Deletes multiple media assets (both photos and videos) inside a target gallery in a single request.
*   **Authentication:** Required (`IsAuthenticated`)
*   **Request Body (JSON):**
    ```json
    {
      "photo_ids": [
        "0190104f-124b-723a-a4f2-90ab12f127a4",
        "0190104f-944f-7f32-84b2-c0e86b0317e2"
      ]
    }
    ```
*   **Success Response (200 OK):**
    *   *Returns the count of successfully deleted records. S3 files are automatically purged via background signals.*
    ```json
    {
      "deleted_count": 2
    }
    ```

### `PATCH /api/v1/photos/{gallery_slug}/reorder/`
*   **Description:** Updates the manual drag-and-drop sequencing of all assets inside a gallery. Sets clean, sequential decimal order coordinates.
*   **Authentication:** Required (`IsAuthenticated`)
*   **Request Body (JSON):**
    ```json
    {
      "ordered_ids": [
        "0190104f-944f-7f32-84b2-c0e86b0317e2",
        "0190104f-124b-723a-a4f2-90ab12f127a4"
      ]
    }
    ```
*   **Success Response (200 OK):**
    ```json
    {
      "success": true,
      "ordered_ids": [
        "0190104f-944f-7f32-84b2-c0e86b0317e2",
        "0190104f-124b-723a-a4f2-90ab12f127a4"
      ]
    }
    ```