# 7.5-C QA results (subscription lifecycle)

Run: 2026-10-08 against the Docker stack (app :3000 rebuilt from this branch, API :8000, real Celery worker and **one** beat restarted
with the new schedule, Mailpit), Chrome headless via puppeteer-core. Script: `qa-script.mjs` (**43 / 43 checks pass**, first run).
It creates 3 accounts (`qa75c-{active,soon,expired}-<stamp>@example.invalid`) and 1 gallery, prints the exact rows, and deletes only those
(count asserted to be 3 before the delete; the Mailpit messages by id). Final state checked: 0 QA users, 0 subscriptions left, 0 Mailpit
messages for the run. The one audit row the job wrote (`subscription.downgrade`, target = the QA expired account) is append-only and
stays in the dev DB. **Safety:** the real job run is made only after `--dry-run` listed nobody but this run's accounts (the dev DB
holds other accounts; at run time none of them was a candidate).

| Area | Check | Result |
|---|---|---|
| API | `my-subscription` `lifecycle`: active (20 days), expiring (2 days), expired (-5) | pass |
| Request time | expired owner, no job run: watermark PATCH refused `403 watermark_requires_upgrade` | pass |
| Billing, desktop | active: "Expires in 20 days", no link; soon: "Expires in 2 days" (amber) with **Renew**, which scrolls to the plan choice; expired: "Expired" with **Upgrade**, "plan ended on ... you are on the Free plan", no Active Tier | pass |
| Dashboard, desktop | active: no banner, tile **Pro**; soon: banner "Your Pro plan expires in 2 days. Renew to keep it." (link to /dashboard/billing); expired: banner "Your Pro plan has ended. You are on the Free plan: ...", tile **Free**, the plan card reads "Free Plan - Your Pro plan ended Oct 3, 2026" with an `expired` badge | pass |
| 390 px | Billing and dashboard of all three: no horizontal scroll; both banners visible and inside the screen | pass (6 pages) |
| Dry run | lists the soon account (remind) and the expired account (downgrade), not the active one; **no marker, no bell, no audit row, no mail** | pass |
| Real run | expired: status `expired`, marker set, legacy flag off, **one audit row with no actor** (`plan=pro period_end=2026-10-03 grace_days=3`), one bell, one mail; soon: reminder marker, still `active`, one bell, one mail; active: nothing | pass |
| Mail content | downgrade: subject "ended", "Nothing was deleted", link to Billing; reminder: subject "expires", link to Billing; no token, no storage path | pass |
| Second run | still 1 audit row, 2 bells, 2 mails in total (no new mail) | pass |
| Bell | the expired owner's bell lists "Your Pro plan ended on 03 Oct 2026 ...", link `/dashboard/billing` | pass |
| After the job | Billing still "Expired"; watermark still refused; the stored `original` download choice and the gallery are untouched | pass |
| Renewal | `grant_subscription` (a new period): Billing "Expires in 30 days", no banner, tile Pro, watermark accepted (200) with no re-entry, all four markers NULL | pass |

Screenshots (desktop and 390 px, each next to its state): `desktop-billing-{active,soon,expired}.png`, `desktop-home-{active,soon,expired,renewed}.png`,
`mobile-billing-{active,soon,expired}.png`, `mobile-home-{active,soon,expired}.png`. They show only the run's own accounts.

Notes:
* `GET my-subscription` (which the page calls on load) flips a lapsed row to `expired` under the row locks, so by the time the browser
  had opened the pages the row already read `expired`; the proof that nothing needs the job is the 403 above and the unit test with
  the job never run (`RequestTimeExpiryTests`, which reads no endpoint that writes).
* The dashboard stats endpoint still reports a lapsed owner as `no_subscription` (debt row 184); the banner and the tile come from `my-subscription`.
