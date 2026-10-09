# backend/apps/subscriptions/tests/test_lifecycle_7_5c.py
"""
CHUNK 7.5-C - subscription lifecycle (apps/subscriptions/lifecycle.py).

  - An ended period is Free at REQUEST time, with the daily job never run (access does not wait for it).
  - The daily job: one reminder before the end (bell + email), one downgrade after the end + grace (status,
    audit row, bell, email), nothing deleted; run twice = once; two runners at once = once (cache lock AND row locks).
  - Days are calendar days in the billing zone (Asia/Kathmandu): the boundary is midnight there.
  - Reminder days and grace days are an admin-edited row, not code.
  - A failed email does not stop the downgrade and is retried by the next run; a suspended account is
    downgraded but never mailed or notified.
  - After the downgrade the account behaves as Free (BILL-C upload refusal; clients still view and download at
    the Free level) while every stored Pro setting is kept and comes back on renewal.
"""
import io
import threading
import time
from datetime import datetime, timedelta
from smtplib import SMTPException
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import admin as django_admin
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connections, transaction
from django.test import TransactionTestCase
from django.urls import Resolver404, resolve
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.clients.download_access import effective_high_res_mode
from apps.clients.tests.test_download_access_flow import DownloadFlowBase, _zip_entries
from apps.core.utils import get_user_subscription_metrics
from apps.core.watermark import build_watermark_spec
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.subscriptions import lifecycle, payments
from apps.subscriptions.admin import LifecycleSettingsAdmin
from apps.subscriptions.entitlements import GB, WATERMARK, get_feature_entitlements, has_feature, storage_figures
from apps.subscriptions.models import LifecycleSettings, ManualPayment, SubscriptionPlan, UserSubscription
from apps.subscriptions.tasks import run_subscription_lifecycle, sweep_expired_subscriptions
from apps.subscriptions.testing import ensure_seed_plans, grant_plan
from apps.subscriptions.tests.test_payment_review_7_5b import MediaSandbox, image_bytes, make_user
from apps.users.audit import Action
from apps.users.models import Notification, StaffAuditLog, User
from apps.users.notifications import deliver_notification

NPT = ZoneInfo('Asia/Kathmandu')
Status = UserSubscription.SubscriptionStatus


# The clock tests live in 2040 so they stay in the real future: a period that "ends" there is still live for the
# code that reads the real clock (approve_payment, the sweep), whatever day the suite runs on.
YEAR = 2040


def npt(month, day, hour=0, minute=0, second=0):
    return datetime(YEAR, month, day, hour, minute, second, tzinfo=NPT)


# The period used by the clock tests: it ends Oct 10, 18:00 Kathmandu time.
END = npt(10, 10, 18)


def bells(user, kind):
    return Notification.objects.filter(user=user, kind=kind).count()


def mails_to(user):
    return [m for m in mail.outbox if user.email in m.to]


def downgrade_rows(user=None):
    rows = StaffAuditLog.objects.filter(action=Action.SUBSCRIPTION_DOWNGRADE)
    return rows.filter(target_id=user.pk) if user else rows


def give_period(user, end, plan_key='pro', status=Status.ACTIVE):
    """A subscription on a real plan row ending at `end`, no lifecycle marker set."""
    plan = SubscriptionPlan.objects.get(key=plan_key)
    sub, _ = UserSubscription.objects.update_or_create(user=user, defaults={
        'plan': plan, 'status': status, 'payment_method': UserSubscription.PaymentMethod.MANUAL,
        'starts_at': end - timedelta(days=30), 'expires_at': end,
        **{marker: None for marker in UserSubscription.LIFECYCLE_MARKERS},
    })
    User.objects.filter(pk=user.pk).update(is_active_plan=status == Status.ACTIVE)
    return sub


