# KYAPTURE subscription lifecycle (chunk 7.5-C)

What happens around the END of a paid period: a reminder before it, the move to Free after it, and what the owner sees. Built on
7.5-B ([KYAPTURE_PAYMENTS.md](KYAPTURE_PAYMENTS.md)); no second system. Code: `backend/apps/subscriptions/lifecycle.py` (every rule),
`tasks.py` (the Celery task and the sweep), `management/commands/run_subscription_lifecycle.py`, `models.py`
(`LifecycleSettings`, four markers on `UserSubscription`); UI: `frontend/src/pages/subscription/BillingPage.jsx`,
`frontend/src/pages/dashboard/HomePage.jsx`, `frontend/src/utils/billingFlow.js` (`expiryNotice`).

## 1. What existed before (audit)

| Surface | Before 7.5-C | Now |
|---|---|---|
| Access after the period | `entitlements._active_plan`, `entitlements_for_subscription`, `get_user_subscription_metrics` already need `status='active' AND expires_at > now` (7.5-B, debt row 43). `IsSubscribed` is not used anywhere | unchanged. **This is what ends access; the job never does** |
| Payment approval | `payments.approve_payment` (locks payment, user, subscription; extends from the end date on the same live plan, else starts now) | unchanged, plus it clears the four lifecycle markers |
| Celery / beat | `celery_beat` service already in `docker-compose.yml` (one); 7 jobs in `config/celery.py`, including `sweep_expired_subscriptions` every 15 minutes | the schedule moved into `CELERY_BEAT_SCHEDULE` in settings (section 5); one new entry |
| The sweep and `GET my-subscription/` | flipped `status` to `expired` with **no lock and no re-check** | both call `lifecycle.expire_lapsed`, which takes the user row then the subscription row (`FOR NO KEY UPDATE`) and re-reads the status inside. A renewal approved while they ran can no longer be written back to `expired` (a freshly paid user would have read as Free) |
| Reminder, grace, downgrade record, mails | none | the daily job |

Paths that could still give a paid feature after the period ended: **none found**. Every gate (`require_feature`, `has_feature`,
the upload metrics, `effective_high_res_mode`, `build_watermark_spec`, the public logo) reads the same live-plan rule.

## 2. The daily job

Beat entry `subscription-lifecycle-daily` -> task `apps.subscriptions.tasks.run_subscription_lifecycle` -> `lifecycle.run()`.
It runs at 18:25 UTC = **00:25 in Asia/Kathmandu** (UTC+5:45, no daylight saving), just after the local day changes. Steps, per account:

| Step | When it is due | What it does |
|---|---|---|
| Reminder | the period is live and today (Kathmandu) is `reminder_days` or fewer days before the END DATE | one bell notification (`plan_expiring`, links to Billing) and one email, once per period |
| Downgrade | the period ended and the local day is after (end date + `grace_days`) | `status` -> `expired`, legacy `is_active_plan` off, one audit row `subscription.downgrade` (no actor; `plan=<key> period_end=<date> grace_days=<n>`), one bell (`plan_expired`) and one email |
| Retry | a mail failed earlier | the next run sends it again, for `SUBSCRIPTION_EMAIL_RETRY_DAYS` (7) after the grace; a reminder mail is retried only while the period is still running |

**Nothing is deleted.** No file, gallery, photo, set, setting, watermark, branding value or payment row is touched.

**Grace does not extend access.** An ended period is Free at request time (section 4). The grace days only delay the *formal*
downgrade (status, audit row, mail), which is the owner's window to renew before they are told they are on Free.

### Days, in the billing zone

A "day" is a calendar day in `settings.BILLING_TIME_ZONE` (`Asia/Kathmandu`). It is **not** `TIME_ZONE` (still UTC: changing it would
move every existing schedule and date). Period ends Oct 10 18:00 Kathmandu, `reminder_days` 3, `grace_days` 3:

* the reminder is due from **Oct 7 00:00** Kathmandu (Oct 6 23:59:59 is too early);
* the downgrade is due from **Oct 14 00:00** (Oct 13 23:59:59 is the last grace day);
* `grace_days = 0` downgrades from the midnight after the end date.

Tests pin both boundaries to the second, and the UTC equivalent (`BoundaryTests`).

### The admin-edited row

