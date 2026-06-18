import os
from celery import Celery

# Set the default Django settings module for the 'celery' command-line program.
# Fallback to local development settings for seamless offline execution.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('config')

# Using a string namespace='CELERY' ensures that Celery will only parse settings
# keys in base.py/development.py/production.py that start with the "CELERY_" prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Automatically scan all registered apps (e.g. apps.photos) for 'tasks.py' files.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Simple connection-probing task to verify worker execution."""
    print(f'Request: {self.request!r}')