class LifecycleBase(APITestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.owner = make_user('lifeowner')
        self.pro = SubscriptionPlan.objects.get(key='pro')

    def run_job(self, now, **kwargs):
        return lifecycle.run(now=now, **kwargs)

    def sub(self, user=None):
        return UserSubscription.objects.get(user=user or self.owner)


# ─── access ends with no job ─────────────────────────────────────────────────

class RequestTimeExpiryTests(LifecycleBase):
    def test_an_expired_user_is_free_at_request_time_with_the_job_never_run(self):
        gallery = Gallery.objects.create(photographer=self.owner, title='Late', slug='late-75c')
        give_period(self.owner, timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.sub().status, 'active')                           # nothing flipped it
        self.assertEqual(Notification.objects.count() + StaffAuditLog.objects.count(), 0)   # and no job wrote anything

        flags = get_feature_entitlements(self.owner)
        self.assertEqual((flags['branding'], flags['watermark'], flags['original_download'], flags['plan_name']),
                         (False, False, False, None))
        metrics = get_user_subscription_metrics(self.owner)
        free = SubscriptionPlan.get_free()
        self.assertEqual((metrics['plan_name'], metrics['storage_bytes_limit']), ('Free', free.storage_gb * GB))
        self.assertEqual(lifecycle.describe(self.sub())['state'], 'expired')
        # the real gate, over HTTP
        client = APIClient()
        client.force_authenticate(user=self.owner)
        patch = {'design_settings': {'downloads': {'high_res': {'enabled': True, 'mode': 'original'}}}}
        gate = client.patch(f'/api/v1/galleries/{gallery.slug}/', patch, format='json')
        self.assertEqual((gate.status_code, gate.data['code']), (403, 'original_download_requires_upgrade'))
        self.assertFalse(has_feature(self.owner, WATERMARK))
        # still nothing written by anyone: only the sweep / the job write, and neither ran
        self.assertEqual(self.sub().status, 'active')

    def test_a_beat_that_is_down_cannot_extend_a_plan_the_period_end_is_the_only_clock(self):
        give_period(self.owner, timezone.now() + timedelta(seconds=2))
        self.assertTrue(get_feature_entitlements(self.owner)['original_download'])
        UserSubscription.objects.filter(user=self.owner).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(get_feature_entitlements(self.owner)['original_download'])


# ─── the clock: calendar days in Kathmandu ───────────────────────────────────

class BoundaryTests(LifecycleBase):
    def setUp(self):
        super().setUp()
        give_period(self.owner, END)

    def test_the_billing_zone_is_kathmandu_not_the_project_zone(self):
        self.assertEqual(settings.BILLING_TIME_ZONE, 'Asia/Kathmandu')
        self.assertEqual(settings.TIME_ZONE, 'UTC')                          # unchanged: every other schedule keeps it
        self.assertEqual(lifecycle.billing_tz().utcoffset(END), timedelta(hours=5, minutes=45))

    def test_the_reminder_is_due_from_midnight_kathmandu_three_days_before_the_end_date(self):
        # end date = Oct 10; 3 days before = Oct 7 00:00 Kathmandu
        before = self.run_job(npt(10, 6, 23, 59, 59))
        self.assertEqual(before['reminders'], [])
        self.assertEqual(bells(self.owner, 'plan_expiring'), 0)
        after = self.run_job(npt(10, 7, 0, 0, 0))
        self.assertEqual(len(after['reminders']), 1)
        self.assertEqual(bells(self.owner, 'plan_expiring'), 1)

    def test_the_boundary_is_the_kathmandu_midnight_in_utc_terms(self):
        # Oct 6 18:14:59 UTC is Oct 6 23:59:59 in Kathmandu; one second later it is Oct 7.
        utc = ZoneInfo('UTC')
        self.assertEqual(self.run_job(datetime(YEAR, 10, 6, 18, 14, 59, tzinfo=utc))['reminders'], [])
        self.assertEqual(len(self.run_job(datetime(YEAR, 10, 6, 18, 15, 0, tzinfo=utc))['reminders']), 1)

    def test_the_downgrade_is_due_from_midnight_after_the_last_grace_day(self):
        # end date Oct 10, 3 grace days = Oct 11, 12, 13; downgrade from Oct 14 00:00 Kathmandu
        early = self.run_job(npt(10, 13, 23, 59, 59))
        self.assertEqual(early['downgrades'], [])
        self.assertEqual(downgrade_rows().count(), 0)
        late = self.run_job(npt(10, 14, 0, 0, 0))
        self.assertEqual(len(late['downgrades']), 1)
        self.assertEqual(downgrade_rows(self.owner).count(), 1)

    def test_a_period_ending_at_23_59_still_counts_as_that_days_date(self):
        give_period(self.owner, npt(10, 10, 23, 59, 59))
        self.assertEqual(self.run_job(npt(10, 13, 23, 59, 59))['downgrades'], [])
        self.assertEqual(len(self.run_job(npt(10, 14, 0, 0, 1))['downgrades']), 1)

    def test_days_left_are_calendar_days_in_the_billing_zone(self):
        self.assertEqual(lifecycle.days_until(END, npt(10, 10, 0, 0, 1)), 0)
        self.assertEqual(lifecycle.days_until(END, npt(10, 9, 23, 59, 59)), 1)
        self.assertEqual(lifecycle.days_until(END, npt(10, 7, 12)), 3)
        self.assertEqual(lifecycle.days_until(END, npt(10, 12, 9)), -2)


# ─── idempotent: twice = once ────────────────────────────────────────────────

class OnceTests(LifecycleBase):
    def setUp(self):
        super().setUp()
        give_period(self.owner, END)

    def test_the_job_twice_sends_one_reminder_bell_and_email(self):
        now = npt(10, 8, 9)
        first = self.run_job(now)
        second = self.run_job(now + timedelta(hours=1))
        self.assertEqual((len(first['reminders']), len(second['reminders'])), (1, 0))
        self.assertEqual(bells(self.owner, 'plan_expiring'), 1)
        self.assertEqual(len(mails_to(self.owner)), 1)
        text = mails_to(self.owner)[0]
        self.assertEqual(text.subject, 'Your Kyapture plan is ending soon')       # 7.5-D: fixed subject
        self.assertIn('Your Pro plan ends on', text.body)
        self.assertIn('/dashboard/billing', text.body)
        self.assertEqual(self.sub().reminder_notified_for, END)
        self.assertEqual(self.sub().reminder_emailed_for, END)
        # and not again the next day, nor on the last day
        self.run_job(npt(10, 9, 9))
        self.run_job(npt(10, 10, 9))
        self.assertEqual((bells(self.owner, 'plan_expiring'), len(mails_to(self.owner))), (1, 1))

    def test_the_job_twice_makes_one_downgrade_one_audit_row_one_bell_one_email(self):
        now = npt(10, 15, 9)
        first = self.run_job(now)
        second = self.run_job(now + timedelta(hours=1))
        self.assertEqual((len(first['downgrades']), len(second['downgrades'])), (1, 0))
        sub = self.sub()
        self.assertEqual((sub.status, sub.downgraded_for, sub.downgrade_emailed_for), ('expired', END, END))
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active_plan)
        self.assertEqual(downgrade_rows(self.owner).count(), 1)
        self.assertEqual(bells(self.owner, 'plan_expired'), 1)
        self.assertEqual(len(mails_to(self.owner)), 1)
        self.assertEqual(mails_to(self.owner)[0].subject, 'Your Kyapture plan has ended')

    def test_the_audit_row_has_no_actor_names_the_account_and_holds_no_secret(self):
        self.run_job(npt(10, 15, 9))
        row = downgrade_rows(self.owner).get()
        self.assertEqual((row.actor_id, row.actor_email, row.ip), (None, '', None))
        self.assertEqual((row.target_id, row.target_email), (self.owner.pk, self.owner.email))
        self.assertEqual(row.reason, f'plan=pro period_end={YEAR}-10-10 grace_days=3')
        staff = make_user('lifestaff', is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff)
        listed = client.get('/api/v1/staff/audit/', {'action': Action.SUBSCRIPTION_DOWNGRADE})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data['results']), 1)
        self.assertEqual(listed.data['results'][0]['action_label'], 'Moved to Free after the plan ended')

    def test_a_reminder_then_the_downgrade_are_two_separate_steps_of_one_period(self):
        self.run_job(npt(10, 8, 9))
        self.run_job(npt(10, 15, 9))
        self.assertEqual((bells(self.owner, 'plan_expiring'), bells(self.owner, 'plan_expired')), (1, 1))
        self.assertEqual(len(mails_to(self.owner)), 2)

    def test_nothing_is_deleted_by_the_downgrade(self):
        gallery = Gallery.objects.create(photographer=self.owner, title='Keep me', slug='keep-75c',
                                         design_settings={'watermark': {'type': 'text', 'text': 'Studio'}})
        asset = MediaAsset.objects.create(
            gallery=gallery, original_file=SimpleUploadedFile('keep.jpg', b'x'), original_name='keep.jpg',
            file_size=10, order=1, processing_status=MediaAsset.ProcessingStatus.READY)
        before = (Gallery.objects.count(), MediaAsset.objects.count(), UserSubscription.objects.count())
        self.run_job(npt(10, 15, 9))
        self.assertEqual((Gallery.objects.count(), MediaAsset.objects.count(), UserSubscription.objects.count()), before)
        gallery.refresh_from_db()
        self.assertEqual(gallery.design_settings, {'watermark': {'type': 'text', 'text': 'Studio'}})
        self.assertTrue(MediaAsset.objects.get(pk=asset.pk).original_file.storage.exists(asset.original_file.name))


