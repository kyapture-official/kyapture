# backend/apps/users/tasks.py
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def flush_expired_jwt_tokens(self):
    """
    Periodic Celery Beat task — see config/celery.py's beat_schedule.

    Phase 4 (DB cleanup, "token blacklist growth"): rest_framework_simplejwt's
    token_blacklist app (INSTALLED_APPS) records one OutstandingToken row
    per refresh token ever issued — every login, every refresh (Phase 4's
    F-36 fix now actually mints a new one on every rotation instead of
    reusing the same row) — and one BlacklistedToken row per token
    that's ever been explicitly revoked (logout, password change/reset —
    see apps/users/utils.py). Neither table had any cleanup before this,
    so both grow forever.

    `flushexpiredtokens` is simplejwt's own built-in management command
    for exactly this: it deletes OutstandingToken rows (and their
    matching BlacklistedToken row, via the DB cascade) once their
    `expires_at` has passed — safe by construction, since an expired
    token is already rejected by TokenError regardless of whether its
    row still exists. Wrapping it in a Celery task (rather than a cron
    entry calling manage.py directly) keeps every scheduled job in this
    project going through the same Celery Beat mechanism.
    """
    from django.core.management import call_command

    try:
        call_command('flushexpiredtokens')
        logger.info("[flush_expired_jwt_tokens] Completed.")
    except Exception as exc:
        logger.error(f"[flush_expired_jwt_tokens] Failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_notification_email(self, user_id, kind, subject, body):
    """
    Delivers one photographer notification email (see apps/users/notifications.py).
    Re-checks the user preference at send time; retries transient mail failures.
    """
    from .notifications import deliver_notification

    try:
        return deliver_notification(user_id, kind, subject, body)
    except Exception as exc:
        logger.exception("[send_notification_email] %s email for user %s failed", kind, user_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def purge_old_notifications(self):
    """
    Keeps the dashboard-bell table small. Notifications are pointers, never the
    record of anything (activity lives in DownloadLog/Favorite/...), so pruning
    loses no history: read ones go after 30 days, unread ones after 90.
    """
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from .models import Notification

    now = timezone.now()
    try:
        deleted, _ = Notification.objects.filter(
            Q(is_read=True, updated_at__lt=now - timedelta(days=30))
            | Q(is_read=False, updated_at__lt=now - timedelta(days=90))
        ).delete()
    except Exception as exc:
        logger.error("[purge_old_notifications] Failed: %s", exc)
        raise self.retry(exc=exc)
    logger.info("[purge_old_notifications] Removed %s old notification(s).", deleted)
    return deleted
