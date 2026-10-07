# KYAPTURE secrets inventory and exposure review (SEC-0)

Scope: working tree, local untracked config (`backend/.env`, `frontend/.env.local`), Docker/compose files, and the git
history of **every** branch (`main`, `dev-testing`, `feature/landing-page-redesign` and their `origin/*` copies, 171 commits).

**No secret value appears in this document.** Locations are given as file, line and type only. Every search printed
masked output (path, line number, match type, length/entropy/placeholder markers), never the matching line. For `.env`
files only variable NAMES were listed.

Finding IDs (SEC-xx) refer to [threat-model.md](threat-model.md).

---

## 1. Where secrets are expected

### 1.1 Backend environment variables (read in `backend/config/settings/*.py`)

| Variable | Secret? | Read at | Required in production |
|---|---|---|---|
| `SECRET_KEY` | **Yes — critical** | `base.py:14`, `production.py:23` | Yes, fail-loud guard (`production.py:26-34`) |
| `DB_PASSWORD` | **Yes** | `development.py:14`, `production.py:69`, `docker-entrypoint.py:42` | Yes (`production.py:53-62`) |
| `DB_NAME`, `DB_USER`, `DB_HOST`, `DB_PORT` | No (connection info) | same | Yes except `DB_PORT` |
| `AWS_ACCESS_KEY_ID` | Identifier (treat as sensitive) | `base.py:188`, `apps/core/storage.py:54-57` | Yes (`production.py:93-104`) |
| `AWS_SECRET_ACCESS_KEY` | **Yes — critical** | `base.py:189`, `apps/core/storage.py:56` | Yes |
| `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_SES_REGION_NAME`, `AWS_SES_REGION_ENDPOINT` | No | `base.py:190-191`, `production.py:141-144` | Bucket yes |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | **Can embed a Redis password** | `base.py:232-233` | No guard |
| `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL` | No | `base.py:395-396` | Sender yes (`production.py:114-125`) |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT` | No (dev only; no SMTP user/password is read anywhere) | `development.py:56-62` | — |
| `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `SESSION_COOKIE_DOMAIN`, `CSRF_COOKIE_DOMAIN`, `SECURE_SSL_REDIRECT`, `NUM_PROXIES`, `FRONTEND_URL` | No (security-relevant config) | `production.py:157-242` | Defaults exist |
| TTL / limit knobs (`CLIENT_SESSION_TTL_DAYS`, `DOWNLOAD_*`, `WEB_SIZE_*`, ...) | No | `base.py:258-325` | — |

SES reuses the S3 key pair (`production.py:130-136`): one IAM principal can write the media bucket **and** send mail.

### 1.2 Frontend build-time variables

`VITE_API_BASE_URL`, `VITE_API_URL`, `VITE_MEDIA_URL`, `VITE_PUBLIC_APP_URL`, `VITE_USE_MOCK_DATA`
(`frontend/src/api/axiosInstance.js:9-10`, `frontend/src/utils/constants.js:2`, `frontend/src/utils/appUrl.js:34`, `useGalleries.js:7`).
None is a secret; all are baked into the public bundle. Rule to keep: **never** put a secret in a `VITE_*` variable.

### 1.3 Secrets created at runtime

| Secret | Storage | Protection |
|---|---|---|
| Photographer passwords | `users.User.password` | Django PBKDF2 hasher (default) + validators (`base.py:150-155`) |
| Gallery password | `Gallery.password_hash` (`apps/galleries/models.py:56`) | bcrypt (`apps/galleries/views.py:518`) |
| Download PIN | `Gallery.download_pin_hash` (`models.py:66`) | bcrypt (`views.py:591`); 4-8 digits (SEC-04) |
| JWT access/refresh | HttpOnly cookies; refresh JTIs in `token_blacklist` tables | HS256 signed with `JWT_SIGNING_KEY` (default `SECRET_KEY`, 7-B) |
| Gallery unlock token | `ClientSession.access_token` holds its **SHA-256** since 7-B (`hash_unlock_token`, migration `clients.0013`) | 256 random bits from `secrets`; returned once by the unlock response (SEC-14) |
| Download / job-link / file tokens | Not stored; `django.core.signing` | Salted, `SECRET_KEY`-signed, TTL 2 h / job TTL / file TTL (`download_access.py:348-460`) |
| Password-reset tokens | Not stored | `default_token_generator` (`apps/users/views.py:473`) |
| S3 presigned URLs | Not stored | 1 h expiry; URL carries the access key ID (by SigV4 design) |

