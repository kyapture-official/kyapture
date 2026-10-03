#!/usr/bin/env python
"""
Production entrypoint shared by every Django-based container in this
project (the gunicorn web process, the Celery worker, and Celery beat —
docker-compose.yml builds all three from this same image and only
overrides `command`, never `entrypoint`).

WHY THIS EXISTS: the Phase 3 "gallery list/create 500" production
incident was caused by migrations existing in the repository but never
being applied to the database the running process actually talked to.
Nothing in the previous Dockerfile/compose setup guaranteed migrations
ran before a process started serving requests or consuming tasks. This
script enforces the required sequence for every container that starts
from this image:

    database available -> migrations applied -> real command starts

Concurrency: web, worker, and beat (and any horizontally-scaled replica
of any of them) all run this same script on startup, which would
otherwise mean multiple processes racing `manage.py migrate`'s
CREATE TABLE/ALTER TABLE statements against each other. A single
Postgres session-level advisory lock (pg_advisory_lock) serializes
this cheaply with no extra infrastructure: whoever gets the lock first
actually runs migrate; everyone else blocks until it's done, then runs
migrate too — which is now a fast no-op ("No migrations to apply")
since Django migrations are idempotent by design.

If migration fails, this script exits non-zero WITHOUT execing the real
command — gunicorn/celery never starts, so a failed migration can never
result in a container silently serving traffic against a broken or
half-migrated schema.
"""
import os
import sys
import time
import subprocess

import psycopg2

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# A fixed, arbitrary 63-bit key for Postgres advisory locking. Any two
# processes calling pg_advisory_lock with the SAME key block each other;
# the value itself has no meaning beyond "identifies this app's
# migration lock" and must just stay constant across the deployment.
MIGRATION_LOCK_KEY = 875219004417

DB_WAIT_TIMEOUT_SECONDS = int(os.getenv("DB_WAIT_TIMEOUT_SECONDS", "60"))
DB_WAIT_INTERVAL_SECONDS = 2


def _connect():
    return psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT, connect_timeout=5,
    )


def wait_for_database():
    """
    Blocks until Postgres accepts connections, or exits non-zero after
    DB_WAIT_TIMEOUT_SECONDS. A container that can never reach its
    database must fail loudly and fast, not hang forever or half-start.
    """
    deadline = time.monotonic() + DB_WAIT_TIMEOUT_SECONDS
    last_error = None
    while time.monotonic() < deadline:
        try:
            conn = _connect()
            conn.close()
            print("[entrypoint] Database is available.", flush=True)
            return
        except psycopg2.OperationalError as exc:
            last_error = exc
            print(f"[entrypoint] Database not ready yet ({exc}). Retrying...", flush=True)
            time.sleep(DB_WAIT_INTERVAL_SECONDS)
    print(f"[entrypoint] Database never became available: {last_error}", file=sys.stderr, flush=True)
    sys.exit(1)


def run_migrations_with_lock():
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        print("[entrypoint] Acquiring migration lock...", flush=True)
        cur.execute("SELECT pg_advisory_lock(%s);", (MIGRATION_LOCK_KEY,))
        print("[entrypoint] Lock acquired. Running migrations...", flush=True)

        result = subprocess.run(
            [sys.executable, "manage.py", "migrate", "--noinput"],
            check=False,
        )
        if result.returncode != 0:
            print(
                f"[entrypoint] Migration FAILED (exit {result.returncode}). "
                "Refusing to start — this container will not serve traffic "
                "or process tasks against a schema that failed to migrate.",
                file=sys.stderr, flush=True,
            )
            sys.exit(result.returncode)

        print("[entrypoint] Migrations applied successfully.", flush=True)
    finally:
        # Releasing on the same connection that acquired it; closing the
        # connection would also release it, but this is explicit and
        # still cheap even on the failure path above (sys.exit raises
        # SystemExit, which this finally still runs before propagating).
        try:
            cur.execute("SELECT pg_advisory_unlock(%s);", (MIGRATION_LOCK_KEY,))
        except Exception:
            pass
        cur.close()
        conn.close()


def main():
    if not sys.argv[1:]:
        print("[entrypoint] No command supplied to exec.", file=sys.stderr, flush=True)
        sys.exit(1)

    # Opt-out escape hatch for one-off debugging containers
    # (`docker run ... bash`, a management-command shell, etc.) where
    # waiting on the DB / running migrations makes no sense and would
    # just block an interactive session.
    if os.getenv("SKIP_ENTRYPOINT_MIGRATIONS", "").lower() == "true":
        os.execvp(sys.argv[1], sys.argv[1:])

    wait_for_database()
    run_migrations_with_lock()

    print(f"[entrypoint] Starting: {' '.join(sys.argv[1:])}", flush=True)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