Django admin -> Subscriptions -> **Subscription lifecycle** (one row, like Upload limits): `reminder_days` (1-30, default 3) and
`grace_days` (0-30, default 3). Read at every run: an edit applies to the next run with no deploy. No day count is in code.

### Safe to repeat, safe to run twice at once

* **Markers.** Four columns on `UserSubscription` (`reminder_notified_for`, `reminder_emailed_for`, `downgraded_for`,
  `downgrade_emailed_for`) each hold the `expires_at` the step was done FOR. A renewal moves `expires_at`, so every marker reads "not
  done" for the new period by itself; `approve_payment` and `grant_subscription` also set them to NULL.
* **Two layers of lock.** A cache lock (`subscription-lifecycle:lock`, shared Redis, 30 minutes) makes a second runner skip
  (`skipped='locked'`). Under it each account is processed in its own transaction that locks the user row, then the subscription row, and
  re-reads everything inside: with the cache lock defeated, two threads still make one downgrade, one audit row, one bell, one mail
  (`TwoRunnersAtOnceTests`; with the row locks removed 2 of 3 of those tests fail).
* **Mail claimed, then sent.** The `*_emailed_for` marker is set inside the transaction, the mail is sent after it commits, and the
  marker is cleared again if the send raises. So a mail goes out once, a failed one is retried by the next run, and **a failed mail never
  undoes or blocks the downgrade**. A process killed between the claim and the send loses that one mail instead of sending it twice
  (debt row 180).
* **Old lapses are silent.** A period that ended longer ago than `grace_days + SUBSCRIPTION_EMAIL_RETRY_DAYS` days is downgraded
  (audit row, `silent=old`) without a bell or a mail, so the first run on a database full of old expired rows does not mail everyone who
  ever lapsed. Run `--dry-run` first on a real database.

### Accounts that asked to be deleted (7.5-E)

Billing stops for an account whose deletion is waiting: the reminder and downgrade candidate queries exclude it and each step re-checks inside the lock, so it gets no reminder, no bell, no mail and no `subscription.downgrade` audit row, and its subscription is not changed. If the owner cancels the deletion the next run treats it like any other account. When the purge runs the subscription is set to `cancelled` and deleted with the account ([KYAPTURE_ACCOUNT_DELETION.md](KYAPTURE_ACCOUNT_DELETION.md)).

### Who is not mailed

An account with `is_active = False` (suspended or deactivated) gets no reminder, no bell and no mail; its downgrade still applies. A
deleted account has no subscription row (cascade). The mails also follow the owner's existing **Payments** email preference
(Settings -> Notifications): with it off they get the bell only. Since 7.5-D the mails are the shared templates `plan_expiring`
("Your plan ends on <date>", sent `reminder_days` before the end) and `plan_ended` (the plan HAS ended, the account is on Free,
files and settings kept, renewing restores the paid features), with fixed subjects, HTML and text, and dates in the billing zone
(docs/KYAPTURE_EMAIL.md). Neither says anything about a grace period: access ended at the end date.

## 3. Running it by hand

```
docker exec kyapture-backend-1 python manage.py run_subscription_lifecycle --dry-run   # who would be reminded / downgraded; writes nothing
docker exec kyapture-backend-1 python manage.py run_subscription_lifecycle             # the real run
```

`--dry-run` takes no lock and writes no row, mail, bell or audit entry (tested by snapshotting every table before and after). There is
**no HTTP endpoint** for the job (tested: the likely paths do not resolve). A run is always safe to repeat.

## 4. At request time (the part that does not need the job)

`entitlements.py` stays the single place. A subscription whose `expires_at` has passed is Free for every check in the same instant,
whether its `status` still says `active` or the job never ran (`RequestTimeExpiryTests`: the flags, the Free plan's limits, the real
Original-download PATCH answering 403, and no row written by anyone). The API's `lifecycle` block (section 6) is computed the same way.

## 5. Beat and Docker

`docker-compose.yml` runs **exactly one** `celery_beat` service (`celery -A config beat -l info`; the worker is `celery_worker`). The
schedule is `CELERY_BEAT_SCHEDULE` in `config/settings/base.py`, **one named entry per periodic job**; `config/celery.py` holds none
(assigning `app.conf.beat_schedule = {...}` there silently loses to a settings value, found while building this). 11-D adds its jobs as
more named entries to the same dict and the same beat. `django-celery-beat` is not installed and not needed.

