# KYAPTURE transactional email (chunk 7.5-D)

One shared base and one registry for every email the app sends. Code: `backend/apps/core/emailing.py`; templates:
`backend/apps/core/templates/emails/` (`base.html`, `base.txt`, `_button.html` and one `<key>.html` + `<key>.txt` per email).
Tests: `backend/apps/core/tests/test_emailing_7_5d.py`. Browser/Mailpit evidence: [qa-7-5d/results.md](qa-7-5d/results.md).

## 1. The audit (what sent mail before this chunk)

| # | Email | To | Template before | Sent by |
|---|---|---|---|---|
| 1 | Download ready | client visitor | `clients/emails/download_ready.{html,txt}` | Celery `send_download_ready_email` -> `ready_email.py` (`EmailMultiAlternatives`); subject held the gallery title |
| 2 | Download code (7-B) | listed contact | none (inline string) | `download_access.send_email_code`, **in the request**, `send_mail`; the 6-digit code was in the subject |
| 3 | Password reset (7-C) | account | `users/emails/password_reset_email.*` | Celery `send_password_reset_email_task` -> `send_mail` |
| 4 | Password changed (7-C) | account | `users/emails/password_changed_email.*` | Celery `send_password_changed_email_task` -> `send_mail` |
| 5 | New download | photographer | none (plain text in `notifications.py`) | Celery `send_notification_email`; subject held the gallery title |
| 6 | New favorite | photographer | none | same |
| 7 | Payment approved (7.5-B) | payer | none | same; subject held the plan name; "runs until" was the UTC date |
| 8 | Payment rejected (7.5-B) | payer | none | same; subject held the plan name |
| 9 | Plan expiring (7.5-C placeholder) | owner | none (`lifecycle.reminder_text`) | the daily job, `send_mail` inline; subject held plan name and days |
| 10 | Plan ended (7.5-C placeholder) | owner | none (`lifecycle.downgrade_text`) | the daily job, `send_mail` inline |

Nothing else called `send_mail`, `EmailMessage`, `EmailMultiAlternatives` or `mail_admins` (a test now scans the source for it).
Share-by-email (debt row 9) is a frontend `mailto:` link: the server sends nothing, so there is no abuse surface.

## 2. The registry (`EMAILS`)

| Key | Fixed subject | Footer settings link | Sent by | Follows |
|---|---|---|---|---|
| `download_ready` | Your photos are ready for download | no | Celery `send_download_ready_email` | per-address / IP / gallery hourly caps |
| `download_code` | Your Kyapture download code | no | in the request (`safe_send_email`) | send caps (10 min and 24 h) |
| `password_reset` | Reset your Kyapture password | no | Celery | always |
| `password_changed` | Your Kyapture password was changed | no | Celery | always |
| `notify_download` | New download from one of your collections | yes | Celery `send_notification_email` | "Downloads" preference, 15 min per collection |
| `notify_favorite` | New favorite in one of your collections | yes | same | "Favorites" preference, 15 min per collection |
| `payment_received` (new) | We received your payment | yes | same | "Payments" preference |
| `payment_approved` | Your payment was approved | yes | same | "Payments" preference |
| `payment_rejected` | Your payment could not be approved | yes | same | "Payments" preference |
| `plan_expiring` (was a placeholder) | Your Kyapture plan is ending soon | yes | the daily job (claim, send after commit, release on failure) | "Payments" preference |
| `plan_ended` (was a placeholder) | Your Kyapture plan has ended | yes | same | "Payments" preference |
| `staff_payment_alert` (new) | New payment to review | no | Celery `send_staff_alert_email` | `STAFF_ALERT_EMAIL` set |

There is no notification-preference system or unsubscribe list in this chunk; the existing three preferences (Settings >
Notifications) keep deciding what they decided. Welcome and alert emails are not built (skipped by the task).

## 3. Rules and where they are enforced

* **Subject.** A fixed string in `EMAILS`; `send_email` and `render_email` take no subject argument, so no user text, name, plan
  name, reason, code or token can reach a header. Tests: regex over all subjects, hostile context on every email, signature check.
* **Values.** `clean_context` folds every string of the context to one line (control characters, CR, LF, tab, NUL and the Unicode
  line separators become spaces) and the template engine HTML-escapes it. The text part is rendered with autoescape off because it
  is `text/plain`. A name like `<script>` is `&lt;script&gt;` in HTML; a CRLF in a rejection reason is one line in both parts and
  cannot add a header (`Bcc` stays empty).
