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

    Deliberately mirrors MySubscriptionView.get()'s self-heal logic
    exactly (same two field writes). That lazy check is left in place
    on purpose as a fast path for the common case — a user who reloads
    their dashboard gets flipped instantly rather than waiting for the
    next sweep interval. Both paths are idempotent no-ops on a
    subscription the other one already handled, so leaving both active
    is safe.
    """
    from apps.subscriptions.models import UserSubscription

    now = timezone.now()

    try:
        # select_related('user') avoids an N+1 — we write user.is_active_plan
        # below for every row in this queryset.
        expired_qs = (
            UserSubscription.objects
            .select_related('user')
            .filter(status=UserSubscription.SubscriptionStatus.ACTIVE, expires_at__lt=now)
        )

        swept_count = 0
        for subscription in expired_qs:
            subscription.status = UserSubscription.SubscriptionStatus.EXPIRED
            subscription.save(update_fields=['status'])

            user = subscription.user
            if user.is_active_plan:
                user.is_active_plan = False
                user.save(update_fields=['is_active_plan'])

            swept_count += 1

        if swept_count:
            logger.info(f"[sweep_expired_subscriptions] Expired {swept_count} subscription(s).")
        else:
            logger.info("[sweep_expired_subscriptions] No expired subscriptions found.")

        return swept_count

    except Exception as exc:
        logger.error(f"[sweep_expired_subscriptions] Sweep failed: {str(exc)}")
        raise self.retry(exc=exc)