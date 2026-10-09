# KYAPTURE staff area (chunk 7.5-A)

Users list, suspend / reactivate, and the staff audit log. Staff is Django `is_staff` and nothing else: no new role,
no new permission table. Code: `backend/apps/users/staff_api.py`, `audit.py`, `models.py::StaffAuditLog`;
UI: `frontend/src/pages/dashboard/StaffUsersPage.jsx`, `StaffAuditPage.jsx`.

## 1. What existed before (audit of staff / admin)

| Surface | Guard before 7.5-A | Note |
|---|---|---|
| Django admin `/admin/` | `is_staff`, login lock since 7-B | no audit of who changed what beyond Django's own `LogEntry` |
| Feedback inbox `GET/PATCH /feedback/inbox/` | `IsStaffUser` (private class in `feedback_api.py`) | moved to `apps/core/permissions.py`, same behaviour |
| Manual payments `GET .../admin/payments/`, `POST .../payments/{id}/review/` | DRF `IsAdminUser` (= `is_staff`) | staff list and review were not audited. **Replaced in 7.5-B** by `/staff/payments/...` ([KYAPTURE_PAYMENTS.md](KYAPTURE_PAYMENTS.md)) |
| `GET .../subscriptions/payments/` as staff | `is_staff` branch of a user endpoint | global queue with receipt URLs, not audited |
| Deactivating a user | Django admin tick box (`is_active`) | tokens stopped (refresh refused), but the owner's **published galleries stayed public** (debt row 131) |
| Users list, suspend, audit log | none | built here |

## 2. Endpoints (all under `/api/v1/staff/`, all `IsStaffUser`: 401 anonymous, 403 anyone who is not staff)

| Route | What |
|---|---|
| `GET users/?q=&plan=&status=&storage=&sort=&page=` | Page of 25 (max 100). `q` is ONE complete email address (case-insensitive exact match; anything else is `400 invalid_email_query`, `%` and `_` are literal). `plan` = a plan key, `status` = `active`/`suspended`, `storage` = `empty`/`near_full` (80%+ of the plan limit)/`full`, `sort` = `joined`/`storage`/`email`. |
| `POST users/{id}/suspend/` `{reason}` | 200 with the updated row. 404 unknown, 403 `cannot_change_self` / `cannot_change_staff`, 409 `already_suspended`, 400 `reason_required` / `reason_too_long`. |
| `POST users/{id}/reactivate/` `{reason}` | Same checks; 409 `not_suspended`. |
| `GET audit/?action=&page=` | Read only. No POST/PUT/PATCH/DELETE route exists (405). |

Throttles (per staff user id, shared Redis cache): `staff_list` 60/minute (users list and audit log), `staff_action` 30/hour
(suspend and reactivate). There is no export route.

A user row carries exactly: `id, email, name, plan, plan_name, storage_used_bytes, storage_limit_bytes, collection_count,
joined, last_login, status, suspended_at, suspension_reason, is_staff`. The query uses `.only()` on those columns, so the
password hash, `token_version`, avatar and every other column is never selected (test: the SQL contains no
`"users"."password"`). No PIN, unlock token, gallery password, download token or storage key is reachable from any staff
route. `storage_used_bytes` is a plain int (64-bit sum cast); `last_login` is set by a real sign-in (it was never set before).

## 3. Suspend and reactivate

A suspension is `User.is_active = False` plus `suspended_at` / `suspension_reason` (staff-typed plain text, 1-300
characters, control characters and line breaks folded to spaces, stored and returned as text, rendered escaped by React).
One flag, so every existing check already reads it.

On suspend, in one transaction with its audit row:
1. `is_active=False`, reason stored;
2. `revoke_all_sessions(user)`: `token_version` is bumped (every access AND refresh token, cookie or bearer, is refused on
   its next use), outstanding refresh tokens are blacklisted, pending reset links are deleted;
3. the owner's galleries are queued for the 7-B public-media rotation (new random keys, old public derivative URLs stop
   resolving at the storage);
4. the audit row is written. If the audit write fails the whole suspension rolls back.

A suspended account cannot sign in (a wrong password still says "Invalid email or password"; only someone who typed the
right password is told the account is suspended). Staff cannot suspend themselves or another staff/superuser, and cannot
reactivate a staff account from here (staff accounts are managed in Django admin).

Reactivation sets `is_active=True`, clears the reason and writes its audit row. Old tokens stay dead (the owner signs in
again); the galleries, the visitors' unlock sessions, download tokens, ZIP ready links and file links work again unchanged
because a suspension deletes nothing.

Switching `is_active` in Django admin is treated the same way (tokens revoked, audit row `reason="django admin"`).

## 4. Every public path (debt row 131)

The 10 public gallery lookups in `apps/clients/views.py` all require `photographer__is_active=True`, next to the existing
published / active / not-expired / username checks. A suspended owner's visitor gets the plain `404 Gallery not found.`:

gallery payload, photo pages, unlock, favorites (GET/POST/DELETE), favorite lists and a single list, video playback,
single-photo download, download access, preparing a ZIP, the job-status poll (by link key and by download token), the ZIP
file link, the download job grant. The portfolio already excluded inactive accounts.