class PaidUserUntouchedTests(LifecycleBase):
    def test_a_paid_user_far_from_the_end_gets_nothing(self):
        give_period(self.owner, END)
        report = self.run_job(npt(10, 1, 9))            # 9 days before the end
        self.assertEqual((report['reminders'], report['downgrades']), ([], []))
        sub = self.sub()
        self.assertEqual((sub.status, sub.expires_at), ('active', END))
        self.assertEqual((Notification.objects.count(), StaffAuditLog.objects.count(), len(mail.outbox)), (0, 0, 0))
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active_plan)

    def test_a_live_user_inside_the_grace_window_of_nothing_is_not_downgraded(self):
        give_period(self.owner, END)
        self.run_job(npt(10, 9, 9))                     # reminder only
        self.assertEqual(downgrade_rows().count(), 0)
        self.assertEqual(self.sub().status, 'active')

    def test_a_user_with_no_subscription_or_a_cancelled_one_is_ignored(self):
        other = make_user('lifenone')
        cancelled = make_user('lifecancel')
        give_period(cancelled, npt(9, 1), status=Status.CANCELLED)
        report = self.run_job(npt(10, 20, 9))
        self.assertEqual((report['reminders'], report['downgrades']), ([], []))
        self.assertEqual(downgrade_rows().count(), 0)
        self.assertFalse(UserSubscription.objects.filter(user=other).exists())

    def test_a_staff_account_is_processed_like_any_other_the_paperwork_only(self):
        staff = make_user('lifestaff2', is_staff=True)
        give_period(staff, END)
        report = self.run_job(npt(10, 15, 9))
        self.assertEqual(len(report['downgrades']), 1)       # paperwork only; staff entitlements are separate


# ─── renewal ─────────────────────────────────────────────────────────────────

class RenewalTests(LifecycleBase):
    @classmethod
    def setUpClass(cls):
        MediaSandbox.enter.__func__(cls)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        MediaSandbox.leave.__func__(cls)

    def setUp(self):
        super().setUp()
        self.staff = make_user('renewstaff', is_staff=True)
        give_period(self.owner, END)
        patcher = mock.patch('apps.users.tasks.send_notification_email.delay',
                             side_effect=lambda *args: deliver_notification(*args))
        patcher.start()
        self.addCleanup(patcher.stop)

    def pay(self, plan=None):
        from django.core.files.base import ContentFile
        plan = plan or self.pro
        payment = ManualPayment(
            user=self.owner, plan=plan, amount=plan.price, plan_price=plan.price,
            reference=f'REN-{ManualPayment.objects.count() + 1:04d}', proof_type='image/png', proof_size=1)
        payment.payment_proof.save('proof.png', ContentFile(image_bytes()), save=False)
        payment.save()
        with self.captureOnCommitCallbacks(execute=True):
            payments.approve_payment(payment.pk, self.staff)
        return payment

    def test_a_renewal_before_the_end_extends_the_period_and_clears_the_markers(self):
        self.run_job(npt(10, 8, 9))                                           # the reminder is sent
        sub = self.sub()
        self.assertEqual((sub.reminder_notified_for, sub.reminder_emailed_for), (END, END))

        before = timezone.now()
        self.pay()
        sub = self.sub()
        self.assertEqual(sub.expires_at, END + timedelta(days=settings.MANUAL_PAYMENT_PERIOD_DAYS))   # same plan: added to the end
        self.assertEqual([getattr(sub, name) for name in UserSubscription.LIFECYCLE_MARKERS], [None] * 4)
        self.assertGreater(sub.updated_at, before)

        # the old window's runs do nothing now ...
        outbox = len(mails_to(self.owner))
        self.assertEqual(self.run_job(npt(10, 9, 9))['reminders'], [])
        self.assertEqual(self.run_job(npt(10, 15, 9))['downgrades'], [])
        self.assertEqual(len(mails_to(self.owner)), outbox)
        self.assertEqual(downgrade_rows().count(), 0)
        # ... and the NEW period gets its own single reminder
        new_end = sub.expires_at
        window = new_end.astimezone(NPT).replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=2)
        self.assertEqual(len(self.run_job(window)['reminders']), 1)
        self.assertEqual(self.run_job(window + timedelta(hours=2))['reminders'], [])
        self.assertEqual(bells(self.owner, 'plan_expiring'), 2)

    def test_a_marker_belongs_to_one_period_even_if_nothing_cleared_it(self):
        self.run_job(npt(10, 8, 9))
        UserSubscription.objects.filter(user=self.owner).update(expires_at=END + timedelta(days=30))   # e.g. an admin edit
        self.assertEqual(self.run_job(npt(10, 9, 9))['reminders'], [])        # not in the new window yet
        self.assertEqual(len(self.run_job(npt(11, 7, 9))['reminders']), 1)    # new end date Nov 9: reminder on Nov 6/7

    def test_a_renewal_after_the_downgrade_makes_a_fresh_period_and_the_user_is_paid_again(self):
        self.run_job(npt(10, 15, 9))
        self.assertEqual(self.sub().status, 'expired')
        self.assertFalse(get_feature_entitlements(self.owner)['original_download'])
        self.pay()
        sub = self.sub()
        self.assertEqual(sub.status, 'active')
        self.assertGreater(sub.expires_at, timezone.now())
        self.assertEqual([getattr(sub, name) for name in UserSubscription.LIFECYCLE_MARKERS], [None] * 4)
        self.assertTrue(get_feature_entitlements(self.owner)['original_download'])
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active_plan)

    def test_paying_for_a_different_plan_during_an_active_period_starts_it_now_for_a_full_period(self):
        """The 7.5-B behaviour that docs/KYAPTURE_PAYMENTS.md section 11 documents (no proration)."""
        give_period(self.owner, timezone.now() + timedelta(days=10), plan_key='basic')
        studio = SubscriptionPlan.objects.get(key='studio')
        self.pay(studio)
        sub = self.sub()
        self.assertEqual(sub.plan_id, studio.pk)
        self.assertAlmostEqual((sub.expires_at - timezone.now()).total_seconds(),
                               settings.MANUAL_PAYMENT_PERIOD_DAYS * 86400, delta=120)      # not 10 + 30 days