---

## 2. Environment and configuration handling

- `base.py:11` loads `backend/.env` with `python-dotenv`. Compose passes the same file with `env_file` (`docker-compose.yml:76-77, 123-124, 157-158, 187-188`) and then **overrides** `DB_*`, broker URLs and mail settings with literal values in `environment:`.
- Local files (names only, values not read):
  - `backend/.env`: `SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DJANGO_SETTINGS_MODULE`. No AWS variables, so dev runs on local disk storage.
  - `frontend/.env.local`: `VITE_API_URL`, `VITE_MEDIA_URL`.
  - Both are ignored (`.gitignore:17` `*.env`, `.gitignore:18` `.env.local`) and **were never committed** (history name scan, §5).
- Production guards refuse to start without a real `SECRET_KEY`, DB variables, S3 trio and sender (`production.py:23-125`). Good: no silent fallback in production.
- `backend/Dockerfile:68-89` passes **placeholder** build args (`build-time-placeholder…`) only to run `collectstatic`; the comment states they are not credentials and runtime env overrides them. Verified shape: the RUN line references the ARGs; their defaults are placeholders.
- Gap: there is **no `backend/.dockerignore`**, so `COPY . .` (`backend/Dockerfile:50`) puts `backend/.env` into the image (SEC-10). `frontend/.dockerignore` correctly excludes `.env` and `.env.*`.
- Gap: no secret manager integration; production values are expected from "the orchestrator" (`docker-compose.yml:24-28`, comment only). Nothing in the repo shows how production secrets are stored or who can read them (needs verification, 15-A).

---

## 3. Hardcoded-secret risks (current working tree)

| # | Location | Type | Assessment |
|---|---|---|---|
| H1 | `backend/config/settings/base.py:14` | Django `SECRET_KEY` fallback literal (41 chars, public `django-insecure-` placeholder) | **Weakness, mitigated**: production rejects it (`production.py:24-34`); dev uses it only if `.env` lacks `SECRET_KEY` (SEC-12) |
| H2 | `backend/config/settings/production.py:24` | Same public placeholder, used only to reject it | Not a secret |
| H3 | `backend/config/settings/development.py:14` | DB password fallback literal (13 chars) | **Weakness (dev)**: same value as H4 and equal to the DB name/user (SEC-11) |
| H4 | `docker-compose.yml:38, 84, 129, 163, 193` | Postgres password literal, 5 copies | **Weakness (dev)**: one value; also in history since the first commit `0f370db` (SEC-11) |
| H5 | `backend/Dockerfile:68-76` | Build-arg placeholders | Not secrets (documented placeholders) |
| H6 | `docs/qa-1r5e/qa-script.js:1` (comment), `:11`, `:12` | QA gallery password (11 chars) and download PIN (4 digits) in plaintext | **Info**: values of a throwaway dev QA gallery; still a pattern to avoid (SEC-25) |
| H7 | `frontend/cypress/e2e/smoke_spec.cy.js:9` | Test user password literal (17 chars) for a random throwaway user | Info: test fixture |
| H8 | `backend/apps/**/tests/*.py` | Many `password=` fixtures | Info: test-only values, not real accounts |
| H9 | `API_DOCS.md:649` | `access_token` example (12 chars, placeholder-shaped) | Not a secret |

High-signal patterns found in the working tree (tracked + untracked, excluding `node_modules`, `venv`, `benchmark*`, images):
**none** for AWS access key IDs, private-key blocks, GitHub/Slack/Stripe/Google keys, JWTs, or URLs with embedded credentials.
Root text files `.aider.chat.history.md`, `.aider.input.history` (untracked), `update.md`, `opencode.json`, `README.md`,
`directory_structure.txt`, `temp_tree.py` (tracked): **0** high-signal matches.

---

## 4. Client-side exposure risks

