# KYAPTURE feedback (chunk 6.3-A: backend and staff inbox API)

Model `users.Feedback` (table `feedback`): user, category, subject, message, route, gallery_slug,
app_version, browser_class, status, created_at, updated_at. Code: `backend/apps/users/feedback_api.py`.

| Endpoint | Who | Notes |
|---|---|---|
| `POST /api/v1/feedback/` | any signed-in user | throttled per user id, `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES["feedback"]` (5/hour) |
| `GET /api/v1/feedback/mine/` | the caller | only their own rows, newest first, paginated |
| `GET /api/v1/feedback/inbox/?status=&category=&page=&page_size=` | `is_staff` | newest first, 20 per page (max 100) |
| `PATCH /api/v1/feedback/inbox/{id}/` | `is_staff` | body `{"status": ...}` only; any other key is a 400 |

- Categories: bug, feature_request, design, performance, download, upload, security_privacy, other.
- Statuses: new, reviewed, in_progress, resolved, dismissed. Staff is Django `is_staff`; a normal user gets 403.
- Limits: subject 120 chars (one line, **optional since 6.3-B**: an empty subject is stored as ''), message 4000 (required), route 200. Text is trimmed; an empty message is a 400. Unknown body fields are ignored.
- Auto-captured: `route` (path only: query string and fragment dropped, UUID/long-token segments masked), `gallery_slug`
  (slug-shaped or dropped), `app_version` (kept only if it equals `settings.APP_VERSION` or is in
  `FEEDBACK_ACCEPTED_APP_VERSIONS`, else `unknown`), `browser_class` (read from the User-Agent header into
  chrome/edge/firefox/safari/opera/other; a body value is ignored). Tokens, cookies, signed URLs, PINs and IPs are never stored.
- Text is stored and returned as plain JSON, never marked safe. The inbox UI (6.3-B) must render it escaped.
- **No attachments**: the model has no file field and the API accepts none.
- A new feedback creates one `Notification` (kind `feedback`) per active staff account, shown in the existing bell.
  No email, no websocket.

## UI (chunk 6.3-B)

- **Floating button + panel**: `frontend/src/components/shared/FeedbackWidget.jsx`, mounted once in `App.jsx`. Shown only to a signed-in
  user on `/dashboard` and `/dashboard/*` (dashboard pages and the gallery workspace); never on `/g/*` (client gallery, download pages),
  login, register, forgot/reset password, pricing or the landing page. It steps aside (and the open panel with its draft) while a modal,
  limit modal, the lightbox or the phone menu drawer is open (`aria-modal="true"` / `role="alertdialog"`), and while a file is still
  uploading (`data-hide-feedback-fab` on the upload list). Page content ends with bottom padding so nothing stays under the button; on a
  phone the workspace button sits above the photo-sets bar and the bottom tabs.
- **Panel**: category (required), subject (optional, 120), message (required, 4000). Loading / success / error; a failure (network, 429,
  400) keeps every typed character; Escape closes from anywhere; focus goes to the first field on open and back to the button on close.
- **What is sent**: `{category, subject?, message, route, app_version}`. `route` is `location.pathname` only. `app_version` is the single
  build constant in `frontend/src/utils/appVersion.js` (`VITE_APP_VERSION`, default `dev`). Docker compose gives the backend `APP_VERSION`
  and the frontend build `VITE_APP_VERSION` from the same `${APP_VERSION:-dev}`, so they match; anything else is stored as `unknown`.
- **Staff**: `/auth/me/` now returns a read-only `is_staff`. The sidebar/drawer "Feedback" link and the page are for `is_staff` only; the
  link is a convenience, the API still answers 403 to everyone else and the page shows that as a message.
- **Inbox** `/dashboard/feedback` (`FeedbackInboxPage.jsx`): newest first, status and category filters, 20 per page, status changed with
  `PATCH {status}`. Loading, empty, error (with Try again), 403 and 429 each have their own message. Every user-written value is rendered as
  React text (never `innerHTML`). The staff bell notification opens this page.