# ─── the sweep no longer overwrites a renewal ────────────────────────────────

class SweepLockTests(LifecycleBase):
    def test_expire_lapsed_re_reads_the_status_under_the_lock_and_skips_a_renewed_row(self):
        sub = give_period(self.owner, timezone.now() - timedelta(minutes=1))
        UserSubscription.objects.filter(pk=sub.pk).update(expires_at=timezone.now() + timedelta(days=5))   # renewed meanwhile
        self.assertFalse(lifecycle.expire_lapsed(sub.pk))
        self.assertEqual(self.sub().status, 'active')

    def test_the_sweep_still_expires_a_lapsed_row_and_clears_the_legacy_flag(self):
        give_period(self.owner, timezone.now() - timedelta(minutes=1))
        self.assertEqual(sweep_expired_subscriptions(), 1)
        self.assertEqual(self.sub().status, 'expired')
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active_plan)
        self.assertEqual(sweep_expired_subscriptions(), 0)

    def test_the_sweep_then_the_job_still_downgrades_once(self):
        end = timezone.now() - timedelta(days=5)
        give_period(self.owner, end)
        sweep_expired_subscriptions()                          # flips to expired at the end (before any grace)
        self.assertEqual(self.sub().status, 'expired')
        self.assertEqual(downgrade_rows(self.owner).count(), 0)
        self.run_job(timezone.now())
        self.run_job(timezone.now() + timedelta(hours=1))
        self.assertEqual((downgrade_rows(self.owner).count(), len(mails_to(self.owner))), (1, 1))

    def test_my_subscription_get_flips_a_lapsed_row_under_the_same_helper(self):
        give_period(self.owner, timezone.now() - timedelta(minutes=1))
        client = APIClient()
        client.force_authenticate(user=self.owner)
        data = client.get('/api/v1/subscriptions/my-subscription/').data
        self.assertEqual(data['status'], 'expired')
        self.assertEqual(data['lifecycle']['state'], 'expired')
        self.assertFalse(data['entitlements']['original_download'])


# ─── mail failures, suspended accounts, preferences ──────────────────────────

class MailTests(LifecycleBase):
    def setUp(self):
        super().setUp()
        give_period(self.owner, END)

    def test_a_failed_downgrade_email_does_not_block_the_downgrade_and_is_retried(self):
        with mock.patch('apps.subscriptions.lifecycle.send_email', side_effect=SMTPException('down')):
            report = self.run_job(npt(10, 15, 9))
        self.assertTrue(report['downgrades'][0]['downgraded'])
        self.assertTrue(report['downgrades'][0]['email_failed'])
        sub = self.sub()
        self.assertEqual((sub.status, sub.downgraded_for, sub.downgrade_emailed_for), ('expired', END, None))
        self.assertEqual((downgrade_rows(self.owner).count(), bells(self.owner, 'plan_expired')), (1, 1))
        self.assertEqual(len(mails_to(self.owner)), 0)

        retry = self.run_job(npt(10, 16, 9))                     # next day, mail works again
        self.assertEqual(len(mails_to(self.owner)), 1)
        self.assertFalse(retry['downgrades'][0]['downgraded'])   # the downgrade itself is not done twice
        self.assertEqual(self.sub().downgrade_emailed_for, END)
        self.run_job(npt(10, 17, 9))
        self.assertEqual((len(mails_to(self.owner)), downgrade_rows(self.owner).count(), bells(self.owner, 'plan_expired')),
                         (1, 1, 1))

    def test_a_failed_reminder_email_is_retried_while_the_period_is_still_running(self):
        with mock.patch('apps.subscriptions.lifecycle.send_email', side_effect=SMTPException('down')):
            self.run_job(npt(10, 8, 9))
        self.assertEqual((bells(self.owner, 'plan_expiring'), len(mails_to(self.owner))), (1, 0))
        self.assertIsNone(self.sub().reminder_emailed_for)
        self.run_job(npt(10, 9, 9))
        self.assertEqual((bells(self.owner, 'plan_expiring'), len(mails_to(self.owner))), (1, 1))

    def test_a_mail_that_keeps_failing_is_dropped_after_the_retry_window(self):
        with mock.patch('apps.subscriptions.lifecycle.send_email', side_effect=SMTPException('down')):
            self.run_job(npt(10, 15, 9))
            late = self.run_job(npt(10, 14) + timedelta(days=3 + settings.SUBSCRIPTION_EMAIL_RETRY_DAYS + 1))
        self.assertEqual(late['downgrades'], [])
        self.assertEqual(downgrade_rows(self.owner).count(), 1)

    def test_a_period_that_ended_long_ago_is_downgraded_silently(self):
        give_period(self.owner, npt(7, 1))
        report = self.run_job(npt(10, 15, 9))
        self.assertEqual(len(report['downgrades']), 1)
        self.assertEqual(self.sub().status, 'expired')
        self.assertEqual((bells(self.owner, 'plan_expired'), len(mails_to(self.owner))), (0, 0))
        self.assertIn('silent=old', downgrade_rows(self.owner).get().reason)
        self.run_job(npt(10, 16, 9))
        self.assertEqual((len(mails_to(self.owner)), downgrade_rows(self.owner).count()), (0, 1))

    def test_a_suspended_account_is_downgraded_but_never_mailed_or_notified(self):
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        reminder = self.run_job(npt(10, 8, 9))
        self.assertEqual(reminder['reminders'], [])
        self.assertEqual((Notification.objects.count(), len(mail.outbox)), (0, 0))
        self.assertIsNone(self.sub().reminder_notified_for)
        report = self.run_job(npt(10, 15, 9))
        self.assertEqual(len(report['downgrades']), 1)
        sub = self.sub()
        self.assertEqual((sub.status, sub.downgraded_for), ('expired', END))
        self.assertEqual(downgrade_rows(self.owner).count(), 1)
        self.assertEqual((Notification.objects.filter(user=self.owner).count(), len(mails_to(self.owner))), (0, 0))
        self.run_job(npt(10, 16, 9))
        self.assertEqual((len(mails_to(self.owner)), downgrade_rows(self.owner).count()), (0, 1))

    def test_an_account_suspended_after_the_reminder_window_opened_is_skipped_inside_the_lock(self):
        # the candidate list was read while the account was active; the row is re-read under the lock
        candidates = lifecycle.reminder_candidates(npt(10, 8, 9), LifecycleSettings.load(), NPT)
        self.assertEqual(len(candidates), 1)
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        sub_id, user_id = candidates[0][0], candidates[0][1]
        self.assertIsNone(lifecycle.process_reminder(sub_id, user_id, npt(10, 8, 9), LifecycleSettings.load(), NPT))
        self.assertEqual((Notification.objects.count(), len(mail.outbox)), (0, 0))

    def test_the_payments_email_preference_off_keeps_the_bell_and_skips_the_mail(self):
        User.objects.filter(pk=self.owner.pk).update(notify_payments=False)
        self.run_job(npt(10, 8, 9))
        self.run_job(npt(10, 15, 9))
        self.assertEqual((bells(self.owner, 'plan_expiring'), bells(self.owner, 'plan_expired')), (1, 1))
        self.assertEqual(len(mails_to(self.owner)), 0)
        self.run_job(npt(10, 16, 9))
        self.assertEqual((len(mails_to(self.owner)), downgrade_rows(self.owner).count()), (0, 1))

    def test_the_mail_and_the_bell_never_carry_a_secret_or_a_storage_path(self):
        self.run_job(npt(10, 8, 9))
        self.run_job(npt(10, 15, 9))
        everything = ' '.join(f'{m.subject} {m.body}' for m in mail.outbox)
        everything += ' '.join(Notification.objects.values_list('message', flat=True))
        for needle in ('password', 'token', 'private', 'media/', 'photographers/'):
            self.assertNotIn(needle, everything.lower())


