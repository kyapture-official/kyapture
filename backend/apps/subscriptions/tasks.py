# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/tasks.py
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sweep_expired_subscriptions(self):
    """
    Periodic Celery Beat task — see config/celery.py's beat_schedule.

    WHY THIS EXISTS:
    MySubscriptionView.get() (this app's views.py) was previously the ONLY
    place that flipped UserSubscription.status to 'expired' and
    User.is_active_plan to False once expires_at had passed — and it only
    ran when a photographer's frontend session happened to call
    GET /api/v1/subscriptions/my-subscription/. IsSubscribed
    (apps/core/permissions.py), the permission gate on gallery and photo
    creation, checks request.user.is_active_plan directly rather than
    live subscription status. A user whose session never re-triggered
    that lazy check could keep creating galleries and uploading photos
    past their paid period indefinitely.

    This task proactively sweeps every UserSubscription row still marked
    'active' whose expires_at has passed, and flips both the subscription
    status and the user's is_active_plan flag — independent of whether or
    when that user's frontend ever hits /my-subscription/.

    MySubscriptionView.get() runs the same flip (lifecycle.expire_lapsed) as a fast
    path for a user who reloads their dashboard. Both are idempotent no-ops on a
    subscription the other one already handled. Neither is what ENDS access: an
    ended period is Free at request time (entitlements.py), job or no job. The
    reminder / downgrade / mail work is the daily run_subscription_lifecycle below.
    """
    from apps.subscriptions.lifecycle import expire_lapsed
    from apps.subscriptions.models import UserSubscription

    now = timezone.now()

    try:
        # Each row is flipped by expire_lapsed(), which takes the user and subscription row locks and re-reads
        # the status inside them (7.5-C): a renewal approved while this loop ran is never written back to
        # 'expired'. The old version saved without a lock and could do exactly that.
        expired_ids = list(
            UserSubscription.objects
            .filter(status=UserSubscription.SubscriptionStatus.ACTIVE, expires_at__lt=now)
            .values_list('pk', flat=True)
        )

        swept_count = 0
        for subscription_id in expired_ids:
            if expire_lapsed(subscription_id, now):
                swept_count += 1

        if swept_count:
            logger.info(f"[sweep_expired_subscriptions] Expired {swept_count} subscription(s).")
        else:
            logger.info("[sweep_expired_subscriptions] No expired subscriptions found.")

        return swept_count

    except Exception as exc:
        logger.error(f"[sweep_expired_subscriptions] Sweep failed: {str(exc)}")
        raise self.retry(exc=exc)


@shared_task(ignore_result=True)
def run_subscription_lifecycle():
    """
    The daily subscription job (7.5-C; beat entry "subscription-lifecycle-daily" in settings.CELERY_BEAT_SCHEDULE).
    All of the work and its rules are in apps/subscriptions/lifecycle.py; `manage.py run_subscription_lifecycle`
    runs the same code by hand. Not retried by Celery: a failed mail is released and retried by the next run, and
    a second run is always safe.
    """
    from apps.subscriptions import lifecycle
    report = lifecycle.run()
    return {'skipped': report['skipped'], 'reminders': len(report['reminders']), 'downgrades': len(report['downgrades'])}
