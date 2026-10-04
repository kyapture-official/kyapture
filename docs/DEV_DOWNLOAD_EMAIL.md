# Dev: download-ready email, Mailpit and the Celery worker

The "your photos are ready" email (Task 1R.5-C/E) is sent by the `send_download_ready_email`
Celery task. In the Docker dev stack it is delivered to **Mailpit**, a catcher that shows the
mail and delivers nothing.

## Commands

```bash
# Start / rebuild the whole stack (does not touch the db/redis/media volumes)
docker compose up -d --build

# A Celery worker only knows the tasks it had when it started. After pulling or editing
# task code (backend/apps/*/tasks.py, ready_email.py, download_jobs.py), recreate it:
docker compose up -d --force-recreate --no-deps celery_worker
# (backend/ is bind-mounted, so the `backend` web container sees edits immediately;
#  only the worker needs the recreate. Recreating `backend` kills a test run inside it.)

# Frontend changes are served by the nginx image on http://localhost:3000:
docker compose build frontend && docker compose up -d --no-deps frontend
```

- **Mailpit inbox:** http://localhost:8025 (API: `http://localhost:8025/api/v1/messages`).
  SMTP is `mailpit:1025` inside the compose network; `backend` and `celery_worker` already
  point at it (`EMAIL_BACKEND`/`EMAIL_HOST`/`EMAIL_PORT` in `docker-compose.yml`).
- Outside compose the dev settings use the console backend: the mail is printed in the log.
- The app origin put in the email link is `FRONTEND_URL` (compose: `http://localhost:3000`).

## What the worker logs

Every outcome of the ready email is one INFO line (`docker compose logs -f celery_worker backend`):

| line | meaning |
| --- | --- |
| `Download-ready email for job <id>: queued` | task handed to Celery |
| `... sent` | handed to the mail backend |
| `... skipped (no email)` | the visitor gave no address |
| `... skipped (already sent)` | one email per job |
| `... skipped (email\|ip\|gallery rate limit)` | hourly limit reached (visitor sees nothing different) |
| `... skipped (job not ready)` / `(job not found)` | job changed or was purged first |
| `... failed` / `failed (could not queue)` | exception logged with traceback; the job is unaffected |

## Rate limits

Per hour, per recipient / requesting IP / gallery:

| | per email | per IP | per gallery |
| --- | --- | --- | --- |
| production (`settings/base.py`) | 5 | 10 | 30 |
| development (`settings/development.py`) | 50 | 100 | 300 |

Override with `DOWNLOAD_READY_EMAIL_LIMIT_PER_EMAIL|IP|GALLERY` in the environment.

## The ready link on a password-protected gallery (Task 1R.5-E)

`/g/{user}/{slug}/download/file/{job}?key=...` opens and downloads **from the key alone**, even in a
fresh browser with no gallery unlock. The key is bound to one job of one gallery and is issued only
by the authorized prepare call (gallery password + PIN/email were checked then). It exposes only that
job's files plus the gallery title and studio name; a forged, expired or other-gallery key shows the
friendly "Download expired" page. Without a key, a protected gallery shows the password gate and then
continues to the download page.
