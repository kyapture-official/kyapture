# KYAPTURE manual payments (chunk 7.5-B)

A photographer pays by eSewa or bank transfer, reports the payment, staff approve or reject it, and the plan follows.
Code: `backend/apps/subscriptions/payments.py` (every rule), `staff_payments.py` (the staff API), `views.py` (the user API),
`models.py` (`ManualPayment`, `PaymentInstructions`); UI: `frontend/src/pages/subscription/BillingPage.jsx`,
`frontend/src/pages/dashboard/StaffPaymentsPage.jsx`.

## 1. What existed before (audit)

| Surface | Before 7.5-B | Now |
|---|---|---|
| Payment model | `ManualPayment` (user, plan, amount, receipt image, notes, status) | the same model; money and review fields added. **No second model.** |
| Submit | `POST /subscriptions/payments/`, image only (5 MB), one pending per plan | same URL; a transaction ID is required, image **or PDF**, pending cap, audit row, staff bell |
| Review | `IsAdminUser` view, no row lock, `admin_note` **overwrote the user's own note**, a hard-coded 30 days | `/staff/payments/...` under `IsStaffUser`, row lock, own-payment ban, audit, days from settings. The two old routes (`admin/payments/`, `payments/{id}/review/`) are **removed** (they bypassed the lock and the self-approve rule) |
| Django admin | `status` editable on `ManualPayment` (would skip the plan, the audit and the user) | `ManualPayment` is read-only there; `PaymentInstructions` is the one editable row |
| Receipt link for a user | a 1 h signed URL of their own receipt in `GET /payments/` | none: the user's list carries `has_proof` only. Staff open a proof through the signed link below |
| Expiry | `get_feature_entitlements` / `get_user_subscription_metrics` already require `expires_at > now` (debt row 43) | unchanged (tested at request time, section 6) |

## 2. The payment row