* **Links.** `app_url(path)` = `settings.FRONTEND_URL` + path (it raises when FRONTEND_URL is not an absolute http(s) URL, so a
  misconfigured worker fails loudly instead of mailing a dead link). The Host header of a request is never read. The existing helpers
  are reused: `reset_link`, `build_gallery_share_url`, `job_page_url`. The password-reset token is in the `#fragment`
  (`/reset-password#token=...`), as 7-C built it.
* **Remote content.** None: no `<img>`, no web font, no `@import`, no `url()`, no script, no tracking pixel; the wordmark is text.
  Every absolute URL in an email is a link to the app or a `mailto:`. The mail is fully readable with images off.
* **Layout.** One table card, `max-width: 600px`, system font stack, `color-scheme: light dark` with `prefers-color-scheme: dark`
  rules (plus Outlook `data-ogs*` rules), a mobile rule at 620 px (22 px side padding). A plain-text twin for every email.
* **Sender.** `DEFAULT_FROM_EMAIL` (required in production). **Reply-To** `EMAIL_REPLY_TO`, else `SUPPORT_EMAIL`. The one exception
  is "your photos are ready": From is `"<studio name>" <the platform address>` and Reply-To is the photographer (the email says
  "Questions? Reply to this email."); the studio name is folded to one line.
* **Dates.** Shown in `BILLING_TIME_ZONE` (Asia/Kathmandu) by `format_date` / `format_datetime`, the same zone the lifecycle counts
  days in. This fixed two old dates: "runs until" (it printed the UTC date) and the password-changed time (it printed UTC).
* **Failure.** Every send is a Celery task (or the lifecycle job) except the download code. `send_email` raises so the task retries
  (3 times) and the lifecycle job releases its claim; the request that triggered the mail is never failed: every builder is wrapped
  (`_never_raises`), every `.delay` is in a try/except, every dispatch runs after the transaction commits, and a log line names the
  exception type only (no trace, no address, no link).
* **The download code stays in the request on purpose.** The visitor is told "we could not send your code" (503) when the send
  fails, and the code is a secret that should not travel through the Celery broker as a task argument (it would sit in Redis).
  It uses `safe_send_email`, so a failure is an answer, not a 500. (Debt row 136 stays: a slow mail provider delays that form.)

## 4. Settings (all env; nothing hard-coded)

| Setting | Meaning | Default |
|---|---|---|
| `DEFAULT_FROM_EMAIL` | sender (existing) | `Kyapture <no-reply@kyapture.com>`; production refuses to boot without it |
| `SUPPORT_EMAIL` | printed in every footer; the default Reply-To | `support@kyapture.com`; **production refuses to boot without it** |
| `EMAIL_REPLY_TO` | Reply-To override | empty = `SUPPORT_EMAIL` |
| `STAFF_ALERT_EMAIL` | the one address told "new payment to review" | empty = no staff email (the staff bell still works). Compose sets a dev catcher address |
| `FRONTEND_URL` | origin of every link (existing) | dev `http://localhost:5173`; compose `http://localhost:3000`; production `https://app.kyapture.com` |
| `BILLING_TIME_ZONE` | zone of every date (existing) | `Asia/Kathmandu` |

## 5. The new and the reworded emails

* **Payment received** goes to the payer after the payment row commits (plan, amount, link to Billing; never the reference).
* **Staff alert** goes to `STAFF_ALERT_EMAIL` after commit and carries the payment id, the plan, the amount and the staff page
  link, nothing else: no proof link, no reference, no notes, no user (test greps the body for each). It is not held back by the
  payer's preference. It has no throttle of its own: one mail per submitted payment, and a payer can hold at most
  `MANUAL_PAYMENT_MAX_PENDING` pending payments.
* **Plan expiring** is sent `reminder_days` before the end: "Your plan ends on <date>" (the date in Kathmandu).
* **Plan ended** says the plan HAS ended, the account is on the Free plan, files, galleries and settings are kept, and renewing
  restores the paid features. Neither mail mentions a grace period (access ends at the end date; the grace only delays this
  paperwork, debt row 182). A test fails if any email contains the word "grace".

## 6. Deploy notes

* Restart the Celery worker with the web process: `send_notification_email` now takes `(user_id, kind, template, context)` and there
  is a new `send_staff_alert_email` task. A message queued by the old code (`subject`, `body`) is dropped with one log line, not retried.
* Production needs `SUPPORT_EMAIL` (and `STAFF_ALERT_EMAIL` if staff should get the alert).