After deploying: restart `celery_worker` (new task) and `celery_beat` (new schedule). `docker compose restart celery_worker celery_beat`.
Production runs the same two processes with `DJANGO_SETTINGS_MODULE=config.settings.production`; exactly one beat (two beats would
still be safe because of the lock, but would double every other job).

## 6. What the owner sees

`GET /api/v1/subscriptions/my-subscription/` gains `lifecycle`:
`{state: 'none'|'active'|'expiring'|'expired', days_left, period_end, reminder_days, grace_days}`. `days_left` counts calendar days in the
billing zone (0 = ends today; negative once ended). `expiring` = live and inside the reminder window; `expired` = the period ended,
whether or not the job has run.

* **Billing**: "Expires in N days" / "Expires today" (amber inside the window) or "Expired", with a **Renew** / **Upgrade** link that scrolls
  to the plan choice; the old "ended on <date>, you are on Free" sentence stays.
* **Dashboard home**: a banner only when the period is inside the reminder window or has ended ("Your Pro plan expires in 2 days. Renew
  to keep it." / "Your Pro plan has ended. You are on the Free plan: your files are kept and the Free limits apply.") with a link to Billing.
  The plan card and the "Current Plan" tile read **Free** after the end instead of the old plan name.
* **Bell**: `plan_expiring` and `plan_expired`, both linking to Billing.

## 7. After the downgrade: the exact behaviour

| Area | Behaviour (all server-side) |
|---|---|
| Uploads | refused when the new files do not fit the Free plan's storage: `403 storage_limit_reached` (BILL-C). An account already over the limit keeps everything and uploads nothing; deleting files or renewing lifts it. Video minutes and the collection cap follow the Free plan row the same way |
| Existing galleries | stay published and public; nothing is unpublished, locked or deleted |
| Clients | can still open the gallery and download. Downloads are at the **Free level**: the 3600 px Download Master / Web Size, never the byte-identical original, even if the owner saved "Original" (`effective_high_res_mode` falls back; the stored choice is not touched) |
| Original download (owner) | **locked**: choosing "Original" is refused `403 original_download_requires_upgrade`. A choice that was already stored stays stored and simply stops taking effect |
| Watermark (owner) | **locked**: changing the watermark or switching it on is refused `403 watermark_requires_upgrade`; switching it OFF is always allowed. A stored watermark stays stored; new derivatives are not watermarked while Free (`build_watermark_spec` returns none) |
| Branding (owner) | **the logo is locked**: uploading or replacing it is refused `403 branding_requires_upgrade`; removing it is always allowed; the stored logo file is kept but not shown to clients. **The brand colour was never plan-gated** (`Gallery.branding_color` / `User.branding_color` are editable and shown on Free): a pre-existing gap, debt row 183 |
| Everything else | unrelated settings keep saving normally; the stored Pro values never block them |
| Upgrade | renewing makes the stored original choice, watermark and logo apply again **with no re-entry** (tested: nothing is saved between the downgrade and the renewal) |

## 8. Operations and evidence

* Migrations `subscriptions.0013` (model + four columns), `0014` (creates the one settings row, so reading it is one query) and `users.0012` (two bell kinds, one audit action: state only) were applied
  to the Docker dev DB only (debt row 178).
* New settings: `BILLING_TIME_ZONE`, `SUBSCRIPTION_EMAIL_RETRY_DAYS`, `SUBSCRIPTION_LIFECYCLE_LOCK_SECONDS`.
* The settings row is one extra query on `my-subscription`; `test_query_efficiency` allows 5 (was 4) with that reason. The first full-suite run failed only on that bound (the row was created lazily on the first read: 9 queries).
* Tests: `apps/subscriptions/tests/test_lifecycle_7_5c.py`, 58 tests (request-time expiry with the job never run, both boundaries,
  once-only reminder and downgrade, renewal, paid user untouched, mail failure and retry, suspended and preference-off accounts, the admin
  row, the lock, real-thread races, the command, the beat entry, over-limit view/download/upload, stored values kept and restored).
  `frontend/src/utils/billingFlow.test.js`: `expiryNotice`.
* Browser: [qa-7-5c/results.md](qa-7-5c/results.md).
