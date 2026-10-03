# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/notifications.py
"""
Photographer email notifications — the only place a notification preference
is turned into an actual email.

Every preference on the User model (notify_downloads / notify_favorites /
notify_payments) has exactly one send path here; there is no preference
without one. Paths:
  - downloads  -> a client downloaded from one of your collections
                  (apps/clients/signals.py, on DownloadLog creation)
  - favorites  -> a client favorited a photo (apps/clients/signals.py)
  - payments   -> a manual payment was approved / rejected
                  (apps/subscriptions/views.py, AdminPaymentReviewView)

Delivery is a Celery task that re-reads the user, so a preference switched
off after the event was queued still wins. Activity alerts are COALESCED per
gallery (one email per window) — a client pulling 40 photos must not produce
40 emails. Sending never raises into the request that triggered it.
"""
import logging

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)

PREFERENCE_FIELD = {
    'downloads': 'notify_downloads',
    'favorites': 'notify_favorites',
    'payments': 'notify_payments',
}
ACTIVITY_COALESCE_SECONDS = 15 * 60


def preferences_url():
    return f"{settings.FRONTEND_URL}/dashboard/settings/notifications"


def _wants(user, kind):
    return bool(user.is_active and getattr(user, PREFERENCE_FIELD[kind], False))


def queue_notification(user, kind, subject, body, dedupe_key=None, dedupe_seconds=0):
    """
    Queues one email if `user` has `kind` switched on. Returns True if queued.
    `dedupe_key` + `dedupe_seconds` suppress repeats of the same alert.
    Safe to call from signal handlers / views: it never raises.
    """
    try:
        if not _wants(user, kind):
            return False
        if dedupe_key and dedupe_seconds:
            if not cache.add(f'notify:{user.pk}:{dedupe_key}', 1, timeout=dedupe_seconds):
                return False

        from .tasks import send_notification_email
        user_id = str(user.pk)

        def dispatch():
            # Runs AFTER the surrounding transaction commits. An exception here
            # (broker down, mail backend misconfigured) would otherwise
            # propagate out of the request that recorded the activity and turn
            # a successful download/favorite into a 500 once the data is
            # already committed — so it is contained and logged instead.
            try:
                send_notification_email.delay(user_id, kind, subject, body)
            except Exception:
                logger.exception('Could not dispatch %s notification for user_id=%s', kind, user_id)

        transaction.on_commit(dispatch)
        return True
    except Exception:
        logger.exception('Could not queue %s notification for user_id=%s', kind, getattr(user, 'pk', None))
        return False


def deliver_notification(user_id, kind, subject, body):
    """Task body: re-check the preference against fresh data, then send."""
    from django.core.mail import send_mail

    from .models import User

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None or not _wants(user, kind):
        return False
    footer = (
        "\n\n—\nYou're receiving this because of your Kyapture notification settings.\n"
        f"Change them any time: {preferences_url()}\n"
    )
    send_mail(
        subject=subject,
        message=body + footer,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    return True


# ─── message builders ────────────────────────────────────────────────────────

def notify_download(download_log):
    gallery = download_log.gallery
    who = download_log.email or 'A client'
    if download_log.download_type == 'gallery':
        what = f'the "{download_log.photo_set.name}" set' if download_log.photo_set_id else 'the full collection'
    else:
        what = 'a video' if download_log.download_type == 'video' else 'a photo'
    link = f"{settings.FRONTEND_URL}/dashboard/galleries/{gallery.slug}/activities?tab=downloads"
    queue_notification(
        gallery.photographer, 'downloads',
        subject=f'New download from "{gallery.title}"',
        body=(
            f'{who} downloaded {what} from "{gallery.title}".\n\n'
            f'See the full download activity: {link}\n\n'
            f'(You get at most one of these emails per collection every '
            f'{ACTIVITY_COALESCE_SECONDS // 60} minutes.)'
        ),
        dedupe_key=f'download:{gallery.pk}', dedupe_seconds=ACTIVITY_COALESCE_SECONDS,
    )


def notify_favorite(favorite):
    gallery = favorite.gallery
    who = favorite.email or 'A client'
    link = f"{settings.FRONTEND_URL}/dashboard/galleries/{gallery.slug}/activities?tab=favorites"
    queue_notification(
        gallery.photographer, 'favorites',
        subject=f'New favorite in "{gallery.title}"',
        body=(
            f'{who} marked a photo as a favorite in "{gallery.title}".\n\n'
            f'See favorite activity: {link}\n\n'
            f'(You get at most one of these emails per collection every '
            f'{ACTIVITY_COALESCE_SECONDS // 60} minutes.)'
        ),
        dedupe_key=f'favorite:{gallery.pk}', dedupe_seconds=ACTIVITY_COALESCE_SECONDS,
    )


def notify_payment_reviewed(payment):
    """Called after an admin approves/rejects a ManualPayment."""
    approved = payment.status == 'approved'
    billing = f"{settings.FRONTEND_URL}/dashboard/billing"
    if approved:
        subject = f'Your {payment.plan.name} plan payment was approved'
        body = f'Your payment for the {payment.plan.name} plan was approved and your plan is now active.\n\nBilling: {billing}'
    else:
        subject = f'Your {payment.plan.name} plan payment could not be approved'
        reason = f'\n\nNote from our team: {payment.notes}' if payment.notes else ''
        body = (
            f'We could not approve your payment for the {payment.plan.name} plan.{reason}\n\n'
            f'You can submit a new receipt from Billing: {billing}'
        )
    queue_notification(payment.user, 'payments', subject=subject, body=body)