# ─── what the owner sees ─────────────────────────────────────────────────────

class OwnerViewTests(LifecycleBase):
    def lifecycle_of(self, end, **kwargs):
        give_period(self.owner, end, **kwargs)
        client = APIClient()
        client.force_authenticate(user=self.owner)
        return client.get('/api/v1/subscriptions/my-subscription/').data['lifecycle']

    def test_active_expiring_and_expired_states(self):
        far = self.lifecycle_of(timezone.now() + timedelta(days=20))
        self.assertEqual((far['state'], far['reminder_days'], far['grace_days']), ('active', 3, 3))
        soon = self.lifecycle_of(timezone.now() + timedelta(days=2, hours=1))
        self.assertEqual(soon['state'], 'expiring')
        self.assertIn(soon['days_left'], (2, 3))
        gone = self.lifecycle_of(timezone.now() - timedelta(days=1), status=Status.EXPIRED)
        self.assertEqual(gone['state'], 'expired')
        self.assertLess(gone['days_left'], 1)

    def test_no_subscription_reads_as_none(self):
        client = APIClient()
        client.force_authenticate(user=make_user('lifenobody'))
        data = client.get('/api/v1/subscriptions/my-subscription/').data
        self.assertEqual(data['lifecycle']['state'], 'none')

    def test_the_reminder_window_follows_the_admin_row(self):
        end = timezone.now() + timedelta(days=5, hours=1)
        self.assertEqual(self.lifecycle_of(end)['state'], 'active')
        row = LifecycleSettings.load()
        row.reminder_days = 7
        row.save()
        self.assertEqual(self.lifecycle_of(end)['state'], 'expiring')

    def test_the_bell_link_for_the_new_kinds_is_billing(self):
        give_period(self.owner, END)
        self.run_job(npt(10, 8, 9))
        client = APIClient()
        client.force_authenticate(user=self.owner)
        listed = client.get('/api/v1/notifications/')
        self.assertEqual(listed.status_code, 200)
        rows = [row for row in listed.data['results'] if row['kind'] == 'plan_expiring']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['link'], '/dashboard/billing')


# ─── the admin-edited row ────────────────────────────────────────────────────

