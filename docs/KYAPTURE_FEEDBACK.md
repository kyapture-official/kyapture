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
- Limits: subject 120 chars (one line), message 4000, route 200. Text is trimmed; empty text is a 400. Unknown body fields are ignored.
- Auto-captured: `route` (path only: query string and fragment dropped, UUID/long-token segments masked), `gallery_slug`
  (slug-shaped or dropped), `app_version` (kept only if it equals `settings.APP_VERSION` or is in
  `FEEDBACK_ACCEPTED_APP_VERSIONS`, else `unknown`), `browser_class` (read from the User-Agent header into
  chrome/edge/firefox/safari/opera/other; a body value is ignored). Tokens, cookies, signed URLs, PINs and IPs are never stored.
- Text is stored and returned as plain JSON, never marked safe. The inbox UI (6.3-B) must render it escaped.
- **No attachments**: the model has no file field and the API accepts none.
- A new feedback creates one `Notification` (kind `feedback`) per active staff account, shown in the existing bell.
  No email, no websocket.
