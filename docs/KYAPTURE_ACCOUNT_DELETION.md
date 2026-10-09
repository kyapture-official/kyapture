# KYAPTURE account deletion, no data export (chunk 7.5-E)

An owner can delete their own account. The account waits through a cooling-off period, then an owner-less Celery job deletes
every file and every row. Code: `backend/apps/users/account_deletion.py` (every rule), `account_api.py` (the five routes),
`tasks.py` (the Celery tasks), `ownership.py` (the one "is this owner public" rule); UI: `frontend/src/components/settings/DeleteAccountCard.jsx`
(Settings > Account), `frontend/src/pages/auth/PendingDeletionPage.jsx`, `CancelDeletionLinkPage.jsx`.
Evidence: section 10 and [qa-7-5e/results.md](qa-7-5e/results.md).

## 1. What existed before (audit)

| Surface | Before 7.5-E | Now |
|---|---|---|
| Account deletion | none. The Account page said "Account deletion isn't available in the app yet". Django admin could delete a user (cascade) | the flow below. The admin delete still works and now also anonymises payments (`pre_delete` signal) |
| 5.1-D purge (`apps/photos/purge.py`) | `purge_assets`, `purge_photo_set`, `purge_gallery`: rows deleted in a transaction, files deleted AFTER commit by one idempotent Celery task (`purge_storage_objects`, retried with backoff, anything left is logged for `purge_orphans`) | reused: `asset_refs`, `web_size_prefix`, `gallery_prefix`, `run_purge`, `delete_prefix`. The account job needs the opposite order (files first, rows only when the files are gone), so it calls `run_purge` itself and wraps the row delete in the new `discarding_purges()` so the post-delete signal queues no second purge |
| Suspension (7.5-A) | `is_active=False` + `revoke_all_sessions` + 7-B public-key rotation; ten public lookups require `photographer__is_active=True` | reused. A closing account must still be able to sign in and cancel, so it is NOT `is_active=False`: one shared filter (`ownership.PUBLIC_OWNER`) now says "active AND no deletion waiting" and replaces the literal in all ten lookups, the portfolio, the ZIP job and the ready email. The rotation (`close_public_media`) and `revoke_all_sessions` are called as they are |
| Purge command | `purge_orphans` (dry-run by default; skips objects younger than 60 minutes) | used as the proof (`--dry-run --min-age-minutes 0`). Finding: it does not know the cached Web Size files and lists them as orphans: debt row 194 |
| Celery | one `celery_worker`, one `celery_websize`, ONE `celery_beat` (docker-compose); beat schedule = `CELERY_BEAT_SCHEDULE` in settings (7.5-C) | one new named beat entry `account-deletion-sweep` (every 15 minutes) and four tasks |
| Audit log (7.5-A) | `staff_audit_log`: plain `actor_id` / `target_id` UUIDs and email snapshots, no foreign key; append-only by model, admin and a Postgres trigger | unchanged. Three new actions; section 7 for what its rows keep |
| Email (7.5-D) | one registry `EMAILS`, fixed subjects, one base | three new entries on the same base |

### Every model that points at the user

| Model | Field | On delete | What the purge does |
|---|---|---|---|
| `galleries.Gallery` | `photographer` | CASCADE | collections are emptied and deleted by the job (files first); everything below hangs off a gallery |
| `photos.MediaAsset`, `PhotoSet` | via gallery | CASCADE | assets: files then rows in batches; sets with the gallery |
| `clients.ClientSession`, `FavoriteList`, `Favorite`, `DownloadLog`, `DownloadJob` | via gallery | CASCADE | gone with the gallery (visitor data: favorites, unlock sessions, download requests and logs, ZIP rows) |
| `users.Notification`, `Feedback`, `PasswordResetToken` | `user` | CASCADE | deleted with the user row |
| `subscriptions.UserSubscription` | `user` (one to one) | CASCADE | set to `cancelled`, then deleted with the user row |
| `subscriptions.ManualPayment` | `user` | **SET_NULL** (was CASCADE) | approved: kept anonymised; others deleted (section 6) |
| `subscriptions.ManualPayment` | `verified_by` | SET_NULL | staff reviewer; staff cannot be deleted here |
| `token_blacklist.OutstandingToken` | `user` | SET_NULL | deleted explicitly (and their blacklist rows) |
| `admin.LogEntry` | `user` | CASCADE | staff only |
| `users.StaffAuditLog` | none | no foreign key | rows stay (section 7) |