class SettingsRowTests(LifecycleBase):
    def test_the_defaults_are_three_and_three_and_the_row_is_one(self):
        row = LifecycleSettings.load()
        self.assertEqual((row.pk, row.reminder_days, row.grace_days), (1, 3, 3))
        other = LifecycleSettings(reminder_days=5, grace_days=1)
        other.save()
        self.assertEqual(LifecycleSettings.objects.count(), 1)          # a singleton: saving again edits row 1
        self.assertEqual(LifecycleSettings.load().reminder_days, 5)

    def test_it_is_registered_in_the_admin_with_no_add_when_it_exists_and_no_delete(self):
        self.assertIn(LifecycleSettings, django_admin.site._registry)
        model_admin = LifecycleSettingsAdmin(LifecycleSettings, django_admin.site)
        LifecycleSettings.load()
        request = mock.Mock()
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertEqual(model_admin.fields, ['reminder_days', 'grace_days'])

    def test_out_of_range_values_are_refused_by_validation(self):
        for values in ({'reminder_days': 0, 'grace_days': 3}, {'reminder_days': 31, 'grace_days': 3},
                       {'reminder_days': 3, 'grace_days': 31}):
            with self.assertRaises(ValidationError):
                LifecycleSettings(**values).full_clean()
        LifecycleSettings(reminder_days=1, grace_days=0).full_clean()       # zero grace is allowed

    def test_a_changed_reminder_day_count_moves_the_reminder(self):
        give_period(self.owner, END)
        row = LifecycleSettings.load()
        row.reminder_days = 5
        row.save()
        self.assertEqual(self.run_job(npt(10, 4, 23, 59, 59))['reminders'], [])
        self.assertEqual(len(self.run_job(npt(10, 5, 0, 0, 0))['reminders']), 1)      # Oct 10 - 5 days

    def test_a_changed_grace_moves_the_downgrade_and_zero_grace_means_the_day_after(self):
        give_period(self.owner, END)
        row = LifecycleSettings.load()
        row.grace_days = 0
        row.save()
        self.assertEqual(self.run_job(npt(10, 10, 23, 59, 59))['downgrades'], [])
        self.assertEqual(len(self.run_job(npt(10, 11, 0, 0, 0))['downgrades']), 1)

    def test_no_number_is_hard_coded_the_row_is_read_at_each_run(self):
        give_period(self.owner, END)
        self.run_job(npt(10, 13, 23, 59, 59))
        self.assertEqual(downgrade_rows().count(), 0)
        row = LifecycleSettings.load()
        row.grace_days = 1
        row.save()
        self.run_job(npt(10, 13, 23, 59, 59))                                   # same instant, shorter grace
        self.assertEqual(downgrade_rows().count(), 1)


# ─── the lock ────────────────────────────────────────────────────────────────

class LockTests(LifecycleBase):
    def setUp(self):
        super().setUp()
        give_period(self.owner, END)

    def test_a_run_that_finds_the_lock_taken_does_nothing_and_leaves_it_alone(self):
        cache.add(lifecycle.LOCK_KEY, 'someone-else', timeout=60)
        report = self.run_job(npt(10, 15, 9))
        self.assertEqual(report['skipped'], 'locked')
        self.assertEqual((downgrade_rows().count(), len(mail.outbox)), (0, 0))
        self.assertEqual(cache.get(lifecycle.LOCK_KEY), 'someone-else')        # it did not steal or free it
        cache.delete(lifecycle.LOCK_KEY)
        self.assertEqual(len(self.run_job(npt(10, 15, 9))['downgrades']), 1)

    def test_the_lock_is_released_after_a_run_even_if_the_run_fails(self):
        self.run_job(npt(10, 8, 9))
        self.assertIsNone(cache.get(lifecycle.LOCK_KEY))
        with mock.patch('apps.subscriptions.lifecycle.process_downgrade', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.run_job(npt(10, 15, 9))
        self.assertIsNone(cache.get(lifecycle.LOCK_KEY))

    def test_the_celery_task_runs_the_same_code(self):
        with mock.patch('apps.subscriptions.lifecycle.timezone') as fake:
            fake.now.return_value = npt(10, 15, 9)
            result = run_subscription_lifecycle()
        self.assertEqual(result, {'skipped': None, 'reminders': 0, 'downgrades': 1})
        self.assertEqual(downgrade_rows(self.owner).count(), 1)


class TwoRunnersAtOnceTests(TransactionTestCase):
    """Real threads on real commits. Plan rows are re-created in setUp (no serialized_rollback)."""

    def setUp(self):
        cache.clear()
        mail.outbox = []
        ensure_seed_plans()
        self.owners = [make_user(f'twin{i}') for i in range(3)]
        for owner in self.owners:
            give_period(owner, END)

    def go(self, jobs):
        barrier = threading.Barrier(len(jobs))
        results = [None] * len(jobs)

        def worker(index, job):
            try:
                barrier.wait(timeout=10)
                results[index] = job()
            except Exception as error:               # surfaced by the assertions below
                results[index] = error
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(i, job)) for i, job in enumerate(jobs)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        return results

    def assert_once(self):
        self.assertEqual(downgrade_rows().count(), 3)
        for owner in self.owners:
            self.assertEqual(downgrade_rows(owner).count(), 1, owner.email)
            self.assertEqual(bells(owner, 'plan_expired'), 1, owner.email)
            self.assertEqual(len(mails_to(owner)), 1, owner.email)

    def test_two_runners_with_the_cache_lock_defeated_still_downgrade_and_mail_once(self):
        # the cache lock is taken out of the picture: only the user + subscription row locks protect the work
        with mock.patch('apps.subscriptions.lifecycle._acquire', return_value='bypass'), \
                mock.patch('apps.subscriptions.lifecycle._release'):
            results = self.go([lambda: lifecycle.run(now=npt(10, 15, 9)) for _ in range(2)])
        for result in results:
            self.assertIsInstance(result, dict, result)
        self.assert_once()

    def test_two_runners_with_the_lock_one_works_or_both_in_turn_and_it_is_still_once(self):
        results = self.go([lambda: lifecycle.run(now=npt(10, 15, 9)) for _ in range(2)])
        for result in results:
            self.assertIsInstance(result, dict, result)
        self.assert_once()
        self.assertIsNone(cache.get(lifecycle.LOCK_KEY))

    def test_a_renewal_holding_the_locks_is_not_overwritten_by_the_sweep(self):
        sub = UserSubscription.objects.get(user=self.owners[0])
        UserSubscription.objects.filter(pk=sub.pk).update(expires_at=timezone.now() - timedelta(minutes=1))   # lapsed
        holding = threading.Event()

        def renew():                      # what approve_payment does: user row, then subscription row, then the write
            with transaction.atomic():
                _user, locked = lifecycle._lock_rows(sub.pk, sub.user_id)
                holding.set()
                time.sleep(0.8)
                locked.expires_at = timezone.now() + timedelta(days=30)
                locked.save(update_fields=['expires_at'])
            return 'renewed'

        def sweep():                      # the old code read the lapsed row now and wrote 'expired' over the renewal
            holding.wait(10)
            return lifecycle.expire_lapsed(sub.pk)

        results = self.go([renew, sweep])
        self.assertEqual(results, ['renewed', False])
        final = UserSubscription.objects.get(pk=sub.pk)
        self.assertEqual(final.status, 'active')
        self.assertGreater(final.expires_at, timezone.now())


