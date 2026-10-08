# 7F results: fixes for reviewer 7R's findings

Date: 2026-10-08. Branch `feature/landing-page-redesign`. Phase 1 commit `ab05434` (F1, F2); Phase 2 commit "security(7F): reviewer findings".
Every finding was a claim from a read-only review; each was proven first (failing test or real request). All 8 were real.

## Proof before the fix, and after

| # | Before (measured) | After | Test |
|---|---|---|---|
| F1 | 8 parallel right-PIN requests with 1 use left: 8 tokens. Owner save during a PIN use: `pin_limit` 5 back to 3, `limit_total` and High Resolution Off lost. PIN use during an owner save: count 3 back to 2. New PIN during an old-PIN use: count 3 instead of 0 | 1 token, 7 x 403; both changes kept in both orders; the new PIN keeps 0 (the old-PIN request answers 401) | `backend/apps/clients/tests/test_pin_counter_lock_7f.py` (TransactionTestCase, threads, 4) |
| F2 | 17 of 19 per-key tests failed (`high_res`, `web`, `require_email`, `restrict_contacts`, `allowed_emails`, `sets_enabled`, `limit_total`, `privacy.pin_limit`, partial `watermark`) | 19/19 | `backend/apps/galleries/tests/test_partial_save_7f.py` |
| F3 | Old frontend container log: `"GET /g/u/s/download/file/x?key=abc7fprefix HTTP/1.1" 200 592 "http://localhost:3000/g/u/s/download/file/x?key=refabc"` | Same requests (plus a 404 under `/assets/`): `"GET /g/u/s/download/file/x HTTP/1.1" 200 ... "http://localhost:3000/g/u/s/download/file/x"`, 0 `key=` in the log. Ready email link `#key=`; ready page from `#key=` and from an old `?key=` link (moved to `#key=`), desktop and 390: 19/19 | `frontend/src/security/nginxLog.test.js`, `downloadFlow.test.js`, `qa_f3_ready.mjs` |
| F4 | 10 of 12 GPS-PNG tests failed: compressed iTXt XMP and Raw-profile EXIF kept their GPS; bad compression / hex / a 40 MB bomb were not refused | 14/14: GPS removed (camera tags and pixels kept) or the file refused (upload answers 400 `location_strip_failed`) | `backend/apps/photos/tests/test_png_location_7f.py` |
| F5 | Rows 150, 152 owned by read-only 7R | Both owned and closed by 7F; 6 simultaneous submissions of one reset link: one 200, five 400, the winner's password set | `backend/apps/users/tests/test_password_reset_concurrency_7f.py` |
| F6 | 20 parallel wrong codes: 20 comparisons (12 through the API); 20 parallel wrong PINs, one client: 15 bcrypt checks; 5 wrong codes did not lock the client (the next right code got 200) | at most 5 comparisons / bcrypt checks; wrong codes lock the client (429); 10 wrong codes per gallery + address per day, then 429 `too_many_codes` and no new code | `backend/apps/clients/tests/test_atomic_counters_7f.py` (5) |
| F7 | Pre-fix build in Chrome, two tabs with an expired access cookie reloaded together: 1 of 4 rounds, one refresh answered 401 and that tab went to `/login` | Fixed build: 0 of 8 rounds (every refresh 200); unit model of the rotating token | `frontend/src/api/refreshLock.test.js`, `qa_f7_tabs.mjs` |
| F7 | Logout with an expired access cookie never run in a browser | logout 401, refresh 200, logout 200, `/login`, `/auth/me` 401 afterwards (5/5) | `qa_f7_logout.mjs` |
| F8 | A full signed job-link key in `docs/qa-1r5c/ready-email.txt:9` and `.html:65` | replaced by `<signed-job-key-removed>`; the 7 screenshots show no key | debt rows 102, 153 |

Side effect of F6 (by design): the per-client lockout now counts every typed PIN/password/code try before it is checked, so
more than 5 SIMULTANEOUS tries from one address get 429 even if one of them is right; one after another nothing changes.

## Test isolation

The first full run (1415 tests) ended with one error: `setUpClass` of `ParallelResetConfirmTests` hit a duplicate
`django_content_type` row, because `serialized_rollback=True` restored rows that `post_migrate` had already re-created after
`CoverRaceTests` (a TransactionTestCase without it) flushed the database. So that test had not run. Reproduced with only the
four TransactionTestCase modules in suite order; fixed by dropping `serialized_rollback` from the three 7F classes and
re-creating the plan rows in `setUp` (`apps/subscriptions/testing.py::ensure_seed_plans`). Same order afterwards: 59/59, all 10
7F concurrency tests executed (6 reset threads: one 200, five 400 `reset_link_invalid`; 8 PIN threads with 1 use left:
one 200, seven 403). New agent rule: no `serialized_rollback` in TransactionTestCase classes.

## Scripts

Browser scripts need `npm i puppeteer-core` and Chrome; they read `QA7F_EMAIL`, `QA7F_PASSWORD`, `QA7F_USERNAME`, `QA7F_SLUG`
from the environment. The QA account (`qa7f-1008a@example.invalid`), its gallery, photo and job were created through
`manage.py shell` and deleted by exact id afterwards (5 rows), with their two media folders.
