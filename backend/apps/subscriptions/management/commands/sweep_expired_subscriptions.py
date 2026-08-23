# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/management/commands/sweep_expired_subscriptions.py
from django.core.management.base import BaseCommand
from apps.subscriptions.tasks import sweep_expired_subscriptions


class Command(BaseCommand):
    """
    Manually runs the same sweep the Celery Beat schedule triggers every
    15 minutes in production. Useful for local testing without needing
    `celery -A config beat` and a worker both running.

    Calling the task directly (not via .delay()/.apply_async()) executes
    it synchronously in this process, regardless of CELERY_TASK_ALWAYS_EAGER —
    that setting only affects calls made through the broker-dispatch path.
    """
    help = "Expires any UserSubscription past its expires_at and clears the user's is_active_plan flag."

    def handle(self, *args, **options):
        count = sweep_expired_subscriptions()
        self.stdout.write(self.style.SUCCESS(f"Swept {count} expired subscription(s)."))