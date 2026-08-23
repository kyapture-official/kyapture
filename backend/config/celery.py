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
}



@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Simple connection-probing task to verify worker execution."""
    print(f'Request: {self.request!r}')