### Where each kind of file lives

| File | Storage | Key |
|---|---|---|
| originals, Download Masters | private | `photographers/<user>/galleries/<gallery>/(photos|videos)/<asset>_<random>_original.* / _download.*` |
| display / medium / thumbnail WebP, video poster, preview, playback MP4 | public | `photographers/<user>/galleries/<gallery>/[<media_token>/](photos|thumbnails|videos)/<asset>_*` |
| cached Web Sizes | private | `photographers/<user>/galleries/<gallery>/web_size/<asset>/<px>-<wm>-<src>.jpg` |
| prepared ZIPs | private | `download_jobs/<job>/<name>.zip` (paths in `DownloadJob.files`) |
| avatar, branding logo | public | `photographers/<user>/profile/avatar_*`, `photographers/<user>/branding/logo_*` |
| payment proofs | private | `payment_proofs/<user>/<payment>.<ext>` |
| payment QR | public | `payment_instructions/qr_*`: the platform's, not an account's, so never deleted here |

## 2. What is deleted and what is kept (the page says exactly this)

**Deleted, permanently:** every collection, set, photo and video with its original, Download Master, previews and cached sizes;
prepared ZIPs; what visitors left on the collections (favorite lists, unlock sessions, download requests, download activity); the
profile, avatar, logo, branding, settings, notifications and feedback messages; the subscription (cancelled); rejected payments and
every payment proof file; the sign-in itself. There is **no data export**.

**Kept:**
* Approved payments: amount, currency, date, plan, transaction reference and the granted period stay as a financial record. The user
  link is removed, the email is replaced by an HMAC (`payer_hash`), the typed note and the proof file are deleted.
* The deletion trail in the staff audit log (section 7).
* Older audit rows written before this chunk keep what they always kept (section 7).

## 3. The life of a deletion

1. **Request** (`POST /auth/account/deletion/request/`): password (an account with no password uses an emailed 6-digit code,
   10 minutes, 5 tries) and the typed account email. Refused for staff (403), while a payment is PENDING (409, says why), when one is
   already waiting (409). On success, in one transaction under the user's row lock: the dates are stamped, every session ends
   (`revoke_all_sessions`: `token_version`), the public derivative keys rotate (the 7.5-A door), the audit row is written and the
   "deletion requested" email is queued after commit. This browser's cookies are cleared.
2. **Waiting** (`AccountSettings.deletion_cooling_off_days`, admin: Users > Account settings, default 7, 0 to 90):
   * galleries answer 404, a ZIP being built fails `owner_unavailable`, the ready email is skipped (all through `ownership.PUBLIC_OWNER`);
   * the API refuses every authenticated route with `403 account_pending_deletion` except `GET /auth/me/`, the status, cancel and sign-out;
     uploads and manual-payment submissions also refuse under the user's row lock;
   * billing stops: the daily lifecycle job skips the account (no reminder, no downgrade, no mail, no audit row) and no payment can be sent;
   * a sign-in works and shows the "Cancel deletion" page; the emailed link does the same without signing in.
3. **Cancel** (`POST .../cancel/` signed in, or `POST .../cancel-link/ {token}`): under the row lock the status is re-read; the stamps are
   cleared and everything is back (nothing had been deleted). Impossible once the purge started (409 `purge_started`).
4. **Purge**: section 4.

With 0 days the purge is queued at once, no cancel link is sent, and nothing can be cancelled.

### The cancel link

`{FRONTEND_URL}/cancel-deletion#token=<43 url-safe chars>`: in the fragment like the reset link (no server, log or Referer sees it), read once,
wiped from the address bar, sent in a POST body. Only its SHA-256 is stored (`User.deletion_cancel_hash`); the token is made inside the
email task, never passed through the broker, and each resend replaces the previous one. The link dies when the deletion is cancelled or the
purge starts. Opening the page changes nothing: the button does.

