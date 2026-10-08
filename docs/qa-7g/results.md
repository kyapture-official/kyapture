# 7G results: fixes for reviewer 7R-2

Each 7R-2 finding was treated as a claim and proven (a failing test or a real request/log check) before code changed.
Docker dev stack only. QA accounts were created with unique `@example.invalid` addresses and deleted by exact address
(rows printed first; counts matched what was created).

## Proof before the fix

| Finding | Check on the 7F code | Result |
|---|---|---|
| R1 deadlock | `test_gallery_lock_7g.py`: thread A locks the photographer row (`FOR UPDATE`), B publishes, A inserts an asset | B's PATCH 500, `deadlock detected ... while locking tuple in relation "users"` at COMMIT |
| R1 deadlock, real upload | real `POST /photos/<slug>/upload/` paused after its photographer lock, owner publishes | the UPLOAD failed: 500 `upload_processing_error`, `DeadlockDetected` on `galleries` |
| R1 bcrypt in lock | `hashpw` spy during a password PATCH | called with a transaction open (`[True]`) |
| R1 "waits for uploads" | uncommitted upload holding an inserted asset; then PIN use / owner save / set-download-pin | 0.173 s / 0.348 s / 0.655 s: **not a problem** (FKs are `DEFERRABLE INITIALLY DEFERRED`; debt row 157) |
| R1 publish waits | after the gallery fix alone, publish during a paused real upload | 3.0 s (the full hold): the notification insert waited for the upload's `FOR UPDATE` on the photographer row |
| R2 PINs, one address | 8 parallel right PINs, production bcrypt cost (with cost 4 the tries barely overlap and it passed) | `[200 x5, 429 x3]` |
| R2 mixed | 4 wrong + 4 right PINs in parallel, one address | `[200, 200, 401, 401, 401, 429, 429, 429]` |
| R2 email codes | 8 parallel right codes (8 listed guests), one address; 4 wrong + 4 right | `[200 x5, 429 x3]`; `[200 x3, 401 x2, 429 x3]` |
| R3 | `docker logs kyapture-backend-1 \| grep -c link_token=` | 13 lines, each with a full key |
| R4 | admin form opened, PIN use recorded, form saved | `pin_use_count` 2 back to 1; a posted `design_settings` overwrote the counter |
| R5 | refresh run without the lock / with the 7F wiring | 2 / 1 of the new interceptor tests fail |

## After the fix

| Check | Result |
|---|---|
| R1 (10 tests) | publish during a real upload 0.058 s, notification created, upload 202; PIN use 0.04-0.09 s; two real uploads still queue (the 2nd waited > 1 s); one bcrypt, outside any transaction; a publish that rolls back sends no notification |
| R2 (7 tests, one shared address) | 8 right PINs `[200 x8]`, no lock; 4+4 `[200 x4, 401 x4]`, no lock; 20 wrong: 5 bcrypt checks, 15 x 429, then locked (even for the right PIN); same three for email codes. 7F's parallel-PIN test now uses one address again: `[200, 403 x7]` |
| R3 (6 tests + browser) | header opens the job; `?link_token=` 400 even when valid; transition flag reads it; preflight allows `x-download-link-key`. Browser (`qa_r3_ready.mjs`, desktop + 390 px): 15/15, every poll sent the header, no poll URL had the key, page lists the ZIP; backend log since the run: 4 job lines (2 preflight + 2 GET), **0 `link_token=`**, key absent. The job was ready at the first poll (3 small photos), so each page polled once |
| R4 (2 tests + browser) | `qa_r4_admin.mjs`: field has no input and is shown read-only (desktop + 390 px, checked in the DOM; the screenshots show the top of the form, the field is further down), PIN use 1 -> 2 while the form was open, save "changed successfully", count still 2, title saved: 8/8 |
| R5 (5 tests + browser) | `axiosInstance.test.js` passes; Chrome, two tabs, access cookie deleted, both reloaded together (`docs/qa-7f/qa_f7_tabs.mjs`): 6/6 rounds signed in, ONE refresh (200) per round |

## Other secrets in query strings (R3 grep of every client call)

- `clientsApi.buildPhotoDownloadHref`: `?token=` (unlock token) and `?download_token=` on single-photo/video download anchors.
- `clientsApi.buildJobFileHref`: `?token=` on ZIP file anchors.
- `PhotoLightbox.jsx`: `?token=` on `<video src>` playback.
- An anchor or a video element cannot send a header: all three stay with debt row 133 (14-A/16-A).
- `getFavorites`, `getFavoriteLists`, `getFavoriteListPhotos`: `?client_uid=` and `?email=`. The owner's Favorite Activity filter: `?email=`. These are in debt row 160.
- No PIN or password is sent in a query string anywhere.

## Commands

- Targeted backend runs: `docker exec -e CELERY_TASK_ALWAYS_EAGER=true kyapture-backend-1 python manage.py test <labels> --noinput --keepdb`.
- Full suite: fresh test DB (no `--keepdb`), detached, `/tmp/full7g.log`: **Ran 1440 tests in 1894 s, OK, EXIT:0**.
- Frontend: `npm test` 134/134 pass; `npm run build` built.
