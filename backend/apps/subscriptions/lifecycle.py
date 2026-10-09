# backend/apps/subscriptions/lifecycle.py
"""
Subscription lifecycle (chunk 7.5-C): the daily job that reminds an owner before a paid period ends and moves
the account to Free after it (and its grace) has ended. It reuses what 7.5-B built and adds no second system:

  access        entitlements.py alone decides who may use a paid feature, and it already treats an ended period
                as Free AT REQUEST TIME. So access never waits for this job, and a dead beat process cannot
                extend a plan. This module only does the paperwork around the end of a period.
  reminder      once per period, `reminder_days` calendar days before the end: a bell notification and an email
                ("Your plan ends on <date>", template plan_expiring).
  downgrade     once per period, after `grace_days` full days past the end: status -> expired, the legacy
                `is_active_plan` flag off, one audit row (no actor), a bell notification and an email
                (template plan_ended: the plan HAS ended, the account is on Free).
                NOTHING is deleted: files, galleries, settings, watermark and branding values all stay, so an
                upgrade restores them.
  tuning        the two day counts are the LifecycleSettings row (admin), never code.

A "day" is a calendar day in settings.BILLING_TIME_ZONE (Asia/Kathmandu). The reminder is due from the START of the
local day that is `reminder_days` before the end's local date; the downgrade is due from the start of the local day
after (end date + grace_days). So a period ending Oct 10 18:00 with grace 3 is downgraded by the run at/after
Oct 14 00:00 Kathmandu time, never on Oct 13 23:59.

Safe to run twice and from two places at once:
  * a cache lock makes a second runner skip (`skipped='locked'`);
  * under it, every row is processed in its own transaction that takes the USER row, then the SUBSCRIPTION row
    (FOR NO KEY UPDATE, the same order approve_payment uses, so the two cannot deadlock) and re-reads everything
    inside the lock; a marker that is already set means the step is done;
  * a mail is CLAIMED (its marker set) inside that transaction, sent after it commits, and un-claimed if the send
    fails, so a mail goes out once and a failure is retried by the next run (for settings.SUBSCRIPTION_EMAIL_RETRY_DAYS).
    A process killed between the claim and the send loses that one mail instead of sending it twice (debt row).

Nothing here emails or notifies an account that is suspended (is_active False): its downgrade is still applied.
"""
import logging
import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.emailing import billing_url, format_date, send_email
from apps.users import audit
from apps.users.models import Notification, User
from apps.users.notification_service import record_notification

from .models import LifecycleSettings, UserSubscription

logger = logging.getLogger(__name__)

Status = UserSubscription.SubscriptionStatus
Kind = Notification.Kind
LOCK_KEY = 'subscription-lifecycle:lock'

# ─── the day, in the billing time zone ───────────────────────────────────────


def billing_tz():
    return ZoneInfo(settings.BILLING_TIME_ZONE)


def local_date(moment, tz=None):
    return moment.astimezone(tz or billing_tz()).date()


def day_start(day, tz=None):
    """Midnight at the start of the calendar date `day` in the billing zone (an aware datetime)."""
    return datetime.combine(day, time.min, tzinfo=tz or billing_tz())


def days_until(end, now=None, tz=None):
    """Whole calendar days from today to the local date of `end` (0 = ends today, negative = ended earlier)."""
    tz = tz or billing_tz()
    return (local_date(end, tz) - local_date(now or timezone.now(), tz)).days


def reminder_boundary(now, reminder_days, tz):
    """A period ending BEFORE this instant is inside the reminder window today (start of the day after today + N)."""
    return day_start(local_date(now, tz) + timedelta(days=reminder_days + 1), tz)


def downgrade_cutoff(now, grace_days, tz):
    """A period that ended BEFORE this instant has used up its grace (start of the local day `grace_days` ago)."""
    return day_start(local_date(now, tz) - timedelta(days=grace_days), tz)


def email_window_start(now, grace_days):
    """A period that ended before this is too old to mail about (downgraded silently / retries dropped)."""
    return now - timedelta(days=grace_days + settings.SUBSCRIPTION_EMAIL_RETRY_DAYS)


# ─── what the owner is shown (Billing page, dashboard banner) ────────────────

