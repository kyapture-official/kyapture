# 7.5-B QA results (manual payment review)

Run: 2026-10-08 against the Docker stack (app :3000 rebuilt from this branch, API :8000, real Celery worker, Mailpit), Chrome
headless via puppeteer-core. Script: `qa-script.mjs` (61 checks, **61 / 61 pass** on the final run). It creates 3 accounts
(`qa75b-{staff,payer1,payer2}-<stamp>@example.invalid`), 1 gallery, 4 payments, an instructions row with a QR, prints the exact
rows and deletes only those (count asserted to match what it created; proof files, the QR file, the instructions row and the 2 Mailpit
messages by exact name or id). Final state checked: 0 QA users, 0 QA payments, 0 instructions rows (it did not exist before), 0 QA
mails. Audit rows are append-only and stay in the dev DB. The dev DB also holds a real pending payment from another account (no
transaction ID: it predates this chunk); the run never touched it, and every screenshot of a shared list hides the rows that are not
the run's (the page was only restyled with `display: none` for the screenshot).

An earlier run failed 2 checks (the proof image was looked for after a fixed 2.5 s; it did not appear in that run and did appear in
the next, unchanged). The script now waits up to 15 s for the proof or an error; the cause of the one slow load was not found.

## 1. The payer (desktop 1280 and 390 px)

| Check | Result |
|---|---|
| Free account: Billing says Free tier; Original download refused (403) before | pass |
| Instructions (account name, eSewa, bank, number, branch) and the admin note come from the admin row; the note's `a < b & c` is drawn as text | pass |
| The QR is an image from our own storage (`/media/payment_instructions/qr_...`) and loads | pass |
| Empty submit: transaction ID and proof errors inline, **0 requests**; `ab` + a `.txt` file: refused inline, 0 requests | pass |
| Real submit (PNG): toast only after the API answered, exactly 1 POST; pending notice and a history row (plan, amount, ID, Pending, Attached) | pass |
| The user's own list has no proof file or link; submitting did not change the plan | pass |
| payer2 submits payer1's ID in another case with spaces: clear "already submitted" message, no row created | pass |
| payer2's PDF is accepted by the form and submitted | pass |
| After approval: Pro active for 29-30 days, `original_download` true, Original download accepted on the same session (was 403), Billing shows Active Tier Pro and Approved, 390 px no horizontal scroll | pass |
| After rejection: Billing shows the reason as literal text (`<b>x</b> & more`, no `<b>` element) and "Your plan has not changed"; plan still none; 390 px no horizontal scroll | pass |
| The same user may submit the rejected ID again (201); another user may not (400) | pass |
| The period made to end (row still `active`, no sweep): Original download refused again (403) at once; Billing shows "plan ended on ...", no Active Tier; gallery and payment rows still there | pass |
| Emails in Mailpit: "approved" to payer1; "could not be approved" with the reason to payer2 | pass |

## 2. Staff (desktop and 390 px)

| Check | Result |
|---|---|
| Sidebar lists Payments for staff; the queue lists the run's pending payments with their transaction IDs | pass |
| The staff member's own payment: "Your own payment", no Approve / Reject; the API refuses it (403 `cannot_review_own`) | pass |
| View proof: the image loads inside the page from `/staff/payments/<id>/proof/?s=...`; the URL holds no storage path | pass |
| The file answers 200 `image/png`, `no-store`, `nosniff`, `no-referrer`, `default-src 'none'`; the same link answers 403 for the payer and 401 with no sign-in | pass |
| A PDF proof shows an "Open PDF" link (signed); it answers `application/pdf` | pass |
| Approve (real click): the dialog says what happens; toast only after the API; the row leaves the pending list | pass |
| A second approve: 200 `changed: false` "Nothing was changed"; a reject after the approve: 409 and nothing changes | pass |
| Reject: empty reason refused before any request; with a reason the toast follows the API; the staff history shows the reason as literal text | pass |
| 390 px: the queue has no horizontal scroll (checked); the reject dialog fits the screen (screenshot) | pass |
| Audit page lists submit, approve, reject, proof opened | pass |
| The audit rows: 4 submits, 1 approve, 1 reject, 2 proof views; none holds a reference, a file name or the reject reason; each has the trusted address | pass |

## 3. A normal user

At `/dashboard/staff/payments` the page shows "Staff only" and made **0** requests to `/api/v1/staff/`. The API answers 403 to the
same user for the queue, approve, reject, proof-link and proof.

Screenshots: `desktop-billing-form.png`, `desktop-billing-filled.png`, `desktop-billing-pending.png`,
`desktop-billing-duplicate.png`, `desktop-billing-approved.png`, `mobile-billing-approved.png`, `desktop-billing-rejected.png`,
`mobile-billing-rejected.png`, `desktop-billing-lapsed.png`, `desktop-staff-queue.png`, `mobile-staff-queue.png`,
`desktop-staff-proof.png`, `desktop-staff-approve-dialog.png`, `mobile-staff-reject-dialog.png`, `desktop-staff-rejected.png`,
`desktop-audit.png`, `desktop-normal-user-denied.png`. Full-page captures show the sticky sidebar mid-page: that is the screenshot
stitching, not the layout.

## 4. Not covered here

* A PDF is opened in its own tab from the signed link (the SPA's CSP has no `frame-src`); it is not embedded. Debt row 171.
* A real eSewa or bank reference was not tried against the transaction-ID rule (row 173).
* The Pixieset reference for Billing is `docs/pixieset-ref/billing/ky-billing-page.png` (KYAPTURE's own page); the layout is that page
  with the new states; there is no Pixieset equivalent of a manual payment form.
