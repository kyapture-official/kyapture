# 7.5-A QA results (staff area: users list, suspend, audit log)

Run: 2026-10-08 against the Docker stack (app :3000, API :8000, real Celery worker), Chrome headless via puppeteer-core.
Script: `qa-script.mjs` (41 checks, **41 / 41 pass**). It creates 3 accounts and 1 gallery with run-specific emails
(`qa75a-{staff,owner,normal}-<stamp>@example.invalid`), uploads one real photo through the upload endpoint and the worker,
prints the rows it will delete and deletes exactly those 3 users (cascade: the gallery, the photo) plus the owner's media
folder. Audit rows are append-only and stay in the dev DB (they name the deleted QA accounts).

## 1. Staff flow (desktop 1280 and 390 px)

| Check | Result |
|---|---|
| Sidebar lists Users and Audit log for a staff account; not for a normal user | pass |
| Users list loads; search by a fragment shows an inline error and sends no request | pass |
| Exact email finds exactly one account: name, email, plan Free, "25.2 KB of 3.00 GB", 1 collection, Active | pass |
| The staff member's own row shows "Staff account" and no Suspend button | pass |
| Suspend with an empty reason: refused in the dialog, no request; with a reason: toast only after the API answered | pass |
| Row reads Suspended with the typed reason as literal text (`<b>bold</b> chargeback & spam`); no `<b>` element | pass |
| 390 px: no horizontal scroll on the users page and the audit page | pass |
| Reactivate through the UI: row Active again | pass |
| Audit page lists "Suspended an account" and "Reactivated an account" with actor, target, address (172.18.0.1, the Docker gateway = the peer), reason; no edit/delete control; the action filter narrows the log | pass |

Screenshots: `desktop-users-list.png`, `desktop-suspend-dialog.png`, `desktop-users-suspended.png`,
`mobile-users-suspended.png`, `desktop-audit.png`, `mobile-audit.png`, `desktop-normal-user-denied.png`,
`mobile-visitor-suspended.png`, `mobile-visitor-reactivated.png`.

## 2. What the suspension did (real stack)

| Check | Result |
|---|---|
| The owner's existing session (cookies) answers 401 on its next request | pass |
| The suspended owner's sign-in answers 400 "This account has been suspended. Contact support." | pass |
| Public gallery API: plain 404; a visitor's phone-width page shows "Gallery not found" | pass |
| The 3 public media URLs (200 before) answer 404 once the rotation task ran | pass |
| After reactivation: the public gallery is 200 again, the 3 NEW media URLs in its payload load (200), the visitor page shows the gallery | pass |
| The pre-suspension session stays dead after reactivation; a fresh sign-in works | pass |

## 3. A normal user

At `/dashboard/staff/users` and `/dashboard/staff/audit` the page shows "Staff only" and made **0** requests to
`/api/v1/staff/`; called directly with that user's cookies, `GET /staff/users/`, `GET /staff/audit/` and
`POST /staff/users/{id}/suspend/` all answered **403**, and the target stayed active.

## 4. Audit rows written by the run (for the owner)

`staff.user_lookup` x2 (found), `account.suspend` (reason = the typed text, address present), `account.reactivate`
("Appeal accepted", address present): exactly one suspend and one reactivate row for the owner.

## 5. Measured: users list over 3,004 accounts

Dev PostgreSQL, 3,000 galleries and 6,000 assets inserted inside a transaction that was rolled back (0 rows left behind);
the view called in-process, median of 7 calls, includes the audit insert and JSON rendering.

| Request | median | max |
|---|---|---|
| page 1, no filter | 60 ms | 167 ms |
| page 40 | 56 ms | 62 ms |
| `status=suspended` | 14 ms | 15 ms |
| `plan=pro` | 14 ms | 16 ms |
| `storage=near_full` (2,025 matches) | 83 ms | 95 ms |
| `sort=storage` | 63 ms | 68 ms |
| exact email | 18 ms | 72 ms |

Production-size hardware and a production-size table are not measured (debt row 163 / 15-B).

## 6. Not covered by the browser run

The suspend path through Django admin's `is_active` box (covered by `test_switching_an_account_off_in_django_admin_is_a_suspension`),
login-lockout and password-reset audit rows (covered by `SecurityEventTests`), and every public route other than the
gallery payload and media (covered one by one in `test_suspended_owner_7_5a.py`).
