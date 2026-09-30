# Kyapture — Phase 0 Status (Production Foundation)

Last updated: 2026-09-30 (session 3 — re-verification pass)
Scope: Phase 0 only, per docs/KYAPTURE_VERIFIED_EXECUTION_PLAN.md and
docs/KYAPTURE_PRODUCT_DECISIONS.md. Gallery PATCH/F-01, media optimization,
photo sets/favorites/slideshow, and broad UI redesign are explicitly
deferred — not started, not touched.

## Status: Phase 0 is genuinely complete. Re-verified fresh this session —
zero code changes were needed. All three tracked items (password reset,
production networking, regression/validation) independently re-checked
against the actual repository state and confirmed correct.

This is the third working session on Phase 0. Sessions 1–2 implemented
and then closed out all Phase 0 work (including the `colorHelper` import
casing fix that was blocking the frontend Docker build). This session's
job was purely verification — inspect first, trust nothing claimed by an
external tracker, re-run every check from a clean state. The repository's
`git status` before and after this session is byte-identical for every
Phase 0 file; no rewrite, no re-implementation was needed or performed.

## TASK 1 — Password reset: VERIFIED COMPLETE

Checked directly against the live files, not assumed:
- `backend/apps/users/urls.py` — `password/reset/` and
  `password/reset/confirm/` both routed correctly.
- `PasswordResetRequestView` — anti-enumeration contract intact: identical
  `generic_response` returned whether the account exists, is inactive, or
  the outbound send fails; the failure-handling try/except still wraps
  everything past "does this user exist," so no path can 500 or otherwise
  distinguish a real account from a fake one.
- Both email templates present and correctly reference `{{ display_name }}`
  / `{{ reset_url }}`.
- `PasswordResetConfirmView` — token validation (`default_token_generator`),
  single-use enforcement, and 400-with-no-leaked-exception-detail on
  invalid/malformed input all unchanged and correct.
- Frontend: `/auth/password/reset/confirm/:uidb64/:token` route in
  `App.jsx`, `ResetPasswordConfirmPage.jsx`, and the
  `authApi.resetPasswordConfirm` / `authStore.resetPasswordConfirm` wiring
  all present and consistent with the backend's emitted reset URL.
- Re-ran the regression suite fresh (real PostgreSQL): **11/11 passing**.

Nothing was incomplete or failing. Left untouched, as instructed.

## TASK 2 — Production networking: VERIFIED COMPLETE

Checked directly in `backend/config/settings/production.py`:
- `DATABASES` — present, fail-loud-guarded, reuses the existing
  `DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT` convention.
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` — present.
- `USE_X_FORWARDED_HOST = True` — present.
- `CSRF_TRUSTED_ORIGINS` — present, env-driven with a sane default.
- `CSRF_COOKIE_DOMAIN` — present, defaults to `SESSION_COOKIE_DOMAIN`.
- `NUM_PROXIES` — present, env-driven, defaults to `1` (matches the
  single nginx hop the repo's actual topology uses).
- `frontend/nginx.conf` — present, SPA fallback via
  `try_files $uri /index.html;`, wired into `frontend/Dockerfile`
  (`COPY nginx.conf /etc/nginx/conf.d/default.conf`).
- `docker-compose.yml` — `celery_worker`/`celery_beat` still consistently
  follow `backend/.env` alongside `backend` (no forced-production
  override reintroduced).
- Gallery URLs confirmed still path-based only:
  `/g/:username`, `/g/:username/:slug`, `/g/:username/:slug/download` in
  `App.jsx` — no subdomain routing present or implied, consistent with
  the locked MVP decision.
- No new proxy architecture was invented; the topology is exactly what
  was verified in sessions 1–2 (one nginx image serving the static SPA,
  cross-origin from the Django API via CORS + credentialed cookies).

Nothing was incomplete or failing. Left untouched, as instructed.

## TASK 3 — Regression tests + validation: VERIFIED COMPLETE

All checks re-run fresh this session, from a clean state, against real
PostgreSQL (not just `manage.py check`):

| Check | Result |
|---|---|
| `manage.py check --settings=production` | 0 issues |
| `manage.py migrate --settings=production --noinput` | all 40 migrations apply cleanly |
| `manage.py check --settings=development` | 0 issues |
| `manage.py test apps.users --settings=development` | **11/11 passing** |
| Frontend `vite build` (clean `npm install`, isolated copy) | succeeds, 2402 modules, no errors |
| Deep-link / SPA-fallback simulation (`/dashboard`, `/dashboard/galleries/:id`, `/g/:username/:slug`, password-reset-confirm route) | all 200, correctly served `index.html`; real assets still served; missing assets still 404 |
| Reset-link route matching (`matchPath`, with/without trailing slash) | matches correctly, `uidb64`/`token` extracted |
| `docker-compose.yml` | valid YAML |
| `frontend/nginx.conf` | brace-balanced, directive-sane (no nginx binary available to run `nginx -t` directly) |

No regression coverage gaps were found beyond what sessions 1–2 already
added (the 11-test `apps/users/tests/test_views.py` suite). No new tests
were added this session because none were needed — Task 3 asked to "add
or complete" coverage, and it was already complete.

### Known pre-existing failure (unrelated, not fixed, not Phase 0)

`apps.photos.tests.test_async_uploads.PhotoAsyncUploadTestCase
.test_non_blocking_upload_returns_202_and_dispatches_task` still fails
(`process_photo_asset.delay` expected once, called 0 times). This is
inside the async photo-upload/Celery dispatch path in `apps/photos`,
untouched by Phase 0 and explicitly out of scope ("Do NOT work on media
optimization yet"). Confirmed still present, confirmed still unrelated,
left alone per instruction not to fix unrelated test failures.

### Docker-only checks still pending

No Docker daemon is available in this verification environment. Not run:
`docker build ./backend`, `docker build ./frontend`, `docker-compose up`
end-to-end. Equivalent validation stands in: real-Postgres
`check`/`migrate` under production settings, `collectstatic` with the
Dockerfile's exact placeholder env values (verified in session 1), valid
YAML for `docker-compose.yml`, and the isolated `npm run build` +
SPA-fallback simulation above. This remains the one genuinely open item,
and it is an environment limitation, not a Phase 0 defect.

## Remaining blockers

- None specific to Phase 0's three tracked items — all verified complete.
- Docker-only checks (above) remain pending for lack of a Docker daemon
  in this environment; recommend running `docker-compose build && 
  docker-compose up` once on a machine with Docker available as the final
  sign-off step.
- The pre-existing `apps.photos` test failure (above) is out of scope
  and documented for whichever phase picks up media/upload work next.
- No git commit was made — none was requested across any session. All
  changes remain in the working tree only.