def describe(subscription, now=None, cfg=None):
    """
    {'state': 'none' | 'active' | 'expiring' | 'expired', 'days_left', 'period_end', 'reminder_days', 'grace_days'}.
    'expiring' = live and inside the reminder window; 'expired' = the period has ended (whether or not the job has
    run yet: the same rule as every entitlement). `days_left` is calendar days in the billing zone (0 = today).
    """
    now = now or timezone.now()
    cfg = cfg or LifecycleSettings.load()
    base = {'state': 'none', 'days_left': None, 'period_end': None,
            'reminder_days': cfg.reminder_days, 'grace_days': cfg.grace_days}
    if subscription is None or subscription.status not in (Status.ACTIVE, Status.EXPIRED):
        return base
    base['period_end'] = subscription.expires_at
    base['days_left'] = days_until(subscription.expires_at, now)
    if subscription.status == Status.ACTIVE and subscription.expires_at > now:
        base['state'] = 'expiring' if base['days_left'] <= cfg.reminder_days else 'active'
    else:
        base['state'] = 'expired'
    return base


# ─── the text ────────────────────────────────────────────────────────────────
# The bell text lives here; the email wording lives in the shared templates (apps/core/templates/emails/
# plan_expiring.* and plan_ended.*, 7.5-D). Dates are always the billing-zone date (format_date).

def _when(days):
    return 'today' if days <= 0 else 'tomorrow' if days == 1 else f'in {days} days'


def reminder_bell(plan_name, end, now):
    return f'Your {plan_name} plan expires {_when(days_until(end, now))} ({format_date(end)}). Renew to keep it.'


def downgrade_bell(plan_name, end):
    return f'Your {plan_name} plan ended on {format_date(end)}. You are on the Free plan now. Your files are kept.'


def _email_context(template, plan_name, end, now):
    context = {'plan_name': plan_name, 'end_date': format_date(end), 'billing_url': billing_url()}
    if template == 'plan_expiring':
        context['when'] = _when(days_until(end, now))
    return context


# ─── locks ───────────────────────────────────────────────────────────────────

def _lock_rows(subscription_id, user_id):
    """User row, then subscription row (approve_payment's order), both FOR NO KEY UPDATE; (user, sub) or (None, None)."""
    user = User.objects.select_for_update(no_key=True).filter(pk=user_id).first()
    sub = (
        UserSubscription.objects.select_for_update(no_key=True, of=('self',))
        .select_related('plan').filter(pk=subscription_id, user_id=user_id).first()
    ) if user else None
    return (user, sub) if sub else (None, None)


def expire_lapsed(subscription_id, now=None):
    """
    Marks a subscription whose period has ended as 'expired' and clears the legacy flag: True when it changed.
    Under the row locks and with the status re-read inside them: a renewal approved a moment earlier is never
    overwritten (the old sweep and the my-subscription self-heal wrote without a lock and could do exactly that).
    """
    now = now or timezone.now()
    with transaction.atomic():
        user_id = UserSubscription.objects.filter(pk=subscription_id).values_list('user_id', flat=True).first()
        if user_id is None:
            return False
        user, sub = _lock_rows(subscription_id, user_id)
        if sub is None or sub.status != Status.ACTIVE or sub.expires_at >= now:
            return False
        sub.status = Status.EXPIRED
        sub.save(update_fields=['status', 'updated_at'])
        if user.is_active_plan:
            user.is_active_plan = False
            user.save(update_fields=['is_active_plan'])
        return True


# ─── mail ────────────────────────────────────────────────────────────────────

def _wants_email(user):
    """The same rule as every billing mail: an active account with the "payments" email preference on."""
    return bool(user.is_active and user.notify_payments)


def _send(to, template, plan_name, end, now):
    send_email(template, to, _email_context(template, plan_name, end, now))


def _deliver(subscription_id, user_id, marker, end, to, template, plan_name, now):
    """
    Sends one claimed mail; on failure releases the claim (under the lock, only if it is still this period's)
    so the next run tries again. Returns True when it was sent.
    """
    try:
        _send(to, template, plan_name, end, now)
        return True
    except Exception:
        logger.error('Lifecycle mail (%s) failed for subscription %s; it will be retried', marker, subscription_id,
                     exc_info=True)
    try:
        with transaction.atomic():
            _user, sub = _lock_rows(subscription_id, user_id)
            if sub is not None and getattr(sub, marker) == end:
                setattr(sub, marker, None)
                sub.save(update_fields=[marker, 'updated_at'])
    except Exception:
        logger.exception('Could not release the %s claim of subscription %s', marker, subscription_id)
    return False