| Item | Where | Risk |
|---|---|---|
| JWTs | HttpOnly cookies only (`apps/users/views.py:52-71`); the persisted auth store keeps only `user` and `isAuthenticated` (`frontend/src/store/authStore.js:154-161`) | Low: not readable by script |
| CSRF token | readable `csrftoken` cookie, sent as `X-CSRFToken` (`axiosInstance.js:34-49`) | By design (double-submit) |
| Gallery unlock tokens, download tokens | `sessionStorage` (`frontend/src/store/clientStore.js:22-60`) | Readable by any script on the SPA origin; CSP `script-src 'self'` limits XSS (SEC-14) |
| Favorites identity (`client_uid`) and remembered visitor email | `localStorage` (`frontend/src/store/visitorStore.js:4-24`) | Low; the email is also the key for SEC-02 |
| Saved login email ("remember me") | `localStorage` (`frontend/src/pages/auth/LoginPage.jsx:89-93`) | Low (PII on shared machines) |
| Tokens in URLs | `?token=`, `?download_token=`, `?file_token=`, `?link_token=` (`apps/clients/views.py:431, 1442-1458, 1527, 1818`) | Logged by servers/proxies, kept in history; `Referrer-Policy: strict-origin-when-cross-origin` (`nginx.conf:57`) stops path leakage cross-origin |
| S3 presigned URLs | Owner `original_url` (SEC-08), video redirect (SEC-07) | Expose the access key ID (not the secret) and private key paths |
| `VITE_*` variables | baked into the bundle | Only URLs today |
| Committed build output | `frontend/dist-phase2-verify/assets/index-*.js` is tracked | Info: contains whatever `VITE_*` values that build had (URLs only per the scan) |

---

## 5. Git and history exposure

### 5.1 Method

1. File-name scan of every path that ever existed on any branch (`git log --all --name-only`) for `.env*`, `*.pem`, `*.key`, `id_rsa*`, `*credentials*`, `*secret*`, `*.p12`, `*.pfx`, `*.sql`, `*.dump`, `*.sqlite3`, `.npmrc`, `.pypirc`.
2. Content scan of every **added** line in every commit on all branches (`git log --all -p --unified=0`), excluding `benchmark/`, `benchmark-artifacts/`, `docs/pixieset-ref/`, images and `package-lock.json`. Patterns: AWS key ID, private-key header, GitHub/Slack/Stripe/Google tokens, JWT, credentialed URL, `django-insecure-`, `SECRET_KEY`/password/AWS-secret/api-key assignments with a literal. Output: path, pattern type, commit and line only.
3. Each high-signal hit was classified by shape only (length, entropy, placeholder markers, equality with a known dev value).

### 5.2 Results

| Finding | Evidence (commit:path:line, type) | Assessment |
|---|---|---|
| No cloud credentials ever committed | 0 hits for AWS key IDs, private keys, JWTs, provider tokens, credentialed URLs across 171 commits | Good: **no AWS rotation is needed because of git history** |
| `backend/.env` / `frontend/.env.local` | never in any commit | Good |
| `backend/.env.example` (deleted in `cadf271`) | `0f370db:L1, L4`; `aecfb94:L8, L10, L13`; `e266625:L9, L20` — `SECRET_KEY`, `DB_PASSWORD`, `AWS_SECRET_ACCESS_KEY` assignments | All placeholder-shaped **except** `aecfb94:backend/.env.example:L10`: a 26-char `SECRET_KEY` literal with no placeholder marker. **Needs verification** that it was never used as a real key anywhere (SEC-25) |
| `frontend/.env.example` (deleted in `cadf271`) | in `0f370db`, `7ce4032` | No high-signal match |
| Dev DB password | `docker-compose.yml` from `0f370db:L21` / `74c2d8e:L10` onward; `development.py:L14` from `aecfb94` | Same dev value as H3/H4; permanent in history. Matters only if the remote is public or the value is reused anywhere real |
| `django-insecure-` placeholder | `base.py`, `production.py`, `.env.example` | Public Django scaffold string; not a secret |
| QA gallery password/PIN | `82668cc:docs/qa-1r5e/qa-script.js:L11` and later | Throwaway QA values (H6) |
| `Windows_TemporaryKey.pfx` | `benchmark/tools/cmake-4.4.3-windows-x86_64/share/cmake-4.4/Templates/Windows/` | Vendored CMake template file (third-party), not a project credential. Info; `benchmark/` is off-limits to agents per `docs/KYAPTURE_AGENT_RULES.md` |
| `password` assignment hits in app/test code | many files | Code identifiers (`password: data.password`, fixtures), not secrets |

### 5.3 Limits

Regex scanning cannot prove absence; binary files were not inspected; `benchmark*` trees were scanned by name only.
The 11 tracked screenshots in `docs/pixieset-ref/` were **not opened** (debt row 39 says they show an IP and emails; they
are already on `origin/feature/landing-page-redesign`: SEC-29). Whether the GitHub remote is public is unknown.

