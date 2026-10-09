# 7.5-D browser QA: every email in Mailpit (Docker stack)

How: `qa_trigger.py` (run in the backend container) created 6 throwaway accounts, one gallery with a hostile title
(`<i>QA</i> Wedding & Co`), and triggered each email through its real path: password reset and change through the API and the Celery
worker, payment submit / approve / reject through the API (staff account), the lifecycle step functions for two accounts only,
activity alerts through the model signals and the worker, the ready email and the download code through their own functions. Mailpit
(`localhost:8025`) was empty before the run. `qa-script.mjs` (puppeteer-core, Chrome) then opened every message at
`/view/<id>.html` and `/view/<id>.txt`: desktop 1000 px and 390 px, each in light and dark (`prefers-color-scheme` emulation).
Screenshots: `shots/` (`*-desktop`, `*-m390`, `*-m390-dark`, `*-desktop-dark`, `*-text-m390`); raw numbers: `shots/results.json`.
Cleanup: `qa_cleanup.py` printed the exact rows, then deleted by exact id (6 users, 1 gallery, 2 payments, 1 job, all cascades);
0 left. The Mailpit messages (14, all from this run) were deleted by exact id. The audit rows the actions wrote cannot be deleted.

## Result: 14 messages (12 kinds, the staff alert twice), 0 failed checks

| Subject (fixed) | From | Reply-To | Card at 1000 px | Page width at 390 px | Dark card |
|---|---|---|---|---|---|
| Reset your Kyapture password | no-reply@kyapture.com | support@kyapture.com | 600 | 390 | rgb(26,26,28) |
| Your Kyapture password was changed | same | same | 600 | 390 | same |
| Your Kyapture download code | same | same | 600 | 390 | same |
| Your photos are ready for download | same (display name = studio) | the photographer | 600 | 390 | same |
| New download from one of your collections | same | support | 600 | 390 | same |
| New favorite in one of your collections | same | support | 600 | 390 | same |
| We received your payment (new) | same | support | 600 | 390 | same |
| Your payment was approved | same | support | 600 | 390 | same |
| Your payment could not be approved | same | support | 600 | 390 | same |
| Your Kyapture plan is ending soon (new template) | same | support | 600 | 390 | same |
| Your Kyapture plan has ended (new template) | same | support | 600 | 390 | same |
| New payment to review (new, to `STAFF_ALERT_EMAIL`, x2: two payments) | same | support | 600 | 390 | same |

Checked on every message, in every one of the four views (desktop/390, light/dark): card width never above 600; no horizontal scroll at 390
(page width 390); 0 images, 0 scripts and 0 requests outside Mailpit; system font stack; the wordmark text "Kyapture" and a `mailto:` support
link present; the dark view changes the card colour; the text part holds no template markup and has the support address; no subject contains
a 6-digit number. The "plan ends on <date>" heading read `Your plan ends on 11 Oct 2026` for a period ending 2 days + 3 h from the run.

## Found and fixed during this QA

* The ready email was 459 px wide at 390 px (the gallery link did not wrap). The base now wraps long words
  (`overflow-wrap:anywhere`); re-run: 390 px on all 14.
* The QA check for "no markup in the text part" first flagged text/plain parts that correctly contain the visitor's or photographer's own
  typed `<u>`/`<i>`; the check now looks for the template's own tags only.
* The first trigger run failed on the test client's host name; its 6 partial accounts and 1 gallery were removed by exact email and slug
  (printed first) before the real run.

## Not covered

Real mail clients (Gmail, Outlook, Apple Mail, a phone app) and real delivery through SES: debt row 186.
