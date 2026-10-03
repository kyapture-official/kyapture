# C:/Users/LENOVO/Desktop/kyapture/backend/config/celery.py
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' command-line program.
# Fallback to local development settings for seamless offline execution.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('config')

# Using a string namespace='CELERY' ensures that Celery will only parse settings
# keys in base.py/development.py/production.py that start with the "CELERY_" prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Automatically scan all registered apps (e.g. apps.photos) for 'tasks.py' files.
app.autodiscover_tasks()

# ─────────────────────────────────────────────────────────────
# CELERY BEAT SCHEDULE (H-5 fix)
# ─────────────────────────────────────────────────────────────
# No periodic tasks existed anywhere in this project before this fix.
# IsSubscribed (apps/core/permissions.py) reads user.is_active_plan as a
# static flag, and until now the only place that flag was ever cleared
# on expiry was MySubscriptionView.get(), which only fires on a live
# request. This schedule closes that gap by running the sweep on a fixed
# interval regardless of frontend activity.
#
# IMPORTANT: this requires a separate `celery -A config beat` process
# running alongside the existing worker — see docker-compose.yml's new
# celery_beat service below. Beat and worker are always separate OS
# processes in Celery; nothing in this schedule fires unless that beat
# process is actually started.

app.conf.beat_schedule = {
    'sweep-expired-subscriptions': {
        'task': 'apps.subscriptions.tasks.sweep_expired_subscriptions',
        'schedule': crontab(minute='*/15'),  # every 15 minutes
    },
    # Phase 4 (F-30 storage-leak fix) — hard-deletes galleries past their
    # trash retention window (see Gallery.trashed_at / GALLERY_TRASH_RETENTION_DAYS).
    # Daily is plenty: this is a retention-window sweep, not a
    # time-sensitive gate like the subscription check above.
    'purge-trashed-galleries': {
        'task': 'apps.galleries.tasks.purge_trashed_galleries',
        'schedule': crontab(hour=3, minute=0),  # once daily, off-peak
    },
    # Phase 4 (auth hardening) — purges expired ClientSession rows past
    # CLIENT_SESSION_TTL_DAYS. See apps/clients/tasks.py.
    'purge-expired-client-sessions': {
        'task': 'apps.clients.tasks.purge_expired_client_sessions',
        'schedule': crontab(hour=3, minute=15),  # staggered after the gallery purge above
    },
    # Phase 4 (DB cleanup) — trims DownloadLog rows past
    # DOWNLOAD_LOG_RETENTION_DAYS. Purely operational housekeeping.
    'purge-old-download-logs': {
        'task': 'apps.clients.tasks.purge_old_download_logs',
        'schedule': crontab(hour=3, minute=30, day_of_week='sunday'),  # weekly
    },
    # Prepared gallery/set ZIPs: deletes expired jobs and their stored files.
    'purge-expired-download-jobs': {
        'task': 'apps.clients.tasks.purge_expired_download_jobs',
        'schedule': crontab(minute=10),  # hourly
    },
    # Dashboard-bell housekeeping: notifications are pointers, not history.
    'purge-old-notifications': {
        'task': 'apps.users.tasks.purge_old_notifications',
        'schedule': crontab(hour=4, minute=30),  # daily, off-peak
    },
    # Phase 4 (DB cleanup, "token blacklist growth") — flushes expired
    # rows from simplejwt's OutstandingToken/BlacklistedToken tables,
    # which otherwise grow forever. See apps/users/tasks.py.
    'flush-expired-jwt-tokens': {
        'task': 'apps.users.tasks.flush_expired_jwt_tokens',
        'schedule': crontab(hour=4, minute=0, day_of_week='sunday'),  # weekly
    },
}



@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Simple connection-probing task to verify worker execution."""
    print(f'Request: {self.request!r}')