---

## 6. Logging and error exposure

| Path | What leaks | Assessment |
|---|---|---|
| App loggers | Reviewed every `logger.*` call naming token/password/pin/email: they log ids only (`apps/clients/ready_email.py:115-153`, `apps/users/views.py:493-499`, `apps/clients/download_jobs.py:302-311`) | Good |
| Dev email | Console backend prints password-reset links to the server terminal (`development.py:47-56`); compose sends them to Mailpit, published on `:8025` (SEC-11) | Dev only; reset links are bearer secrets |
| Access logs | Query-string tokens (§4) appear in runserver output, gunicorn access logs (if enabled) and the proxy | Weakness (SEC-14) |
| API errors | `ApiExceptionMiddleware` returns a generic JSON 500 and logs the traceback server-side (`apps/core/middleware.py:41-61`) | Good |
| DEBUG pages | `DEBUG=True` in dev (`development.py:5`) shows technical pages for non-API paths (e.g. `/admin/`); Django's filter masks setting names containing `SECRET`, `PASS`, `KEY`, `TOKEN`, etc. | Dev only; `CELERY_BROKER_URL` would show a Redis password if one is ever embedded there (name not masked) — needs verification |
| Entrypoint | Prints `psycopg2.OperationalError` text while waiting for the DB (`docker-entrypoint.py:79-81`) | Info: host/user, not the password |
| `test_s3_connection` | Prints the probe file's resolved URL (`apps/core/management/commands/test_s3_connection.py:49`), a presigned URL with the access key ID | Info (SEC-26) |
| Log storage | `backend/logs/django.log` inside the container (`base.py:332-359`), ignored by git (`.gitignore:33, 54-55`) but copied into the image by SEC-10 | Weakness |

---

## 7. Secret rotation requirements

| Secret | Rotate when | Blast radius of rotation | Current support |
|---|---|---|---|
| `SECRET_KEY` | Suspected leak; staff departure; before first production launch if it was ever in a dev `.env` shared with others | With `SECRET_KEY_FALLBACKS` none (links signed with the old key keep verifying); without, every signed link breaks | `SECRET_KEY_FALLBACKS` and a separate `JWT_SIGNING_KEY` since 7-B; runbook §7.1 |
| `DB_PASSWORD` | Leak; staff change | Requires coordinated restart of web, workers, beat (all read it) | Env-only; fine |
| AWS key pair (S3 + SES) | Every 90 days or on leak | Media upload/download and all email | One pair for both services; recommend two least-privilege IAM principals and role-based credentials (no static keys) on the host |
| Redis | When a password is introduced | Broker URL in every Celery process | No auth today (SEC-11) |
| Gallery password / PIN | Photographer's choice | Password change deletes every `ClientSession` of the gallery (`apps/galleries/views.py:500-537`); PIN change invalidates download tokens via the fingerprint (`download_access.py:340-372`) | Implemented |
| Photographer password | User choice / reset | Revokes every refresh token (`apps/users/views.py:555-563`, `apps/users/serializers.py:260-275`); access tokens live up to 15 min | Implemented |
| Dev DB password in history | Only if that value is used outside local dev, or the remote is public | — | Owner decision (debt row 87) |

### 7.1 Rotating `SECRET_KEY` (runbook, 7-B, debt row 88)

Since 7-B: `SECRET_KEY_FALLBACKS` is read from the environment (comma-separated, `base.py`), and JWTs are signed with their own
`JWT_SIGNING_KEY` (falls back to `SECRET_KEY` when unset, `SIMPLE_JWT['SIGNING_KEY']`). Django verifies `signing` values (download,
job-link and file tokens, password-reset links) with the current key **or** a fallback, and signs only with the current key
(`backend/apps/users/tests/test_security_7b.py::KeyRotationSettingsTests`).

1. Generate a new key: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
2. Deploy with `SECRET_KEY=<new>` and `SECRET_KEY_FALLBACKS=<old>` on **every** process (web, Celery worker, websize worker, beat) at once.
   Emailed ready links (job TTL 7 days) and reset links keep working; new ones use the new key.
3. Set `JWT_SIGNING_KEY` once (if it is unset, JWTs follow `SECRET_KEY`: step 2 then logs everyone out once; SimpleJWT has no
   fallback list). Rotate `JWT_SIGNING_KEY` on its own when needed: everyone signs in again, nothing else breaks.