## 4. The purge job

`purge_account(user_id)` (Celery, no request, no session): runs `run_purge_steps`, which takes a per-account cache lock and calls
`purge_step` up to 25 times; if there is more it re-queues itself, if a file could not be deleted it retries with backoff (up to 8 times,
then the beat sweep resumes it). Each `purge_step` is one bounded unit and starts with the status check under the row lock:

| Stage | Work | Rows go only after |
|---|---|---|
| begin | lock the user row; stop if never requested / cancelled / not due; stamp `deletion_started_at`, clear the cancel hash, `is_active=False`, `revoke_all_sessions` | |
| assets | up to `ACCOUNT_PURGE_BATCH_ASSETS` (200) photos/videos: `asset_refs` + cached Web Size prefix through `run_purge` | their files are deleted |
| collection | a collection with no photo left: its key prefix in both storages and each ZIP's folder | its files are deleted |
| finish | `photographers/<user>/` in both storages, `payment_proofs/<user>/`; then ONE transaction: re-check the status under the lock, anonymise payments, delete token rows, cancel the subscription, write the audit row, delete the user (cascade), queue the farewell email | the files are deleted |

A failed file delete leaves its rows in place and ends the step with `retry`; running again resumes from the remaining rows. Every stage is idempotent
(a missing file counts as deleted, an empty batch is skipped), two runners are turned away by the cache lock and, if they both got through, by the row
locks (tests with real threads). The beat sweep (`account-deletion-sweep`, every 15 minutes) starts accounts whose cooling-off ended and resumes
purges nobody touched for 30 minutes.

**Races.** The request, the cancel, the purge start and the final step all take `FOR NO KEY UPDATE` on the user row and re-read the status inside it.
Uploads and manual-payment submissions take the same lock and refuse a closing account, so an upload that started before the request cannot add
rows. An upload that is still streaming when the purge begins fails at commit (its gallery is gone). Its stored file can outlive the purge by that one
request; `purge_orphans` finds it (the 11-D schedule will remove it, debt row 19). A rotation task queued by the request (7-B) finishes in seconds,
long before a normal 7-day purge; with 0 days the request skips the rotation so nothing races the purge.

## 5. Endpoints (all under `/api/v1/auth/account/deletion/`, no id in any route)

| Route | Auth | Throttle | What |
|---|---|---|---|
| `GET /` | signed in | default | `{state, requested_at, scheduled_for, cooling_off_days, uses_password, is_staff, blockers[]}` |
| `POST code/` | signed in | `account_deletion_code` 3/h per user | emails the one-time code (accounts with no password only; 503 when the mail fails) |
| `POST request/` | signed in | `account_deletion` 5/h per user | `{password | code, email}` |
| `POST cancel/` | signed in | `account_deletion_cancel` 10/h per user | cancel by the owner |
| `POST cancel-link/` | none | `account_deletion_cancel_link` 10/h per client address (trusted-proxy aware, 7-B) | `{token}` |

Error codes (all `{error, code}`): `password_required`, `password_wrong`, `code_invalid`, `email_mismatch`, `staff_cannot_delete` (403),
`payment_pending` (409), `already_pending` (409), `not_pending` (409), `purge_started` (409), `cancel_link_invalid`, `email_failed` (503).
`GET /auth/me/` gains `deletion: null | {requested_at, scheduled_for}`.

## 6. Payments

