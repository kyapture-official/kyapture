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
def send_notification_email(self, user_id, kind, template, context):
    """
    Delivers one photographer notification email (see apps/users/notifications.py): a shared template key
    and a flat context, never a subject or a body. Re-checks the user preference at send time; retries
    transient mail failures. The log line names the kind and the exception type only.
    """
    from .notifications import deliver_notification

    try:
        return deliver_notification(user_id, kind, template, context)
    except Exception as exc:
        logger.error("[send_notification_email] %s email for user %s failed (%s)", kind, user_id, type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_staff_alert_email(self, template, context):
    """7.5-D: the "new payment to review" email to the one STAFF_ALERT_EMAIL address."""
    from .notifications import deliver_staff_alert

    try:
        return deliver_staff_alert(template, context)
    except Exception as exc:
        logger.error("[send_staff_alert_email] %s failed (%s)", template, type(exc).__name__)
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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email_task(self, email):
    """
    7-C: the "forgot password" email. Queued for EVERY well-formed address the
    reset endpoint accepts (known or not), so the request itself never touches
    the user table; this task finds out whether the account exists. A retry
    issues a fresh link (the previous one is dropped). Returns nothing that
    could end up in a result backend or a log: no token, no link.
    """
    from .password_reset import send_reset_email

    try:
        send_reset_email(email)
    except Exception as exc:
        logger.exception("[send_password_reset_email] failed; retrying")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_changed_email_task(self, user_id, how):
    """7-C: "your password was changed" to the account address, after a reset or a change."""
    from .password_reset import send_password_changed_email

    try:
        send_password_changed_email(user_id, how)
    except Exception as exc:
        logger.exception("[send_password_changed_email] for user %s failed; retrying", user_id)
        raise self.retry(exc=exc)


# ─── account deletion (7.5-E, apps/users/account_deletion.py) ────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_deletion_requested_email(self, user_id):
    """The "your account is scheduled for deletion" email with a fresh cancel link (the token is made in the task)."""
    from .account_deletion import send_requested_email

    try:
        send_requested_email(user_id)
    except Exception as exc:
        logger.error("[send_deletion_requested_email] for user %s failed (%s); retrying", user_id, type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_account_deleted_email(self, email):
    """The one "your account was deleted" notice, to the address the account had. Queued once, by the final purge step."""
    from .account_deletion import send_deleted_email

    try:
        send_deleted_email(email)
    except Exception as exc:
        logger.error("[send_account_deleted_email] failed (%s); retrying", type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=8, acks_late=True)
def purge_account(self, user_id):
    """
    Owner-less purge of one closing account (no request, no user in the session). Idempotent and resumable:
    it re-checks the status under the row lock, does bounded steps, re-queues itself while there is more to do
    and retries (with backoff) when a file could not be deleted, leaving the rows in place until it can.
    """
    from .account_deletion import run_purge_steps

    outcome = run_purge_steps(user_id)
    if outcome == 'more':
        purge_account.apply_async(args=[user_id], countdown=1)
    elif outcome == 'retry':
        if self.request.retries >= self.max_retries:
            logger.error("[purge_account] giving up for now on user %s: files still cannot be deleted; the sweep resumes it", user_id)
            return outcome
        raise self.retry(countdown=min(30 * 2 ** self.request.retries, 1800))
    return outcome


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sweep_account_deletions(self):
    """Beat: starts every purge that is due and resumes the ones that stalled (a killed worker, a long storage outage)."""
    from .account_deletion import sweep_due

    queued = sweep_due()
    if queued:
        logger.info("[sweep_account_deletions] queued %s purge(s).", queued)
    return queued