# ─── the command ─────────────────────────────────────────────────────────────

class CommandTests(LifecycleBase):
    def setUp(self):
        super().setUp()
        self.reminded = make_user('cmdremind')
        self.lapsed = make_user('cmdlapsed')
        self.suspended = make_user('cmdsuspended')
        give_period(self.reminded, timezone.now() + timedelta(days=2))
        give_period(self.lapsed, timezone.now() - timedelta(days=5))
        give_period(self.suspended, timezone.now() - timedelta(days=5))
        User.objects.filter(pk=self.suspended.pk).update(is_active=False)

    def snapshot(self):
        return (
            list(UserSubscription.objects.order_by('user_id').values()),
            Notification.objects.count(), StaffAuditLog.objects.count(), len(mail.outbox),
            list(User.objects.order_by('pk').values_list('is_active_plan', flat=True)),
        )

    def test_dry_run_prints_who_and_writes_nothing(self):
        before = self.snapshot()
        out = io.StringIO()
        call_command('run_subscription_lifecycle', '--dry-run', stdout=out)
        text = out.getvalue()
        self.assertEqual(self.snapshot(), before)                               # no row, no mail, no bell, no audit
        self.assertIsNone(cache.get(lifecycle.LOCK_KEY))
        self.assertIn('DRY RUN', text)
        self.assertIn(self.reminded.email, text)
        self.assertIn(self.lapsed.email, text)
        self.assertIn(self.suspended.email, text)
        self.assertIn('suspended', text)
        self.assertIn('would', text)

    def test_the_normal_run_does_the_work_and_a_second_run_does_nothing(self):
        out = io.StringIO()
        call_command('run_subscription_lifecycle', stdout=out)
        self.assertEqual(bells(self.reminded, 'plan_expiring'), 1)
        self.assertEqual(downgrade_rows().count(), 2)                           # the lapsed one and the suspended one
        self.assertEqual(len(mails_to(self.reminded)) + len(mails_to(self.lapsed)), 2)
        self.assertEqual(len(mails_to(self.suspended)), 0)
        first = self.snapshot()
        call_command('run_subscription_lifecycle', stdout=io.StringIO())
        self.assertEqual(self.snapshot(), first)

    def test_there_is_no_http_route_for_the_job(self):
        for path in ('/api/v1/subscriptions/lifecycle/', '/api/v1/subscriptions/run-lifecycle/',
                     '/api/v1/staff/lifecycle/', '/api/v1/subscriptions/run_subscription_lifecycle/'):
            with self.assertRaises(Resolver404):
                resolve(path)


# ─── the beat ────────────────────────────────────────────────────────────────

class BeatScheduleTests(APITestCase):
    def test_the_daily_job_is_a_named_entry_in_the_one_schedule_with_the_older_jobs_intact(self):
        from config.celery import app
        schedule = app.conf.beat_schedule
        self.assertIn('subscription-lifecycle-daily', schedule)
        self.assertEqual(schedule['subscription-lifecycle-daily']['task'],
                         'apps.subscriptions.tasks.run_subscription_lifecycle')
        for name in ('sweep-expired-subscriptions', 'purge-trashed-galleries', 'purge-expired-client-sessions',
                     'purge-old-download-logs', 'purge-expired-download-jobs', 'purge-old-notifications',
                     'flush-expired-jwt-tokens'):
            self.assertIn(name, schedule)
        self.assertIn('account-deletion-sweep', schedule)        # 7.5-E added its own named entry
        self.assertEqual(len(schedule), 9)
        self.assertEqual(settings.CELERY_BEAT_SCHEDULE.keys(), schedule.keys())

    def test_it_runs_just_after_midnight_in_kathmandu(self):
        from config.celery import app
        entry = app.conf.beat_schedule['subscription-lifecycle-daily']['schedule']
        self.assertEqual((list(entry.hour), list(entry.minute)), ([18], [25]))
        utc = datetime(2026, 10, 9, 18, 25, tzinfo=ZoneInfo('UTC'))
        self.assertEqual((utc.astimezone(NPT).hour, utc.astimezone(NPT).minute, utc.astimezone(NPT).day), (0, 10, 10))

    def test_the_task_is_registered(self):
        from config.celery import app
        self.assertIn('apps.subscriptions.tasks.run_subscription_lifecycle', app.tasks)


# ─── a downgraded owner: Free behaviour, stored Pro values kept, upgrade restores ───