4. After the longest-lived signed value has expired (7 days: ready links), remove the old key from `SECRET_KEY_FALLBACKS` and redeploy.
5. On a suspected **leak**, skip the fallback (step 2 without `SECRET_KEY_FALLBACKS`) and rotate `JWT_SIGNING_KEY` too: every link and
   session made with the leaked key must die now.

Still open (13-C, row 88): separate IAM principals for S3 and SES, and a secret manager instead of env files.

### 7.2 Django admin: throttle now, MFA plan (7-B, debt row 90)

Done in 7-B: `/admin/login/` goes through `apps/core/admin_login.py` (failed sign-ins per address and per account, in the shared
cache; the form answers 429 for the rest of the window, even to the right password), and the admin never renders gallery
password/PIN hashes or unlock-token hashes.

MFA plan (not built; needs a dependency decision by the owner): `django-otp` with the TOTP device plugin, `OTPAdminSite` as
`admin.site`, a TOTP device enrolled for every staff user before the switch (a management command prints the provisioning URI once),
and static backup codes kept offline. Until then: staff accounts use long unique passwords, and the production proxy restricts
`/admin/` to the operators' addresses (`allow <office/VPN>; deny all;`).

---

## 8. Findings (Severity → Evidence → Risk → Location → Why → Fix)

**S-1 (SEC-10) — `backend/.env` copied into the backend image**
- Severity: Medium · Classification: Needs verification
- Evidence: no `backend/.dockerignore`; `backend/Dockerfile:50` `COPY . .`; `backend/.env` exists in the build context.
- Risk: dev `SECRET_KEY` and DB credentials (and local `media/`, `logs/`, `venv/`) readable from any copy of the image.
- Location: `backend/Dockerfile:50`.
- Why it matters: images get pushed to registries and CI caches that more people can read than the source repo.
- Fix: add `backend/.dockerignore`; inspect the next image's layers. Debt row 86. **Confirmed and fixed in 7-B**: the image built from the old context held `/app/.env` (with its `SECRET_KEY=` line) and `/app/logs/django.log`; an image built with `backend/.dockerignore` has no `.env`, `venv/`, `media/`, `logs/`, `celerybeat-schedule` or `C:` (checked with `docker run ... ls`).

**S-2 (SEC-13) — single signing key, no rotation path**
- Severity: Medium · Classification: Missing control
- Evidence: `base.py:14, 132-142`; `download_access.py:348-460`; no `SECRET_KEY_FALLBACKS`.
- Risk: key leak = forge any user's JWT and any gallery's download token; rotation = global logout and dead email links.
- Fix: separate JWT signing key, `SECRET_KEY_FALLBACKS`, rotation runbook. Debt row 88. **Done in 7-B** (§7.1); the IAM split stays with 13-C.

**S-3 (SEC-11) — dev DB password hardcoded and in history**
- Severity: Low · Classification: Weakness
- Evidence: `docker-compose.yml:38, 84, 129, 163, 193`; `development.py:14`; history from `0f370db`.
- Risk: trivial DB access on any network that reaches a dev machine's published `5432`.
- Fix: untracked env file, `127.0.0.1` port bindings. Debt row 87.

**S-4 (SEC-14) — unlock tokens in plaintext and in URLs**
- Severity: Low · Classification: Weakness
- Evidence: `apps/clients/models.py:61`; `apps/clients/admin.py:37`; `?token=` handling in `apps/clients/views.py`.
- Fix: hash at rest; header-only transport where possible. Debt row 89. **Hashed at rest in 7-B**; the `?token=` transport remains for `<a href>` / `<video src>` (debt row 133).

**S-5 (SEC-25/26) — secret hygiene in docs, history and tooling**
- Severity: Info · Classification: Weakness
- Evidence: `docs/qa-1r5e/qa-script.js:1, 11, 12`; `aecfb94:backend/.env.example:L10`; `test_s3_connection.py:49`.
- Fix: read QA values from env; confirm the old example key was never deployed; print only the object key in the S3 test. Debt row 102.

**S-6 — one AWS key pair for S3 and SES**
- Severity: Low · Classification: Recommendation
- Evidence: `production.py:130-136`.
- Fix: separate IAM users/roles scoped to `s3:*Object` on one bucket and `ses:SendRawEmail` on the verified identity. Folded into debt row 88.

No **Confirmed vulnerability** for secrets: no real credential for any external service was found in the tree or the history.
