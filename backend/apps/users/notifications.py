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
  - payments   -> a manual payment was submitted / approved / rejected
                  (apps/subscriptions/payments.py)
  The plan-expiring and plan-ended mails of the daily lifecycle job follow the same
  "payments" preference (apps/subscriptions/lifecycle.py).

Every mail is one of the shared templates of apps/core/emailing.py (7.5-D): the task carries a
template KEY and a flat context of plain values, never a subject or a body, so no user text can
become a header. Delivery is a Celery task that re-reads the user, so a preference switched
off after the event was queued still wins. Activity alerts are COALESCED per
gallery (one email per window) — a client pulling 40 photos must not produce
40 emails. Sending never raises into the request that triggered it.
"""
import functools
import logging

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from apps.core.emailing import EMAILS, app_url, billing_url, format_date, send_email

logger = logging.getLogger(__name__)

PREFERENCE_FIELD = {
    'downloads': 'notify_downloads',
    'favorites': 'notify_favorites',
    'payments': 'notify_payments',
}
ACTIVITY_COALESCE_SECONDS = 15 * 60


def _wants(user, kind):
    return bool(user.is_active and getattr(user, PREFERENCE_FIELD[kind], False))


def queue_notification(user, kind, template, context, dedupe_key=None, dedupe_seconds=0):
    """
    Queues one email (shared template `template`, flat `context`) if `user` has `kind` switched on.
    Returns True if queued.
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
                send_notification_email.delay(user_id, kind, template, context)
            except Exception:
                logger.exception('Could not dispatch %s notification for user_id=%s', kind, user_id)

        transaction.on_commit(dispatch)
        return True
    except Exception:
        logger.exception('Could not queue %s notification for user_id=%s', kind, getattr(user, 'pk', None))
        return False


def deliver_notification(user_id, kind, template, context):
    """Task body: re-check the preference against fresh data, then send. An unknown template is dropped."""
    from .models import User

    if template not in EMAILS:
        logger.error('Notification email dropped: unknown template for %s notification', kind)
        return False
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None or not _wants(user, kind):
        return False
    send_email(template, user.email, context)
    return True


# ─── message builders ────────────────────────────────────────────────────────

def _never_raises(builder):
    """A builder runs inside the request or the staff action that recorded the event: its failure is logged, not raised."""
    @functools.wraps(builder)
    def wrapper(*args, **kwargs):
        try:
            return builder(*args, **kwargs)
        except Exception as exc:
            logger.error('Could not build the %s email (%s)', builder.__name__, type(exc).__name__)
            return None
    return wrapper


def _activity_url(gallery, tab):
    return app_url(f'/dashboard/galleries/{gallery.slug}/activities?tab={tab}')


@_never_raises
def notify_download(download_log):
    gallery = download_log.gallery
    who = download_log.email or 'A client'
    if download_log.download_type == 'gallery':
        what = f'the "{download_log.photo_set.name}" set' if download_log.photo_set_id else 'the full collection'
    else:
        what = 'a video' if download_log.download_type == 'video' else 'a photo'
    queue_notification(
        gallery.photographer, 'downloads', 'notify_download',
        {
            'who': who, 'what': what, 'gallery_title': gallery.title,
            'activity_url': _activity_url(gallery, 'downloads'),
            'window_minutes': ACTIVITY_COALESCE_SECONDS // 60,
        },
        dedupe_key=f'download:{gallery.pk}', dedupe_seconds=ACTIVITY_COALESCE_SECONDS,
    )


@_never_raises
def notify_favorite(favorite):
    gallery = favorite.gallery
    who = favorite.email or 'A client'
    queue_notification(
        gallery.photographer, 'favorites', 'notify_favorite',
        {
            'who': who, 'gallery_title': gallery.title,
            'activity_url': _activity_url(gallery, 'favorites'),
            'window_minutes': ACTIVITY_COALESCE_SECONDS // 60,
        },
        dedupe_key=f'favorite:{gallery.pk}', dedupe_seconds=ACTIVITY_COALESCE_SECONDS,
    )


def _money(payment):
    return f'{payment.currency} {payment.amount:,.0f}'


@_never_raises
def notify_payment_submitted(payment):
    """After a user submits a manual payment (apps/subscriptions/payments.py): "we received your payment"."""
    queue_notification(
        payment.user, 'payments', 'payment_received',
        {'plan_name': payment.plan.name, 'amount': _money(payment), 'billing_url': billing_url()},
    )


@_never_raises
def notify_payment_reviewed(payment):
    """Called after staff approve / reject a ManualPayment (apps/subscriptions/payments.py)."""
    if payment.status == 'approved':
        template = 'payment_approved'
        context = {
            'plan_name': payment.plan.name,
            'until': format_date(payment.period_end) if payment.period_end else '',
        }
    else:
        template = 'payment_rejected'
        context = {'plan_name': payment.plan.name, 'reason': payment.rejection_reason or ''}
    context['billing_url'] = billing_url()
    queue_notification(payment.user, 'payments', template, context)


def queue_staff_payment_alert(payment):
    """
    One email to settings.STAFF_ALERT_EMAIL (empty = none; the staff bell still works) when a payment waits
    for review. It names the payment id, the plan, the amount and the staff page, and nothing else: no proof
    link, no reference, no notes, no user. Sent after the surrounding transaction commits; never raises.
    """
    try:
        if not settings.STAFF_ALERT_EMAIL:
            return False
        from .tasks import send_staff_alert_email
        context = {
            'payment_id': str(payment.pk), 'plan_name': payment.plan.name, 'amount': _money(payment),
            'staff_url': app_url('/dashboard/staff/payments'),
        }

        def dispatch():
            try:
                send_staff_alert_email.delay('staff_payment_alert', context)
            except Exception:
                logger.exception('Could not dispatch the staff payment alert')

        transaction.on_commit(dispatch)
        return True
    except Exception:
        logger.exception('Could not queue the staff payment alert')
        return False


def deliver_staff_alert(template, context):
    """Task body: sends one staff alert to the ONE env-configured address (read at send time)."""
    if template not in EMAILS or not settings.STAFF_ALERT_EMAIL:
        return False
    send_email(template, settings.STAFF_ALERT_EMAIL, context)
    return True