An **approved** `ManualPayment` is kept: `user` becomes NULL (`SET_NULL`, was CASCADE), `payer_hash` = HMAC-SHA256 (Django `salted_hmac`, key derived from `SECRET_KEY`,
salt `kyapture.account-deletion.payer`) of the lower-cased email, `notes`, `payment_proof`, `proof_type`, `proof_size` are cleared and the proof FILE is deleted.
`amount`, `currency`, `plan_price`, `plan`, `reference`, `status`, `period_start`, `period_end`, `reviewed_at`, `verified_by` and `created_at` stay.
A **rejected** payment (or a pending one that slipped in) is deleted with its proof. A pending payment blocks the request, so none normally exists.
The hash is a pseudonym, not anonymity: someone who already knows an address can compute and confirm it; rotating `SECRET_KEY` changes the hash of rows written afterwards
(`SECRET_KEY_FALLBACKS` does not apply to it). The staff payment queue shows an anonymised row as "Deleted account".

## 7. The audit trail and the privacy policy (feeds 13-B)

`staff_audit_log` has **no foreign key** to the user (only the plain `actor_id` / `target_id` UUIDs): deleting an account neither cascades into nor changes the log;
the append-only layers (model, admin, Postgres trigger `users.0010`) are untouched. Tests: the table has no relation (`introspection.get_relations`), and a user with
suspend/reactivate rows is deleted with the rows byte-identical afterwards.

**Written by this chunk** (`account.deletion_requested`, `account.deletion_cancelled`, `account.deletion_completed`): the account id (as actor and target), a masked
address (`k***@gmail.com`), a coarse reason (`requested`, `requested_now`, `cancelled`, `cancelled_by_link`, `completed`) and the time. No name, no full address, no IP.

**Personal data the log keeps after the account is deleted:**

| Rows | Personal data | For how long |
|---|---|---|
| the three deletion rows | account id, masked address, dates | indefinitely |
| rows written before this chunk and by other flows: `account.suspend/reactivate`, `staff.user_lookup`, `payment.submit/approve/reject/proof_view`, `security.password_change/reset`, `security.login_lockout` (account), `subscription.downgrade` | the full email address of the actor and/or target, the client IP address of the request (`ip`), and for a suspension the reason a staff member typed | indefinitely: the log is append-only (trigger) and **no retention rule exists yet** |

Nothing deletes or rewrites these rows. Deciding a retention period (and the migration that relaxes the trigger to apply it) is an owner decision: debt row 193 (13-B / 13-C).
Other personal data outside this chunk's reach: Django admin `LogEntry` (staff only), web-server and proxy access logs (14-A/16-A), mail-provider logs, backups.

## 8. Emails (shared base, docs/KYAPTURE_EMAIL.md)

| Key | Fixed subject | When |
|---|---|---|
| `deletion_code` | Confirm deleting your Kyapture account | the code request of an account with no password (in the request, like the download code) |
| `deletion_requested` | Your Kyapture account is scheduled for deletion | once per request when the cooling-off is above 0, with the cancel link and the start date |
| `account_deleted` | Your Kyapture account was deleted | once, to the old address, queued by the transaction that deletes the user (a repeat run finds the user gone) |

The farewell task receives the address as its argument (the user row is gone): it sits in the broker until sent (at most 3 retries) and nowhere else.

## 9. Operations

* Migrations `users.0013` (four `User` columns, `AccountSettings` + its row, three audit actions) and `subscriptions.0015` (`ManualPayment.user` nullable + `SET_NULL`, `payer_hash`) were applied to the Docker dev DB only (debt row 192).
* Restart `celery_worker` and `celery_beat` after deploying (four tasks, one beat entry): `docker compose restart celery_worker celery_beat`.
* Settings: `ACCOUNT_PURGE_BATCH_ASSETS` (200), `ACCOUNT_DELETION_CODE_MINUTES` (10), `ACCOUNT_DELETION_CODE_MAX_TRIES` (5); throttle rates `account_deletion*`. The cooling-off is the admin row, not a setting.
* Run by hand: `from apps.users.account_deletion import run_purge_steps; run_purge_steps('<uuid>')` in `manage.py shell`.

## 10. Evidence

See the chunk report and [qa-7-5e/results.md](qa-7-5e/results.md). Tests: `apps/users/tests/test_account_deletion_7_5e.py`, `apps/clients/tests/test_deleting_owner_7_5e.py` (the 19 public-path tests of 7.5-A re-run for a deleting owner),
`frontend/src/utils/deletionFlow.test.js`.