# ─── the steps ───────────────────────────────────────────────────────────────

def _reminder_due(sub, now, cfg, tz):
    return (sub.status == Status.ACTIVE and sub.expires_at > now
            and sub.expires_at < reminder_boundary(now, cfg.reminder_days, tz))


def _downgrade_due(sub, now, cfg, tz):
    return sub.status in (Status.ACTIVE, Status.EXPIRED) and sub.expires_at < downgrade_cutoff(now, cfg.grace_days, tz)


def _unmarked(field):
    """Rows whose `field` is not set for the CURRENT period end."""
    return Q(**{f'{field}__isnull': True}) | ~Q(**{field: F('expires_at')})


def reminder_candidates(now, cfg, tz):
    """(subscription id, user id, email, plan name, period end) rows that still owe a reminder bell or mail."""
    rows = (
        UserSubscription.objects
        .filter(status=Status.ACTIVE, expires_at__gt=now, user__is_active=True, user__deletion_requested_at__isnull=True,
                expires_at__lt=reminder_boundary(now, cfg.reminder_days, tz))
        .filter(_unmarked('reminder_notified_for') | _unmarked('reminder_emailed_for'))
        .select_related('user', 'plan').order_by('expires_at')
    )
    return [(s.pk, s.user_id, s.user.email, s.plan.name, s.expires_at) for s in rows]


def downgrade_candidates(now, cfg, tz):
    """Rows past their grace that still owe the downgrade, or whose downgrade mail is still unsent and recent."""
    recent = Q(expires_at__gte=email_window_start(now, cfg.grace_days))
    rows = (
        UserSubscription.objects
        .filter(status__in=(Status.ACTIVE, Status.EXPIRED), expires_at__lt=downgrade_cutoff(now, cfg.grace_days, tz),
                user__deletion_requested_at__isnull=True)      # 7.5-E: billing stops for an account that is closing
        .filter(_unmarked('downgraded_for') | (_unmarked('downgrade_emailed_for') & recent))
        .select_related('user', 'plan').order_by('expires_at')
    )
    return [(s.pk, s.user_id, s.user.email, s.plan.name, s.expires_at,
             s.downgraded_for != s.expires_at, s.user.is_active) for s in rows]


def process_reminder(subscription_id, user_id, now, cfg, tz):
    """
    One reminder step for one subscription, under the locks. Returns a dict of what was done, or None when nothing
    was due (renewed, expired, suspended or already done meanwhile).
    """
    mail_job = None
    done = {'bell': False, 'email_claimed': False}
    with transaction.atomic():
        user, sub = _lock_rows(subscription_id, user_id)
        if sub is None or not user.is_active or user.deletion_requested_at is not None or not _reminder_due(sub, now, cfg, tz):
            return None
        end = sub.expires_at
        bell = reminder_bell(sub.plan.name, end, now)
        fields = []
        if sub.reminder_notified_for != end:
            if record_notification(user, Kind.PLAN_EXPIRING, None, message=bell) is not None:
                sub.reminder_notified_for = end
                fields.append('reminder_notified_for')
                done['bell'] = True
        if sub.reminder_emailed_for != end:
            sub.reminder_emailed_for = end          # the claim: set now, released if the send fails
            fields.append('reminder_emailed_for')
            if _wants_email(user):
                mail_job = (user.email, 'plan_expiring', sub.plan.name, now)
                done['email_claimed'] = True
        if not fields:
            return None
        sub.save(update_fields=[*fields, 'updated_at'])
    if mail_job and not _deliver(subscription_id, user_id, 'reminder_emailed_for', end, *mail_job):
        done['email_claimed'] = False
        done['email_failed'] = True
    return done