| Field | Meaning |
|---|---|
| `amount`, `currency` (`NPR`), `plan_price` | frozen at submission: `amount` must equal the plan price then, and `plan_price` keeps it. A later price edit changes nothing on a pending payment |
| `reference`, `reference_key` | the transaction ID as typed (trimmed) and its trimmed, lower-cased form |
| `payment_proof`, `proof_type`, `proof_size` | private file, the type sniffed from its bytes, 64-bit byte count |
| `status`, `verified_by`, `reviewed_at`, `rejection_reason` | the review result; the reason is plain text, at most 300 characters |
| `period_start`, `period_end` | set on approval: the period the plan was granted (= the subscription's `expires_at` after this payment) |

## 3. Rules (all server-side)

* **Reference.** 4-64 characters, letters, digits and `. _ / -` only. A database unique constraint on `reference_key`
  (`uniq_manual_pay_reference`) covers every payment except REJECTED ones (and rows from before 7.5-B, which have none). A
  rejected payment releases its reference; only the same user may submit it again (`check_reference`). The second submit gets
  `400 reference_taken` (or `reference_already_submitted` for your own); two accounts sending the same new reference in the
  same instant are separated by the constraint.
* **Proof.** PNG, JPEG, WEBP or PDF, judged by the bytes (Pillow for images, the `%PDF-` header for a PDF), at most
  `MANUAL_PAYMENT_PROOF_MAX_MB` (5) and `MANUAL_PAYMENT_PROOF_MAX_PIXELS`; the stored name is `payment_proofs/{user}/{payment}{ext}`
  with the extension from the sniffed type, in `PrivateMediaStorage`. A failed submit deletes the file it had stored.
* **Pending cap.** At most `MANUAL_PAYMENT_MAX_PENDING` (3) pending payments per user, one per plan, counted under the user's
  row lock so parallel submits cannot pass it. `payment_submit` throttle: 10 per hour per user.
* **Approve.** Locks the PAYMENT row (`select_for_update(no_key=True)`, the 7G lock), re-reads its status inside the lock and flips
  it once; then locks the user's row so two payments of one account are applied one after the other. The plan paid for
  (`payment.plan`, a row in the plan table) is applied for `MANUAL_PAYMENT_PERIOD_DAYS` (30): **from the current end date when the
  user is already on that plan and it is still live, otherwise from now.** `User.is_active_plan` is set, one audit row, a bell and
  an email. A repeat approve answers `200 {changed: false}` and changes, mails and logs nothing.
* **Reject.** Needs a reason (one line of plain text, 1-300 characters). The plan and the subscription are untouched; the user sees
  the reason on Billing and in the email. A repeat answers `changed: false`; a reject after an approve (and an approve after a
  reject) is `409` and changes nothing.
* **Staff cannot review their own payment** (`403 cannot_review_own`).
* **Entitlements.** Nothing here names a plan or a limit: the flags and limits are the `SubscriptionPlan` row's, read through
  `entitlements.py` / `get_user_subscription_metrics` only.

## 4. Endpoints

User (`IsAuthenticated`):

| Route | What |
|---|---|
| `GET /api/v1/subscriptions/payments/` | the user's OWN payments, newest first (allowlisted keys, no proof link, no reviewer) |
| `POST /api/v1/subscriptions/payments/` | multipart `plan`, `amount`, `reference`, `payment_proof`, `notes`; `201`, or `400 {error, code, errors}` |
| `GET /api/v1/subscriptions/payment-instructions/` | the admin-edited instructions row plus `period_days`, `proof_max_mb`, `max_pending` |

Staff (`IsStaffUser`: 401 anonymous, 403 anyone else; `staff_list` 60/min, `staff_action` 30/h):

| Route | What |
|---|---|
| `GET /api/v1/staff/payments/?status=pending|approved|rejected|all&page=` | the queue (pending oldest first), 25 per page; audited |
| `POST /api/v1/staff/payments/{id}/approve/` | `{changed, code, message, payment}` |
| `POST /api/v1/staff/payments/{id}/reject/` | `{reason}` -> the same shape |
| `POST /api/v1/staff/payments/{id}/proof-link/` | `{url, expires_in, content_type}`; audited (`payment.proof_view`) |
| `GET /api/v1/staff/payments/{id}/proof/?s=<signed link>` | the file, streamed through the API |

## 5. The proof link

A signed token (`TimestampSigner`, salt `kyapture.payments.proof-link`) over `payment id : staff id`, valid
`MANUAL_PAYMENT_PROOF_LINK_SECONDS` (300). The file route needs the staff sign-in **and** a token minted for that payment and that
staff member: another payment, another staff member, a normal user, a tampered or an expired token are all refused (`403`). The
bytes are streamed through the API (`Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy:
no-referrer`, `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`), so no storage path or storage URL ever
leaves the server. The link and the storage name never appear in a payload or a log (tested by capturing every log record).
Images are drawn inside the staff page; a PDF is opened from the same signed link in a new tab (the SPA's CSP has no `frame-src`).

## 6. Expiry at request time

`entitlements._active_plan`, `entitlements_for_subscription` and `get_user_subscription_metrics` all require
`status='active' AND expires_at > now`. A subscription whose period ended is Free the moment the clock passes it, whether or not the
sweep (`sweep_expired_subscriptions`, every 15 minutes) has run. Tests set `expires_at` to the past with the status still `active`
and check: the feature flags, the Free plan limits, the Original-download gate on a real gallery PATCH, the effective download
mode, that nothing is deleted, and that storage above the Free limit reads `over` and refuses new uploads (the BILL-C rules).
The reminder, grace, the audit row and the mails around the end of a period are the daily job of chunk 7.5-C
([KYAPTURE_SUBSCRIPTION_LIFECYCLE.md](KYAPTURE_SUBSCRIPTION_LIFECYCLE.md)); access never waits for it.

## 7. The payment instructions row

`PaymentInstructions` (one row, Django admin: Subscriptions -> Payment instructions): account name, eSewa ID, bank name, account
number, branch, a note and an optional QR. **Public information only**: the page shows every field to any signed-in user; never a
password, PIN or API key. Text is stored with tags stripped and drawn escaped; the QR goes through `sanitize_image_upload`
(decoded and re-encoded: no metadata, no SVG) into public storage under a random name. The Billing page keeps the form shut when
the row is empty.

## 8. Audit and bell

| Action | Written by | Reason column |
|---|---|---|
| `payment.submit` | the user, inside the submit transaction | `payment=<id> plan=<key> amount=<n> NPR` |
| `payment.approve`, `payment.reject` | staff, inside the review transaction (a failed audit write rolls the review back) | the same summary |
| `payment.proof_view` | staff, when a proof link is minted | the same summary |
| `staff.inbox_view` | the queue read | `payments status=<filter>` |

Never the proof, its name, the reference or the user's note. A new payment makes one bell notification
(`payment_review`, link `/dashboard/staff/payments`) for each active staff account; a decision makes one for the user and one
email (through `notifications.notify_payment_reviewed`, which still honours the user's "payments" email preference).
Since 7.5-D every one of these mails is a shared template with a fixed subject (docs/KYAPTURE_EMAIL.md): a submit also sends
"We received your payment" to the payer (same preference) and one "New payment to review" email to `STAFF_ALERT_EMAIL` (payment id,
plan, amount and the staff page link only; no proof link, reference, notes or user).

## 9. Operations

* Settings (`config/settings/base.py`, env-overridable): `MANUAL_PAYMENT_PERIOD_DAYS`, `MANUAL_PAYMENT_MAX_PENDING`,
  `MANUAL_PAYMENT_PROOF_MAX_MB`, `MANUAL_PAYMENT_PROOF_MAX_PIXELS`, `MANUAL_PAYMENT_PROOF_LINK_SECONDS`; throttle `payment_submit`.
* Migrations `subscriptions.0010` (columns, `PaymentInstructions`), `0011` (backfill of old rows: `plan_price` = `amount`,
  `reviewed_at`, `proof_type`), `0012` (the unique constraint; apart from the UPDATE because PostgreSQL refuses an index build in the
  same transaction), `users.0011` (audit actions and a bell kind: state only). Applied to the Docker dev DB only (debt row 169).
* The Celery worker must be restarted with the web process only for the existing mail task (nothing new was added).

## 10. Evidence

* Backend: `apps/subscriptions/tests/test_payment_review_7_5b.py`, 64 tests (reference rules and the database constraint, proof
  types / size / pixels, private storage, pending cap, throttle, audit rows, bell, own list, instructions row and QR, read-only
  admin, 401 / 403 on every staff route, approve / reject / double approve / reject after approve, own-payment ban, rollback on a
  failed review, expiry at request time, the proof link bound to payment / staff / clock, no proof or link in any log, and five
  real-thread races). With the row locks taken out, 3 of the 5 race tests fail. Old tests that used the removed routes were moved to
  the new ones. Full suite on a fresh test database (no `--keepdb`, Redis cache db 3), run detached: **1571 tests, OK** (30 min).
* Frontend: `npm test` 150 / 150 (`billingFlow.test.js`, `staffFlow.test.js`), `vite build` and the Docker frontend image build.
* Browser: [qa-7-5b/results.md](qa-7-5b/results.md), 61 / 61 checks at desktop and 390 px, with a real submit, a real approve and a
  real reject.
* Debt: new rows 169-177.

## 11. Paying for a DIFFERENT plan during an active period (current behaviour, no proration)

What `approve_payment` does today, unchanged by 7.5-C and pinned by `test_another_plan_or_a_lapsed_one_starts_now_instead` (7.5-B) and
`test_paying_for_a_different_plan_during_an_active_period_starts_it_now_for_a_full_period` (7.5-C):

| The user pays for | Their current subscription | Result |
|---|---|---|
| the **same** plan they are on | live (not ended) | the period is added to the current end date: `expires_at = old end + MANUAL_PAYMENT_PERIOD_DAYS`; `starts_at` is kept |
| a **different** plan (upgrade or downgrade) | live | the new plan starts **now** for a full `MANUAL_PAYMENT_PERIOD_DAYS` (30): `starts_at = now`, `expires_at = now + 30 days`. **The unused rest of the old period is dropped: no proration, no credit, no queued change** |
| any plan | ended, `expired`, or none | the paid plan starts now for a full period |

So a Basic user with 10 days left who pays for Studio has Studio for 30 days from approval, and the 10 Basic days are gone. The payment row
records the period it granted (`period_start`, `period_end`). Proration or queuing the new plan is an owner decision (debt row 170, 13-A);
this chunk adds none. In every case the lifecycle markers are cleared, so the new period gets its own reminder and downgrade.