class AfterDowngradeTests(DownloadFlowBase):
    """Uses the public-gallery fixture of the download tests: a real gallery, photos and files."""
    with_pin = False

    def setUp(self):
        super().setUp()
        mail.outbox = []
        grant_plan(self.photographer)                       # Pro, all three paid flags on
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(user=self.photographer)

    def downgrade(self):
        UserSubscription.objects.filter(user=self.photographer).update(expires_at=END)
        report = lifecycle.run(now=npt(10, 15, 9))
        self.assertEqual(len(report['downgrades']), 1, report)

    def renew(self):
        UserSubscription.objects.filter(user=self.photographer).update(
            status='active', expires_at=timezone.now() + timedelta(days=30),
            **{marker: None for marker in UserSubscription.LIFECYCLE_MARKERS})

    def photo(self, resolution='download'):
        cache.clear()
        token = self.token(email='visitor@example.com')
        response = self.client.get(self.photo_url(self.a1), {'download_token': token, 'resolution': resolution})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return b''.join(response.streaming_content)

    def fill_beyond_free(self):
        # the filler sits in a private second collection, so the public one still holds only its three real photos
        free = SubscriptionPlan.get_free()
        private = Gallery.objects.create(photographer=self.photographer, title='Filler', slug='filler-75c')
        MediaAsset.objects.create(
            gallery=private, original_file=SimpleUploadedFile('fill.jpg', b'x'), original_name='fill.jpg',
            file_size=free.storage_gb * GB + 5, order=99, processing_status=MediaAsset.ProcessingStatus.READY)

    def test_an_over_limit_user_cannot_upload_but_clients_still_view_and_download(self):
        self.fill_beyond_free()
        self.downgrade()
        figures = storage_figures(get_user_subscription_metrics(self.photographer))
        self.assertEqual(figures['storage_state'], 'over')

        buf = io.BytesIO()
        Image.new('RGB', (30, 30), 'white').save(buf, 'JPEG')
        refused = self.owner_client.post(
            f'/api/v1/photos/{self.gallery.slug}/upload/',
            {'image': [SimpleUploadedFile('more.jpg', buf.getvalue(), content_type='image/jpeg')]}, format='multipart')
        self.assertEqual((refused.status_code, refused.data['code']), (403, 'storage_limit_reached'))

        # the gallery stays public and viewable
        cache.clear()
        page = self.client.get(self.base)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(page.data['photos']), 3)                            # nothing hidden or deleted
        # clients download at the Free level: the 3600 px master, never the original
        self.assertEqual(self.photo('download'), b'MASTER:a1.jpg')
        cache.clear()
        token = self.token(email='visitor2@example.com')
        zipped = self.zip(token=token)
        self.assertEqual(zipped.status_code, 200)
        self.assertEqual(_zip_entries(zipped), {
            'a1.jpg': b'MASTER:a1.jpg', 'a2.jpg': b'MASTER:a2.jpg', 'b1.jpg': b'MASTER:b1.jpg'})
        self.assertEqual(MediaAsset.objects.filter(gallery=self.gallery).count(), 3)

    def test_pro_only_features_lock_and_every_stored_value_survives_then_an_upgrade_restores_them(self):
        # a Pro owner's saved settings: original downloads, a watermark, a logo and a brand colour
        patch = {'watermark_enabled': True, 'branding_color': '#112233', 'design_settings': {
            'downloads': {'high_res': {'enabled': True, 'mode': 'original'}},
            'watermark': {'type': 'text', 'text': 'Studio Mark', 'position': 'bottom-right'},
        }}
        saved = self.owner_client.patch(f'/api/v1/galleries/{self.gallery.slug}/', patch, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        logo = io.BytesIO()
        Image.new('RGBA', (200, 100), (200, 30, 30, 255)).save(logo, 'PNG')
        put = self.owner_client.put(
            '/api/v1/auth/me/', {'logo': SimpleUploadedFile('logo.png', logo.getvalue(), content_type='image/png')},
            format='multipart')
        self.assertEqual(put.status_code, 200, put.data)
        self.photographer.refresh_from_db()
        logo_name = self.photographer.logo.name
        self.gallery.refresh_from_db()
        stored = (self.gallery.design_settings, self.gallery.watermark_enabled, self.gallery.branding_color)
        self.assertEqual(self.photo('download'), b'ORIGINAL:a1.jpg')
        self.assertIsNotNone(build_watermark_spec(self.gallery))
        self.assertTrue(self.client.get(self.base).data['photographer_logo'])

        self.downgrade()

        # locked: the effect stops
        self.gallery.refresh_from_db()
        self.photographer.refresh_from_db()
        self.assertEqual(effective_high_res_mode(self.gallery), '3600')
        self.assertEqual(self.photo('download'), b'MASTER:a1.jpg')
        self.assertIsNone(build_watermark_spec(self.gallery))
        cache.clear()
        self.assertIsNone(self.client.get(self.base).data['photographer_logo'])
        # locked: editing is refused server-side
        url = f'/api/v1/galleries/{self.gallery.slug}/'
        new_mark = {'design_settings': {'watermark': {'type': 'text', 'text': 'Different'}}}
        refused = self.owner_client.patch(url, new_mark, format='json')
        self.assertEqual((refused.status_code, refused.data['code']), (403, 'watermark_requires_upgrade'))
        second = Gallery.objects.create(photographer=self.photographer, title='Second', slug='second-75c')
        refused = self.owner_client.patch(
            f'/api/v1/galleries/{second.slug}/',
            {'design_settings': {'downloads': {'high_res': {'enabled': True, 'mode': 'original'}}}}, format='json')
        self.assertEqual((refused.status_code, refused.data['code']), (403, 'original_download_requires_upgrade'))
        other_logo = io.BytesIO()
        Image.new('RGBA', (50, 50), (1, 2, 3, 255)).save(other_logo, 'PNG')
        refused = self.owner_client.put(
            '/api/v1/auth/me/', {'logo': SimpleUploadedFile('l2.png', other_logo.getvalue(), content_type='image/png')},
            format='multipart')
        self.assertEqual((refused.status_code, refused.data['code']), (403, 'branding_requires_upgrade'))

        # kept: the stored values are exactly what they were
        self.gallery.refresh_from_db()
        self.photographer.refresh_from_db()
        self.assertEqual(self.photographer.logo.name, logo_name)
        self.assertTrue(self.photographer.logo.storage.exists(logo_name))
        self.assertEqual(self.gallery.design_settings, stored[0])
        self.assertEqual((self.gallery.watermark_enabled, self.gallery.branding_color), stored[1:])
        # saving an unrelated setting is not blocked by the stored Pro values
        ok = self.owner_client.patch(url, {'title': 'Renamed while Free'}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)

        # an upgrade restores them with NO re-entry: nothing is saved again, the stored values simply apply
        self.renew()
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.design_settings['downloads']['high_res']['mode'], 'original')
        self.assertEqual(effective_high_res_mode(self.gallery), 'original')
        self.assertEqual(self.photo('download'), b'ORIGINAL:a1.jpg')
        self.assertIsNotNone(build_watermark_spec(self.gallery))               # the watermark is back
        cache.clear()
        self.assertTrue(self.client.get(self.base).data['photographer_logo'])   # and so is the logo

    def test_a_stored_original_choice_that_was_never_changed_comes_back_by_itself_on_renewal(self):
        patch = {'design_settings': {'downloads': {'high_res': {'enabled': True, 'mode': 'original'}}}}
        self.assertEqual(self.owner_client.patch(
            f'/api/v1/galleries/{self.gallery.slug}/', patch, format='json').status_code, 200)
        self.downgrade()
        self.assertEqual(self.photo('download'), b'MASTER:a1.jpg')
        self.renew()
        self.assertEqual(self.photo('download'), b'ORIGINAL:a1.jpg')