def process_downgrade(subscription_id, user_id, now, cfg, tz):
    """
    One downgrade step for one subscription, under the locks: status -> expired, the legacy flag off, one audit
    row, then (for a live account, and a period that ended recently) the bell and the mail. A failed mail does not
    undo the downgrade. Returns what was done, or None when nothing was due.
    """
    mail_job = None
    done = {'downgraded': False, 'bell': False, 'email_claimed': False}
    with transaction.atomic():
        user, sub = _lock_rows(subscription_id, user_id)
        if sub is None or user.deletion_requested_at is not None or not _downgrade_due(sub, now, cfg, tz):
            return None
        end = sub.expires_at
        recent = end >= email_window_start(now, cfg.grace_days)
        bell = downgrade_bell(sub.plan.name, end)
        fields = []
        if sub.downgraded_for != end:
            sub.status = Status.EXPIRED
            sub.downgraded_for = end
            fields += ['status', 'downgraded_for']
            if user.is_active_plan:
                user.is_active_plan = False
                user.save(update_fields=['is_active_plan'])
            audit.record(
                audit.Action.SUBSCRIPTION_DOWNGRADE, target=user,
                reason=f'plan={sub.plan.key} period_end={end.astimezone(tz):%Y-%m-%d} grace_days={cfg.grace_days}'
                       + ('' if recent else ' silent=old'),
            )
            done['downgraded'] = True
            if user.is_active and recent:
                if record_notification(user, Kind.PLAN_EXPIRED, None, message=bell) is not None:
                    done['bell'] = True
        if sub.downgrade_emailed_for != end and (recent or done['downgraded']):
            sub.downgrade_emailed_for = end         # the claim (also "handled" for a suspended or very old account)
            fields.append('downgrade_emailed_for')
            if user.is_active and recent and _wants_email(user):
                mail_job = (user.email, 'plan_ended', sub.plan.name, now)
                done['email_claimed'] = True
        if not fields:
            return None
        sub.save(update_fields=[*fields, 'updated_at'])
    if mail_job and not _deliver(subscription_id, user_id, 'downgrade_emailed_for', end, *mail_job):
        done['email_claimed'] = False
        done['email_failed'] = True
    return done


# ─── the run ─────────────────────────────────────────────────────────────────

def _acquire():
    token = uuid.uuid4().hex
    return token if cache.add(LOCK_KEY, token, timeout=settings.SUBSCRIPTION_LIFECYCLE_LOCK_SECONDS) else None


def _release(token):
    if cache.get(LOCK_KEY) == token:
        cache.delete(LOCK_KEY)


def run(*, now=None, dry_run=False):
    """
    The whole daily job. Returns a report:
      {'skipped': None | 'locked', 'dry_run', 'reminders': [...], 'downgrades': [...]}
    Each entry names the account (email), the plan and the period end, and what was (or would be) done. A dry run
    reads the same candidates and writes nothing (it does not even take the lock).
    """
    now = now or timezone.now()
    tz = billing_tz()
    cfg = LifecycleSettings.load()
    report = {'skipped': None, 'dry_run': dry_run, 'reminders': [], 'downgrades': [], 'today': local_date(now, tz)}

    token = None
    if not dry_run:
        token = _acquire()
        if token is None:
            report['skipped'] = 'locked'
            logger.info('Subscription lifecycle: another run holds the lock; skipped')
            return report
    try:
        for sub_id, user_id, email, plan_name, end in reminder_candidates(now, cfg, tz):
            entry = {'email': email, 'plan': plan_name, 'period_end': end, 'days_left': days_until(end, now, tz)}
            if dry_run:
                report['reminders'].append({**entry, 'would': 'remind'})
                continue
            done = process_reminder(sub_id, user_id, now, cfg, tz)
            if done:
                report['reminders'].append({**entry, **done})
        for sub_id, user_id, email, plan_name, end, owes_downgrade, active in downgrade_candidates(now, cfg, tz):
            entry = {'email': email, 'plan': plan_name, 'period_end': end, 'suspended': not active}
            if dry_run:
                report['downgrades'].append({**entry, 'would': 'downgrade' if owes_downgrade else 'retry the mail'})
                continue
            done = process_downgrade(sub_id, user_id, now, cfg, tz)
            if done:
                report['downgrades'].append({**entry, **done})
    finally:
        if token:
            _release(token)
    if not dry_run:
        logger.info('Subscription lifecycle: %d reminder(s), %d downgrade(s)',
                    len(report['reminders']), len(report['downgrades']))
    return report