Background work: a PREPARING ZIP job whose owner is suspended before the worker reaches it ends as
`failed / owner_unavailable` (no ZIP is built); the "photos are ready" email is skipped for a suspended owner and goes out
normally after reactivation. Tests: `apps/clients/tests/test_suspended_owner_7_5a.py` (one test per path, each proves
200 -> 404 -> 200 through the real staff endpoints; 15 of the 19 fail on the code from before the change).

## 5. The audit log

`staff_audit_log`: `id, created_at, action, actor_id, actor_email, target_id, target_email, ip, reason`. Users are plain ids
plus an email snapshot, not foreign keys, so deleting an account neither cascades into nor rewrites its history.

| Action | Written by | Reason |
|---|---|---|
| `account.suspend` / `account.reactivate` | the staff endpoints; Django admin `is_active` change | staff text / `django admin` |
| `staff.user_list` / `staff.user_lookup` | users list (every page; a lookup names the account found, or none) | the filters used / `found` / `not found` |
| `staff.audit_view` | audit list | the action filter |
| `staff.inbox_view` | feedback inbox, payment queues | `feedback` / `payments` |
| `staff.feedback_status` | feedback PATCH | `status=<new>` |
| `staff.payment_review` | (7.5-A rows only; 7.5-B writes the three below) | `approve` / `reject` |
| `payment.submit` | a user submitting a manual payment | `payment=<id> plan=<key> amount=<n> NPR` |
| `payment.approve` / `payment.reject` | staff, in the review transaction | the same summary |
| `payment.proof_view` | staff opening a payment proof (minting its link) | the same summary |
| `subscription.downgrade` | the daily lifecycle job (7.5-C): no actor, the account is the target | `plan=<key> period_end=<date> grace_days=<n>` (+ ` silent=old` for a very old lapse) |
| `security.password_change` | change-password serializer; Django admin password form | `self` / `admin` |
| `security.password_reset` | reset-confirm view (completion) | `reset` |
| `security.login_lockout` | Django-admin login lock (`apps/core/admin_login.py`); account login throttle (`LoginAccountRateThrottle`, once per window) | `admin_ip` / `admin_account` / `account_rate` |
| `security.gallery_lockout` | `post_save` signal on the lockout's own SECURITY notification (`apps/clients/lockout.py` is unchanged) | `pin` / `password` / `email_code` |

Security events use `record_event` (a failed write is logged and swallowed, so the audit can never break a sign-in or a
reset). Staff actions use `record` inside the action's transaction (fail closed: no row, no change, no data).

IP: `apps.core.request_ip.client_ip` only, i.e. DRF's `get_ident` with `NUM_PROXIES` (7-B). A spoofed `X-Forwarded-For`
never reaches a row (tests with `NUM_PROXIES` 0 and 1). The gallery-lockout row has no address (the pause is the sum of
many visitors). A row never holds a password, PIN, code, token, link or hash; typed addresses that are not accounts are
never stored (tests grep the whole table).

Append only, three layers: the model and its queryset refuse `save` of an existing row, `update`, `bulk_update` and
`delete` (`AuditLogImmutable`); the Django admin shows it with no add/change/delete permission and no actions; on PostgreSQL
a trigger (`users.0010`) raises on any `UPDATE` or `DELETE`. A future retention purge (debt row 98) needs a migration that
drops or relaxes that trigger on purpose.

## 6. UI

`/dashboard/staff/users` (search by full email, filters plan / status / storage / sort, paginated table on desktop and
stacked list at 390 px, Suspend / Reactivate dialog with a required reason and counter) and `/dashboard/staff/audit`
(action filter, read-only table / list). Both are listed under "Staff" in the sidebar for `is_staff` accounts only; a
normal user who opens the URL sees "Staff only" and no request is made (the server would answer 403 anyway). The success
toast appears only after the API answered 200.

## 7. Operations

- Migration `users.0010` (two `User` columns, the audit table, the trigger) was applied to the Docker dev DB only; the host
  dev DB and production are not migrated (debt row 163).
- The staff area needs no new setting. Rates: `staff_list`, `staff_action` in `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`.
- The Celery worker must be restarted with the web process (the ZIP task and ready-email task changed).

## 8. Evidence

- Backend: `apps/users/tests/test_staff_7_5a.py` (47 tests: 401/403 on every route, allowlisted fields, exact-email search,
  pagination and throttles, suspend / reactivate rules, token revocation, the audit row and its IP, append-only at the ORM,
  admin and database, password / reset / lockout events) and `apps/clients/tests/test_suspended_owner_7_5a.py` (19 tests, one
  per public path, 200 -> 404 -> 200). Full suite on a fresh test database (no `--keepdb`, Redis cache db 3): **1506 tests,
  OK** (27 min).
- Frontend: `npm test` 141 / 141 (7 of them are `staffFlow.test.js`); `vite build` and the Docker frontend image build.
- Browser: [qa-7-5a/results.md](qa-7-5a/results.md), 41 / 41 checks at desktop and 390 px.
- Measured: the users list over 3,004 accounts answers in 14-83 ms median (page 1: 60 ms), results.md section 5.
- Debt: row 131 DONE; new rows 162-168.

