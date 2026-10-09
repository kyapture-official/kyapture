# backend/apps/users/tests/test_account_deletion_7_5e.py
"""
CHUNK 7.5-E - account deletion, no data export.

  REQUEST   password (or an emailed code) + the typed email; owner only; staff refused; a pending payment blocks it
  PENDING   logged out everywhere, public galleries 404 (the 19 per-path tests are in
            apps/clients/tests/test_deleting_owner_7_5e.py), API closed except the cancel page, billing stops
  CANCEL    from the signed-in page or the emailed link; restores everything; impossible once the purge started
  PURGE     files first then rows, batch-limited, idempotent, resumable, re-checks the status under the row lock
  RECORDS   approved payments anonymised, the audit trail holds no foreign key and no personal data beyond a mask
  EMAIL     "deletion requested" and "account deleted", each once; throttles on request and cancel
"""
import logging
import os
import uuid
import shutil
import tempfile
import threading
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import connection, connections
from django.db.models.signals import post_save
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from io import StringIO
from rest_framework.test import APIClient, APITestCase

from apps.clients.models import ClientSession, DownloadJob, DownloadLog, Favorite, FavoriteList
from apps.core.storage import PrivateMediaStorage, PublicMediaStorage
from apps.core.utils import get_user_subscription_metrics
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet
from apps.photos.purge import run_purge
from apps.photos.tests.test_permanent_delete import make_asset
from apps.subscriptions import lifecycle
from apps.subscriptions.models import ManualPayment, UserSubscription
from apps.subscriptions.testing import ensure_seed_plans, grant_plan
from apps.users import account_deletion as deletion
from apps.users.models import AccountSettings, Feedback, Notification, PasswordResetToken, StaffAuditLog, User

PASSWORD = 'Sturdy-Pass-8842!'
BASE = '/api/v1/auth/account/deletion/'
Status = ManualPayment.VerificationStatus
Action = StaffAuditLog.Action


def files_under(root):
    return {os.path.join(folder, name) for folder, _, names in os.walk(root) for name in names}


def set_cooling_off(days):
    AccountSettings.objects.update_or_create(pk=1, defaults={'deletion_cooling_off_days': days})


class TempMedia:
    """A throwaway MEDIA_ROOT; the 5.1-D purge task runs inline when a signal queues it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp(prefix='kyapture-acctdel-')
        cls.addClassCleanup(shutil.rmtree, cls.media_root, True)
        cls.enterClassContext(override_settings(MEDIA_ROOT=cls.media_root))
        patcher = mock.patch(
            'apps.photos.tasks.purge_storage_objects.delay',
            side_effect=lambda refs, prefixes=None: run_purge(refs, prefixes or []),
        )
        patcher.start()
        cls.addClassCleanup(patcher.stop)


_ROOT = [None]          # the running class's temporary MEDIA_ROOT (set by Base.setUpClass)


def make_account(name, *, assets=2, payments=True):
    """
    A user with everything an account owns: two collections with photos (originals, masters, derivatives, a cached
    Web Size), a ZIP, visitor data, an avatar and a logo, notifications, feedback, a subscription, and payments.
    Returns (user, the set of files that belong to it).
    """
    before = files_under(_ROOT[0])
    user = User.objects.create_user(email=f'{name}@example.test', username=name, password=PASSWORD, display_name=name.title())
    user.avatar.save('a.png', ContentFile(b'AVATAR'), save=False)
    user.logo.save('l.png', ContentFile(b'LOGO'), save=False)
    user.save()
    plan = grant_plan(user)
    for number in range(2):
        gallery = Gallery.objects.create(
            photographer=user, title=f'G{number}', slug=f'g{number}-{name}', is_published=True, allow_download=True)
        photo_set = PhotoSet.objects.create(gallery=gallery, name=f'S{number}', order=1)
        made = [make_asset(gallery, f'p{i}.jpg', order=i, photo_set=photo_set) for i in range(assets)]
        # a cached Web Size file, in the layout apps/clients/web_size.py writes
        size_key = f'photographers/{user.pk}/galleries/{gallery.pk}/web_size/{made[0].pk}/2048-0-x.jpg'
        PrivateMediaStorage().save(size_key, ContentFile(b'WEBSIZE'))
        zip_job = DownloadJob.objects.create(gallery=gallery, state='ready', email='visitor@example.test')
        zip_name = PrivateMediaStorage().save(f'download_jobs/{zip_job.pk}/z.zip', ContentFile(b'ZIP'))
        zip_job.files = [{'name': 'z.zip', 'size_bytes': 3, 'storage_path': zip_name}]
        zip_job.save(update_fields=['files'])
        session = ClientSession.objects.create(gallery=gallery, email='visitor@example.test')
        favorite_list = FavoriteList.objects.create(gallery=gallery, client_key=f'k{number}', email='visitor@example.test')
        Favorite.objects.create(gallery=gallery, media_asset=made[0], client_key=f'k{number}', favorite_list=favorite_list,
                                client_session=session)
        DownloadLog.objects.create(gallery=gallery, media_asset=made[0], email='visitor@example.test', ip_address='10.1.2.3')
    Notification.objects.create(user=user, kind=Notification.Kind.PAYMENT, message='hello')
    Feedback.objects.create(user=user, category='bug', subject='s', message='m')
    PasswordResetToken.objects.create(user=user, token_hash=f'{name:0<64}'[:64], expires_at=timezone.now() + timedelta(hours=1))
    if payments:
        for index, state in enumerate((Status.APPROVED, Status.REJECTED)):
            payment = ManualPayment.objects.create(
                user=user, plan=plan, amount=1500, plan_price=1500, reference=f'TX{index}{uuid.uuid4().hex[:10]}', status=state,
                notes='my private note', period_start=timezone.now(), period_end=timezone.now() + timedelta(days=30),
            )
            payment.payment_proof.save('p.png', ContentFile(b'PROOF'), save=True)
    return user, files_under(_ROOT[0]) - before


class Base(TempMedia, APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ROOT[0] = cls.media_root

    def setUp(self):
        cache.clear()
        ensure_seed_plans()
        set_cooling_off(7)
        mail.outbox = []

    def api(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def ask(self, user, **body):
        body.setdefault('password', PASSWORD)
        body.setdefault('email', user.email)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            response = self.api(user).post(f'{BASE}request/', body, format='json')
        return response, callbacks

    def request_ok(self, user, **body):
        response, callbacks = self.ask(user, **body)
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        user.refresh_from_db()
        return callbacks


# ─── REQUEST ─────────────────────────────────────────────────────────────────

class RequestTests(Base):
    def setUp(self):
        super().setUp()
        self.user, _ = make_account('owner1')

    def test_a_wrong_password_is_refused_and_nothing_changes(self):
        response, _ = self.ask(self.user, password='Not-The-Password-1!')
        self.assertEqual((response.status_code, response.data['code']), (400, 'password_wrong'))
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deletion_requested_at)
        self.assertEqual(self.user.token_version, 0)

    def test_a_missing_or_empty_password_is_refused(self):
        for body in ({'password': ''}, {'password': None}, {'password': 12345}):
            response, _ = self.ask(self.user, **body)
            self.assertEqual((response.status_code, response.data['code']), (400, 'password_required'), body)
        response = self.api(self.user).post(f'{BASE}request/', {'email': self.user.email}, format='json')
        self.assertEqual(response.data['code'], 'password_required')
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deletion_requested_at)

    def test_the_typed_email_must_match_the_account(self):
        for typed in ('', 'someone-else@example.test', 'owner1@example.test.evil'):
            response, _ = self.ask(self.user, email=typed)
            self.assertEqual((response.status_code, response.data['code']), (400, 'email_mismatch'), typed)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deletion_requested_at)

    def test_the_typed_email_ignores_case_and_surrounding_spaces(self):
        response, _ = self.ask(self.user, email='  OWNER1@Example.Test ')
        self.assertEqual(response.status_code, 200, response.data)

    def test_anonymous_callers_are_refused_on_every_route_but_the_link(self):
        anonymous = APIClient()
        for method, url in (('get', BASE), ('post', f'{BASE}request/'), ('post', f'{BASE}code/'), ('post', f'{BASE}cancel/')):
            self.assertEqual(getattr(anonymous, method)(url).status_code, 401, url)

    def test_another_users_account_cannot_be_deleted_and_no_route_takes_an_id(self):
        other, _ = make_account('owner2', assets=1)
        response, _ = self.ask(self.user, email=other.email)             # their address typed with MY password
        self.assertEqual(response.data['code'], 'email_mismatch')
        # a body that names someone else is ignored: only the signed-in account is acted on
        self.api(self.user).post(f'{BASE}request/', {
            'password': PASSWORD, 'email': self.user.email, 'user_id': str(other.pk), 'id': str(other.pk)}, format='json')
        other.refresh_from_db()
        self.user.refresh_from_db()
        self.assertIsNone(other.deletion_requested_at)
        self.assertIsNotNone(self.user.deletion_requested_at)
        # and I cannot cancel THEIR deletion either: cancel acts on me only
        set_cooling_off(7)
        self.request_ok(other)
        self.api(self.user).post(f'{BASE}cancel/')                       # mine
        other.refresh_from_db()
        self.assertIsNotNone(other.deletion_requested_at)
        from django.urls import resolve
        for suffix in ('', 'code/', 'request/', 'cancel/', 'cancel-link/'):
            self.assertEqual(resolve(f'/api/v1/auth/account/deletion/{suffix}').kwargs, {}, suffix)     # no id in any route

    def test_staff_cannot_delete_their_own_account_here(self):
        for flags in ({'is_staff': True}, {'is_superuser': True}):
            staff = User.objects.create_user(email=f's{len(flags)}{list(flags)[0]}@example.test', username=f's{list(flags)[0]}', password=PASSWORD, **flags)
            response, _ = self.ask(staff)
            self.assertEqual((response.status_code, response.data['code']), (403, 'staff_cannot_delete'))
            staff.refresh_from_db()
            self.assertIsNone(staff.deletion_requested_at)
            self.assertIn('staff', self.api(staff).get(BASE).data['blockers'])

    def test_a_pending_payment_blocks_the_request_and_says_why(self):
        ManualPayment.objects.create(user=self.user, plan=grant_plan(self.user), amount=1500, plan_price=1500,
                                     reference='WAIT-1', status=Status.PENDING)
        response, _ = self.ask(self.user)
        self.assertEqual((response.status_code, response.data['code']), (409, 'payment_pending'))
        self.assertIn('payment', response.data['error'].lower())
        self.assertIn('waiting for review', response.data['error'])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deletion_requested_at)
        self.assertEqual(self.api(self.user).get(BASE).data['blockers'], ['payment_pending'])
        ManualPayment.objects.filter(reference='WAIT-1').update(status=Status.REJECTED)
        self.assertEqual(self.ask(self.user)[0].status_code, 200)

    def test_approved_and_rejected_payments_do_not_block(self):
        self.assertEqual(self.api(self.user).get(BASE).data['blockers'], [])

    def test_a_second_request_while_pending_is_refused(self):
        self.request_ok(self.user)
        response = self.api(self.user).post(f'{BASE}request/', {'password': PASSWORD, 'email': self.user.email}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (409, 'already_pending'))

    def test_the_request_ends_every_session_stamps_the_dates_and_queues_one_email(self):
        before = timezone.now()
        with mock.patch('apps.users.tasks.send_deletion_requested_email.delay') as queued:
            callbacks = self.request_ok(self.user)
            for callback in callbacks:
                callback()
        queued.assert_called_once_with(str(self.user.pk))
        self.assertEqual(self.user.token_version, 1)
        self.assertGreaterEqual(self.user.deletion_requested_at, before)
        self.assertAlmostEqual(
            (self.user.deletion_scheduled_for - self.user.deletion_requested_at).total_seconds(), 7 * 86400, delta=5)
        self.assertIsNone(self.user.deletion_started_at)
        self.assertTrue(self.user.is_active)         # not suspended: the owner can still sign in and cancel

    def test_the_cooling_off_length_is_the_admin_row(self):
        self.assertEqual(AccountSettings.load().deletion_cooling_off_days, 7)
        set_cooling_off(3)
        self.request_ok(self.user)
        self.assertAlmostEqual(
            (self.user.deletion_scheduled_for - self.user.deletion_requested_at).total_seconds(), 3 * 86400, delta=5)

    def test_zero_days_starts_the_purge_now_and_sends_no_cancel_link(self):
        set_cooling_off(0)
        with mock.patch('apps.users.tasks.purge_account.delay') as purge, \
                mock.patch('apps.users.tasks.send_deletion_requested_email.delay') as requested:
            for callback in self.request_ok(self.user):
                callback()
        purge.assert_called_once_with(str(self.user.pk))
        requested.assert_not_called()
        row = StaffAuditLog.objects.get(action=Action.ACCOUNT_DELETION_REQUESTED, target_id=self.user.pk)
        self.assertEqual(row.reason, 'requested_now')

    def test_the_cooling_off_row_is_validated_and_exists_from_the_migration(self):
        from django.core.exceptions import ValidationError
        AccountSettings.objects.all().delete()
        self.assertEqual(AccountSettings.load().deletion_cooling_off_days, 7)
        row = AccountSettings(deletion_cooling_off_days=91)
        with self.assertRaises(ValidationError):
            row.full_clean()
        self.assertEqual(AccountSettings.objects.count(), 1)

    def test_the_admin_page_for_the_cooling_off_loads(self):
        staff = User.objects.create_superuser(email='root@example.test', username='root', password=PASSWORD)
        client = APIClient()
        client.force_login(staff)
        self.assertEqual(client.get('/admin/users/accountsettings/').status_code, 200)
        self.assertEqual(client.get('/admin/users/accountsettings/1/change/').status_code, 200)


# ─── a password-less account confirms with an emailed code ───────────────────

class CodeTests(Base):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='nopass@example.test', username='nopass', password=None)
        self.assertFalse(self.user.has_usable_password())

    def code_from_mail(self):
        body = mail.outbox[-1].body
        return next(word for word in body.split() if word.isdigit() and len(word) == 6)

    def test_the_status_says_the_account_uses_a_code(self):
        self.assertFalse(self.api(self.user).get(BASE).data['uses_password'])

    def test_a_password_is_not_accepted_and_a_code_is_required(self):
        response, _ = self.ask(self.user, password='anything')
        self.assertEqual((response.status_code, response.data['code']), (400, 'code_invalid'))
        response = self.api(self.user).post(f'{BASE}request/', {'email': self.user.email, 'code': ''}, format='json')
        self.assertEqual(response.data['code'], 'code_invalid')

    def test_the_code_is_emailed_in_the_body_never_the_subject_and_works_once(self):
        sent = self.api(self.user).post(f'{BASE}code/')
        self.assertEqual(sent.status_code, 200, sent.data)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        code = self.code_from_mail()
        self.assertEqual(message.to, ['nopass@example.test'])
        self.assertNotIn(code, message.subject)
        wrong = self.ask(self.user, code='000000' if code != '000000' else '111111')[0]
        self.assertEqual(wrong.data['code'], 'code_invalid')
        good, _ = self.ask(self.user, code=code)
        self.assertEqual(good.status_code, 200, good.data)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.deletion_requested_at)
        # the code is used up
        self.user.deletion_requested_at = None
        self.user.save(update_fields=['deletion_requested_at'])
        again, _ = self.ask(self.user, code=code)
        self.assertEqual(again.data['code'], 'code_invalid')

    @override_settings(ACCOUNT_DELETION_CODE_MAX_TRIES=2)
    def test_too_many_wrong_codes_burn_the_code(self):
        self.api(self.user).post(f'{BASE}code/')
        code = self.code_from_mail()
        for _ in range(2):
            self.assertEqual(self.ask(self.user, code='999999' if code != '999999' else '888888')[0].data['code'], 'code_invalid')
        response, _ = self.ask(self.user, code=code)          # even the right one is dead now
        self.assertEqual(response.data['code'], 'code_invalid')
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deletion_requested_at)

    def test_an_account_with_a_password_cannot_ask_for_a_code(self):
        other = User.objects.create_user(email='haspass@example.test', username='haspass', password=PASSWORD)
        response = self.api(other).post(f'{BASE}code/')
        self.assertEqual((response.status_code, response.data['code']), (400, 'password_account'))
        self.assertEqual(mail.outbox, [])

    def test_a_failed_send_is_a_clean_503_and_leaves_no_usable_code(self):
        with mock.patch('apps.users.account_deletion.safe_send_email', return_value=False):
            response = self.api(self.user).post(f'{BASE}code/')
        self.assertEqual((response.status_code, response.data['code']), (503, 'email_failed'))
        self.assertEqual(self.ask(self.user, code='123456')[0].data['code'], 'code_invalid')


# ─── PENDING ─────────────────────────────────────────────────────────────────

class PendingTests(Base):
    def setUp(self):
        super().setUp()
        self.user, _ = make_account('pend1', assets=1)

    def login(self):
        client = APIClient()
        response = client.post('/api/v1/auth/login/', {'email': self.user.email, 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return client, response

    def test_old_sessions_die_but_a_new_login_works_and_shows_the_pending_state(self):
        client, _ = self.login()
        stale = {name: morsel.value for name, morsel in client.cookies.items() if name in ('access_token', 'refresh_token')}
        self.assertEqual(client.get('/api/v1/auth/me/').status_code, 200)
        self.assertEqual(client.post(f'{BASE}request/', {'password': PASSWORD, 'email': self.user.email}, format='json').status_code, 200)

        old = APIClient()
        old.cookies['access_token'] = stale['access_token']
        old.cookies['refresh_token'] = stale['refresh_token']
        self.assertEqual(old.get('/api/v1/auth/me/').status_code, 401)             # logged out everywhere
        self.assertEqual(old.post('/api/v1/auth/token/refresh/').status_code, 401)

        fresh, response = self.login()                                             # a login during the wait works
        self.assertEqual(set(response.data['user']['deletion']), {'requested_at', 'scheduled_for'})
        me = fresh.get('/api/v1/auth/me/')
        self.assertEqual(me.status_code, 200)
        self.assertIsNotNone(me.data['deletion'])
        status = fresh.get(BASE).data
        self.assertEqual(status['state'], 'pending')

    def test_the_api_is_closed_to_a_pending_account_except_the_cancel_page(self):
        self.request_ok(self.user)
        client, _ = self.login()
        for method, url in (
            ('get', '/api/v1/galleries/'), ('get', '/api/v1/subscriptions/my-subscription/'),
            ('get', '/api/v1/auth/settings/'), ('put', '/api/v1/auth/me/'), ('post', '/api/v1/subscriptions/payments/'),
            ('get', '/api/v1/notifications/'), ('post', '/api/v1/feedback/'),
        ):
            response = getattr(client, method)(url)
            self.assertEqual(response.status_code, 403, f'{method} {url}')
            self.assertEqual(response.data['code'], 'account_pending_deletion', url)
        for url in ('/api/v1/auth/me/', BASE):
            self.assertEqual(client.get(url).status_code, 200, url)
        self.assertEqual(client.post('/api/v1/auth/logout/').status_code, 200)

    def test_an_upload_to_a_closing_account_is_refused_under_the_row_lock(self):
        gallery = Gallery.objects.filter(photographer=self.user).first()
        client = self.api(self.user)                    # force_authenticate: bypasses the token gate on purpose
        self.request_ok(self.user)
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io
        buffer = io.BytesIO()
        Image.new('RGB', (8, 8), 'white').save(buffer, 'JPEG')
        before = MediaAsset.objects.filter(gallery__photographer=self.user).count()
        response = client.post(
            f'/api/v1/photos/{gallery.slug}/upload/', {'image': SimpleUploadedFile('x.jpg', buffer.getvalue(), 'image/jpeg')},
            format='multipart')
        self.assertEqual(response.status_code, 403, getattr(response, 'data', response.content[:200]))
        self.assertEqual(response.data['code'], 'account_pending_deletion')
        self.assertEqual(MediaAsset.objects.filter(gallery__photographer=self.user).count(), before)

    def test_billing_stops_no_payment_can_be_sent(self):
        self.request_ok(self.user)
        from apps.subscriptions import payments
        plan = grant_plan(self.user)
        with self.assertRaises(payments.PaymentError) as caught:
            payments.create_payment(user=self.user, plan=plan, amount=plan.price, reference='LATE-1', proof=None,
                                    proof_type='image/png')
        self.assertEqual(caught.exception.code, 'account_closing')
        self.assertFalse(ManualPayment.objects.filter(reference='LATE-1').exists())

    def test_billing_stops_the_daily_job_skips_a_closing_account(self):
        gone = grant_plan(self.user, days=-10)         # period ended ten days ago: due for the downgrade
        control = User.objects.create_user(email='ctl@example.test', username='ctl', password=PASSWORD)
        grant_plan(control, days=-10)
        self.request_ok(self.user)
        lifecycle.run()
        self.assertEqual(UserSubscription.objects.get(user=self.user).status, 'active')      # untouched
        self.assertEqual(UserSubscription.objects.get(user=control).status, 'expired')       # the control was processed
        self.assertFalse(StaffAuditLog.objects.filter(action=Action.SUBSCRIPTION_DOWNGRADE, target_id=self.user.pk).exists())
        self.assertEqual(Notification.objects.filter(user=self.user, kind__in=('plan_expired', 'plan_expiring')).count(), 0)
        self.assertEqual(gone.key, UserSubscription.objects.get(user=self.user).plan.key)

    def test_staff_cannot_suspend_or_reactivate_a_closing_account(self):
        staff = User.objects.create_user(email='st@example.test', username='st', password=PASSWORD, is_staff=True)
        self.request_ok(self.user)
        client = self.api(staff)
        for action in ('suspend', 'reactivate'):
            response = client.post(f'/api/v1/staff/users/{self.user.pk}/{action}/', {'reason': 'x'}, format='json')
            self.assertEqual((response.status_code, response.data['code']), (409, 'deletion_pending'), action)

    def test_a_purging_account_cannot_sign_in(self):
        self.request_ok(self.user)
        User.objects.filter(pk=self.user.pk).update(deletion_scheduled_for=timezone.now() - timedelta(minutes=1))
        deletion.purge_step(str(self.user.pk))        # first step: the purge begins
        response = APIClient().post('/api/v1/auth/login/', {'email': self.user.email, 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('being deleted', str(response.data))
        wrong = APIClient().post('/api/v1/auth/login/', {'email': self.user.email, 'password': 'Wrong-Pass-1!'}, format='json')
        self.assertNotIn('deleted', str(wrong.data))           # only the right password learns the state


# ─── CANCEL ──────────────────────────────────────────────────────────────────

class CancelTests(Base):
    def setUp(self):
        super().setUp()
        self.user, self.files = make_account('cancel1')

    def fresh_link_token(self):
        deletion.send_requested_email(str(self.user.pk))
        body = mail.outbox[-1].body
        return body.split('#token=')[1].split()[0]

    def snapshot(self):
        return {
            'assets': MediaAsset.objects.filter(gallery__photographer=self.user).count(),
            'galleries': Gallery.objects.filter(photographer=self.user).count(),
            'payments': ManualPayment.objects.filter(user=self.user).count(),
            'sub': list(UserSubscription.objects.filter(user=self.user).values_list('status', 'expires_at')),
            'files': files_under(self.media_root),
        }

    def test_cancel_from_the_signed_in_page_restores_everything(self):
        before = self.snapshot()
        public = f'/api/v1/public/{self.user.username}/'
        slug = Gallery.objects.filter(photographer=self.user).first().slug
        self.assertEqual(APIClient().get(f'{public}{slug}/').status_code, 200)
        self.request_ok(self.user)
        self.assertEqual(APIClient().get(f'{public}{slug}/').status_code, 404)
        response = self.api(self.user).post(f'{BASE}cancel/')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual((self.user.deletion_requested_at, self.user.deletion_scheduled_for, self.user.deletion_cancel_hash),
                         (None, None, None))
        self.assertEqual(APIClient().get(f'{public}{slug}/').status_code, 200)       # the public galleries are back
        self.assertEqual(APIClient().get(public).status_code, 200)                  # and the portfolio
        after = self.snapshot()
        self.assertEqual(after, before)                                             # nothing was deleted at all
        self.assertEqual(self.api(self.user).get(BASE).data['state'], 'none')

    def test_cancel_by_the_emailed_link_works_once_and_needs_no_session(self):
        self.request_ok(self.user)
        token = self.fresh_link_token()
        anonymous = APIClient()
        response = anonymous.post(f'{BASE}cancel-link/', {'token': token}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deletion_requested_at)
        again = anonymous.post(f'{BASE}cancel-link/', {'token': token}, format='json')
        self.assertEqual((again.status_code, again.data['code']), (400, 'cancel_link_invalid'))

    def test_a_wrong_or_malformed_link_token_is_one_plain_refusal(self):
        self.request_ok(self.user)
        self.fresh_link_token()
        for token in ('nope', '', 'x' * 500, None, 12, {'a': 1}):
            response = APIClient().post(f'{BASE}cancel-link/', {'token': token}, format='json')
            self.assertEqual((response.status_code, response.data['code']), (400, 'cancel_link_invalid'), token)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.deletion_requested_at)

    def test_only_the_stored_hash_exists_never_the_token_and_the_newest_link_wins(self):
        self.request_ok(self.user)
        first = self.fresh_link_token()
        second = self.fresh_link_token()
        self.user.refresh_from_db()
        self.assertNotEqual(first, second)
        self.assertNotIn(second, self.user.deletion_cancel_hash)
        self.assertEqual(self.user.deletion_cancel_hash, deletion.hash_token(second))
        self.assertEqual(APIClient().post(f'{BASE}cancel-link/', {'token': first}, format='json').status_code, 400)
        self.assertEqual(APIClient().post(f'{BASE}cancel-link/', {'token': second}, format='json').status_code, 200)

    def test_cancel_after_the_purge_started_is_refused_and_the_link_is_dead(self):
        self.request_ok(self.user)
        token = self.fresh_link_token()
        User.objects.filter(pk=self.user.pk).update(deletion_scheduled_for=timezone.now() - timedelta(minutes=1))
        self.assertEqual(deletion.purge_step(str(self.user.pk)), 'more')
        response = self.api(self.user).post(f'{BASE}cancel/')
        self.assertEqual((response.status_code, response.data['code']), (409, 'purge_started'))
        link = APIClient().post(f'{BASE}cancel-link/', {'token': token}, format='json')
        self.assertEqual(link.data['code'], 'cancel_link_invalid')       # the hash was cleared when the purge began

    def test_cancelling_when_nothing_is_pending_is_a_409(self):
        response = self.api(self.user).post(f'{BASE}cancel/')
        self.assertEqual((response.status_code, response.data['code']), (409, 'not_pending'))

    def test_the_cancel_email_is_not_sent_for_a_cancelled_account(self):
        self.request_ok(self.user)
        self.api(self.user).post(f'{BASE}cancel/')
        mail.outbox = []
        self.assertFalse(deletion.send_requested_email(str(self.user.pk)))
        self.assertEqual(mail.outbox, [])

    def test_a_cancelled_account_is_billed_again_by_the_daily_job(self):
        grant_plan(self.user, days=-10)
        self.request_ok(self.user)
        self.api(self.user).post(f'{BASE}cancel/')
        lifecycle.run()
        self.assertEqual(UserSubscription.objects.get(user=self.user).status, 'expired')


# ─── THE EMAILS ──────────────────────────────────────────────────────────────

class EmailTests(Base):
    def setUp(self):
        super().setUp()
        self.user, _ = make_account('mailer1', assets=1)

    def test_deletion_requested_goes_out_once_with_a_fragment_link_and_a_fixed_subject(self):
        self.request_ok(self.user)
        self.assertTrue(deletion.send_requested_email(str(self.user.pk)))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])
        self.assertEqual(message.subject, 'Your Kyapture account is scheduled for deletion')
        self.assertIn('/cancel-deletion#token=', message.body)
        self.assertNotIn('?token=', message.body)
        self.assertNotIn('token=', message.subject)
        html = message.alternatives[0][0]
        self.assertIn('/cancel-deletion#token=', html)
        self.assertIn('days', message.body)

    def test_account_deleted_goes_to_the_old_address_exactly_once_even_if_the_purge_is_repeated(self):
        self.request_ok(self.user)
        User.objects.filter(pk=self.user.pk).update(deletion_scheduled_for=timezone.now() - timedelta(minutes=1))
        mail.outbox = []
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay',
                        side_effect=lambda email: deletion.send_deleted_email(email)) as queued:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(deletion.run_purge_steps(str(self.user.pk), max_steps=500), 'done')
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(deletion.run_purge_steps(str(self.user.pk), max_steps=500), 'gone')
        self.assertEqual(queued.call_count, 1)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['mailer1@example.test'])
        self.assertEqual(message.subject, 'Your Kyapture account was deleted')
        self.assertNotIn('mailer1@example.test', message.subject)
        self.assertIn('Records of payments', message.body)

    def test_the_task_wrappers_retry_instead_of_raising_to_the_caller_state(self):
        from celery.exceptions import Retry
        from apps.users.tasks import send_account_deleted_email
        with mock.patch('apps.users.account_deletion.send_email', side_effect=RuntimeError('smtp down')):
            with self.assertRaises((Retry, RuntimeError)):
                send_account_deleted_email.apply(args=['x@example.test'], throw=True).get()


# ─── THROTTLES ───────────────────────────────────────────────────────────────

class ThrottleTests(Base):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='thr@example.test', username='thr', password=PASSWORD)

    def test_the_request_is_limited_per_user(self):
        client = self.api(self.user)
        codes = [client.post(f'{BASE}request/', {'password': 'bad', 'email': self.user.email}, format='json').status_code
                 for _ in range(6)]
        self.assertEqual(codes, [400] * 5 + [429])

    def test_the_code_email_is_limited_per_user(self):
        user = User.objects.create_user(email='thr2@example.test', username='thr2', password=None)
        client = self.api(user)
        codes = [client.post(f'{BASE}code/').status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])
        self.assertEqual(len(mail.outbox), 3)

    def test_the_cancel_route_is_limited_per_user(self):
        client = self.api(self.user)
        codes = [client.post(f'{BASE}cancel/').status_code for _ in range(11)]
        self.assertEqual(codes[:10], [409] * 10)
        self.assertEqual(codes[10], 429)

    def test_the_cancel_link_is_limited_per_client_address_and_ignores_a_forged_forwarded_header(self):
        codes = []
        for number in range(11):
            codes.append(APIClient().post(
                f'{BASE}cancel-link/', {'token': f'bad{number}'}, format='json',
                HTTP_X_FORWARDED_FOR=f'203.0.113.{number}').status_code)
        self.assertEqual(codes[:10], [400] * 10)
        self.assertEqual(codes[10], 429)


# ─── PURGE ───────────────────────────────────────────────────────────────────

class PurgeTests(Base):
    def setUp(self):
        super().setUp()
        self.keep, self.keep_files = make_account('keeper', assets=2)           # must be untouched by every purge below
        self.user, self.files = make_account('victim1', assets=3)
        self.uid = str(self.user.pk)
        self.galleries = list(Gallery.objects.filter(photographer=self.user).values_list('pk', flat=True))
        self.keep_counts = self.counts(self.keep)

    def counts(self, user):
        return {
            'galleries': Gallery.objects.filter(photographer=user).count(),
            'assets': MediaAsset.objects.filter(gallery__photographer=user).count(),
            'logs': DownloadLog.objects.filter(gallery__photographer=user).count(),
            'sessions': ClientSession.objects.filter(gallery__photographer=user).count(),
            'favorites': Favorite.objects.filter(gallery__photographer=user).count(),
            'lists': FavoriteList.objects.filter(gallery__photographer=user).count(),
            'jobs': DownloadJob.objects.filter(gallery__photographer=user).count(),
            'payments': ManualPayment.objects.filter(user=user).count(),
            'notifications': Notification.objects.filter(user=user).count(),
            'feedback': Feedback.objects.filter(user=user).count(),
        }

    def close_now(self):
        set_cooling_off(7)
        self.request_ok(self.user)
        User.objects.filter(pk=self.user.pk).update(deletion_scheduled_for=timezone.now() - timedelta(minutes=1))

    def run_all(self):
        with self.captureOnCommitCallbacks(execute=True):
            return deletion.run_purge_steps(self.uid, max_steps=1000)

    def assert_keeper_untouched(self):
        self.assertEqual(self.counts(self.keep), self.keep_counts)
        for path in self.keep_files:
            self.assertTrue(os.path.exists(path), f'the other account lost {path}')
        self.assertTrue(User.objects.filter(pk=self.keep.pk).exists())

    def test_the_whole_account_is_gone_every_file_and_every_row(self):
        self.assertGreater(len(self.files), 20)
        self.assertGreater(get_user_subscription_metrics(self.user)['current_total_storage_bytes'], 0)
        self.close_now()
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay'):
            self.assertEqual(self.run_all(), 'done')
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        leftovers = [path for path in self.files if os.path.exists(path)]
        self.assertEqual(leftovers, [])
        self.assertEqual(self.counts(self.user), {key: 0 for key in self.counts(self.user)})
        self.assertEqual(Gallery.objects.filter(pk__in=self.galleries).count(), 0)
        self.assertFalse(UserSubscription.objects.filter(user_id=self.uid).exists())
        self.assertFalse(PasswordResetToken.objects.filter(user_id=self.uid).exists())
        # storage usage is zero
        self.assertEqual(get_user_subscription_metrics(self.user)['current_total_storage_bytes'], 0)
        self.assertEqual(MediaAsset.objects.filter(gallery__photographer_id=self.uid).count(), 0)
        # no empty directory left behind (debt row 21)
        for folder in (f'photographers/{self.uid}', f'payment_proofs/{self.uid}'):
            for root in (self.media_root,):
                self.assertFalse(os.path.exists(os.path.join(root, folder)), folder)
        self.assert_keeper_untouched()

    def test_purge_orphans_in_dry_run_finds_nothing_of_the_account(self):
        self.close_now()
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay'):
            self.run_all()
        out = StringIO()
        call_command('purge_orphans', '--dry-run', '--min-age-minutes', '0', stdout=out)
        text = out.getvalue()
        self.assertNotIn(self.uid, text)
        for gallery_id in self.galleries:
            self.assertNotIn(str(gallery_id), text)
        self.assertIn('DRY RUN', text)
        # (files of other tests in this class' temporary folder, and the cached Web Size files of any account, are
        # listed by purge_orphans too: it does not know the cache. Only THIS account's tree is asserted.)
        self.assertNotIn(f'payment_proofs/{self.uid}', text)

    def test_visitor_data_goes_with_the_galleries(self):
        self.close_now()
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay'):
            self.run_all()
        for model in (ClientSession, FavoriteList, Favorite, DownloadLog, DownloadJob):
            self.assertEqual(model.objects.filter(gallery_id__in=self.galleries).count(), 0, model.__name__)

    def test_the_purge_does_nothing_before_the_cooling_off_ends_or_for_a_cancelled_request(self):
        self.request_ok(self.user)                                   # scheduled in 7 days
        self.assertEqual(deletion.purge_step(self.uid), 'not_due')
        self.api(self.user).post(f'{BASE}cancel/')
        User.objects.filter(pk=self.user.pk).update(deletion_scheduled_for=timezone.now() - timedelta(days=1))
        self.assertEqual(deletion.purge_step(self.uid), 'noop')      # cancelled: the stale date is not a request
        self.assertEqual(deletion.run_purge_steps(self.uid), 'noop')
        self.assertEqual(deletion.purge_step(str(self.keep.pk)), 'noop')      # never requested
        for path in self.files:
            self.assertTrue(os.path.exists(path))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_one_step_is_bounded_and_files_are_deleted_before_their_rows(self):
        self.close_now()
        order = []
        real = deletion.audit  # noqa: F841 - keep the module imported
        from apps.photos import purge as purge_module
        real_delete = purge_module.delete_object

        def spy(kind, name):
            order.append(('file', name, MediaAsset.objects.filter(original_file=name).exists()))
            real_delete(kind, name)

        with override_settings(ACCOUNT_PURGE_BATCH_ASSETS=2), mock.patch.object(purge_module, 'delete_object', spy):
            total = MediaAsset.objects.filter(gallery__photographer=self.user).count()
            self.assertEqual(deletion.purge_step(self.uid), 'more')          # begins and removes <= 2 assets
            remaining = MediaAsset.objects.filter(gallery__photographer=self.user).count()
            self.assertEqual(total - remaining, 2)
            self.assertEqual(deletion.purge_step(self.uid), 'more')
            self.assertEqual(MediaAsset.objects.filter(gallery__photographer=self.user).count(), remaining - 2)
        originals = [entry for entry in order if '_original' in entry[1]]
        self.assertTrue(originals)
        self.assertTrue(all(row_existed for _, _, row_existed in originals), 'a row was deleted before its file')

    def test_a_failing_file_delete_keeps_the_rows_and_the_next_run_finishes_the_job(self):
        self.close_now()
        from apps.photos import purge as purge_module
        real_delete = purge_module.delete_object
        broken = {'on': True}

        def flaky(kind, name):
            if broken['on'] and name.endswith('_original.jpg') and 'g1-' not in name and kind == 'private' and flaky.hits == 0:
                flaky.hits += 1
                raise OSError('storage unavailable')
            real_delete(kind, name)

        flaky.hits = 0
        with mock.patch.object(purge_module, 'delete_object', flaky):
            outcomes = []
            for _ in range(3):
                outcomes.append(deletion.purge_step(self.uid))
                if outcomes[-1] == 'retry':
                    break
        self.assertEqual(outcomes[-1], 'retry')
        user = User.objects.get(pk=self.user.pk)
        self.assertIsNotNone(user.deletion_started_at)                    # started, not finished
        self.assertTrue(MediaAsset.objects.filter(gallery__photographer=self.user).exists())    # the rows stayed
        remaining_rows = list(MediaAsset.objects.filter(gallery__photographer=self.user))
        self.assertTrue(any(os.path.exists(a.original_file.path) for a in remaining_rows), 'a row lost its file first')
        # the storage is back: a plain run resumes from where it stopped and completes
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay'):
            self.assertEqual(self.run_all(), 'done')
        self.assertEqual([p for p in self.files if os.path.exists(p)], [])
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assert_keeper_untouched()

    def test_a_failing_account_file_keeps_the_account_row_until_it_can_be_deleted(self):
        self.close_now()
        from apps.photos import purge as purge_module
        real_prefix = purge_module.delete_prefix

        def broken_prefix(kind, prefix):
            if prefix.startswith('payment_proofs/'):
                raise OSError('disk gone')
            return real_prefix(kind, prefix)

        with mock.patch.object(purge_module, 'delete_prefix', broken_prefix), \
                mock.patch('apps.users.tasks.send_account_deleted_email.delay') as farewell:
            outcome = deletion.run_purge_steps(self.uid, max_steps=1000)
        self.assertEqual(outcome, 'retry')
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(ManualPayment.objects.filter(user=self.user).count(), 2)       # not anonymised yet
        farewell.assert_not_called()
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay'):
            self.assertEqual(self.run_all(), 'done')

    def test_the_purge_is_idempotent(self):
        self.close_now()
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay') as farewell:
            self.assertEqual(self.run_all(), 'done')
            for _ in range(3):
                self.assertEqual(self.run_all(), 'gone')
                self.assertEqual(deletion.purge_step(self.uid), 'gone')
        self.assertEqual(farewell.call_count, 1)
        self.assertEqual(StaffAuditLog.objects.filter(action=Action.ACCOUNT_DELETION_COMPLETED, target_id=self.uid).count(), 1)
        self.assert_keeper_untouched()

    def test_a_second_runner_is_turned_away_while_one_holds_the_lock(self):
        self.close_now()
        cache.add(f'acctdel:lock:{self.uid}', 1, timeout=60)
        self.assertEqual(deletion.run_purge_steps(self.uid), 'busy')
        self.assertTrue(User.objects.filter(pk=self.user.pk, deletion_started_at__isnull=True).exists())

    def test_the_celery_task_runs_the_purge_to_the_end_without_a_session(self):
        from apps.users.tasks import purge_account
        self.close_now()
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay'), self.captureOnCommitCallbacks(execute=True):
            purge_account.apply(args=[self.uid], throw=True)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_the_beat_sweep_starts_due_accounts_and_resumes_stalled_ones_only(self):
        from apps.users.tasks import sweep_account_deletions
        due, _ = make_account('due1', assets=1)
        later, _ = make_account('later1', assets=1)
        self.request_ok(due)
        self.request_ok(later)
        User.objects.filter(pk=due.pk).update(deletion_scheduled_for=timezone.now() - timedelta(minutes=1))
        with mock.patch('apps.users.tasks.purge_account.delay') as queued:
            self.assertEqual(sweep_account_deletions.apply().get(), 1)
        queued.assert_called_once_with(str(due.pk))
        # a runner touched it a moment ago: left alone; once that mark expires it is resumed
        cache.set(f'acctdel:alive:{due.pk}', 1, timeout=60)
        with mock.patch('apps.users.tasks.purge_account.delay') as queued:
            self.assertEqual(deletion.sweep_due(), 0)
        queued.assert_not_called()
        cache.delete(f'acctdel:alive:{due.pk}')
        User.objects.filter(pk=due.pk).update(deletion_started_at=timezone.now())
        with mock.patch('apps.users.tasks.purge_account.delay') as queued:
            self.assertEqual(deletion.sweep_due(), 1)

    def test_a_promoted_staff_account_is_never_purged(self):
        self.close_now()
        User.objects.filter(pk=self.user.pk).update(is_staff=True)
        self.assertEqual(deletion.purge_step(self.uid), 'noop')
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertIsNone(User.objects.get(pk=self.user.pk).deletion_requested_at)

    def test_an_upload_or_a_payment_while_the_purge_runs_creates_nothing(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io
        from apps.subscriptions import payments
        self.close_now()
        slug = Gallery.objects.filter(photographer=self.user).first().slug
        self.assertEqual(deletion.purge_step(self.uid), 'more')                 # the purge has begun
        buffer = io.BytesIO()
        Image.new('RGB', (8, 8), 'white').save(buffer, 'JPEG')
        before = MediaAsset.objects.filter(gallery__photographer=self.user).count()
        response = self.api(self.user).post(
            f'/api/v1/photos/{slug}/upload/', {'image': SimpleUploadedFile('x.jpg', buffer.getvalue(), 'image/jpeg')},
            format='multipart')
        self.assertEqual((response.status_code, response.data['code']), (403, 'account_pending_deletion'))
        self.assertLessEqual(MediaAsset.objects.filter(gallery__photographer=self.user).count(), before)
        with self.assertRaises(payments.PaymentError):
            payments.create_payment(user=User.objects.get(pk=self.user.pk), plan=grant_plan(self.keep), amount=1, reference='LATE-2',
                                    proof=None, proof_type='image/png')
        self.assertFalse(ManualPayment.objects.filter(reference='LATE-2').exists())
        # and a late sign-in cannot bring the account back to life
        login = APIClient().post('/api/v1/auth/login/', {'email': self.user.email, 'password': PASSWORD}, format='json')
        self.assertEqual(login.status_code, 400)
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay'):
            self.assertEqual(self.run_all(), 'done')
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(MediaAsset.objects.filter(gallery__photographer_id=self.uid).count(), 0)

    def test_the_subscription_is_cancelled_before_it_is_removed(self):
        seen = []

        def record(sender, instance, **kwargs):
            seen.append((instance.user_id, instance.status))

        post_save.connect(record, sender=UserSubscription, weak=False)
        self.addCleanup(post_save.disconnect, record, sender=UserSubscription)
        self.close_now()
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay'):
            self.run_all()
        self.assertIn((self.user.pk, 'cancelled'), seen)
        self.assertFalse(UserSubscription.objects.filter(user_id=self.uid).exists())


# ─── PAYMENTS: anonymised, not deleted ───────────────────────────────────────

class PaymentRecordTests(Base):
    def setUp(self):
        super().setUp()
        self.user, self.files = make_account('payer1', assets=1)
        self.approved = ManualPayment.objects.get(user=self.user, status=Status.APPROVED)
        self.rejected = ManualPayment.objects.get(user=self.user, status=Status.REJECTED)
        self.proofs = [p.payment_proof.path for p in (self.approved, self.rejected)]

    def purge(self):
        self.request_ok(self.user)
        User.objects.filter(pk=self.user.pk).update(deletion_scheduled_for=timezone.now() - timedelta(minutes=1))
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay'), self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(deletion.run_purge_steps(str(self.user.pk), max_steps=1000), 'done')

    def test_the_approved_payment_stays_as_an_anonymised_financial_record(self):
        email = self.user.email
        self.purge()
        kept = ManualPayment.objects.get(pk=self.approved.pk)
        self.assertIsNone(kept.user_id)
        self.assertEqual(kept.payer_hash, deletion.payer_hash(email))
        self.assertEqual(len(kept.payer_hash), 64)
        self.assertEqual((kept.amount, kept.currency, kept.plan_id, kept.reference, kept.status),
                         (self.approved.amount, self.approved.currency, self.approved.plan_id, self.approved.reference, 'approved'))
        self.assertEqual((kept.period_start, kept.period_end, kept.created_at),
                         (self.approved.period_start, self.approved.period_end, self.approved.created_at))
        # what identified the person is gone
        self.assertEqual((kept.notes, kept.proof_type, kept.proof_size), ('', '', 0))
        self.assertFalse(kept.payment_proof)
        row = ManualPayment.objects.filter(pk=kept.pk).values().get()
        for value in row.values():
            self.assertNotIn(email.split('@')[0], str(value))
            self.assertNotIn('private note', str(value))

    def test_the_rejected_payment_and_every_proof_file_are_deleted(self):
        self.purge()
        self.assertFalse(ManualPayment.objects.filter(pk=self.rejected.pk).exists())
        self.assertEqual([p for p in self.proofs if os.path.exists(p)], [])
        self.assertFalse(os.path.exists(os.path.join(self.media_root, 'payment_proofs', str(self.user.pk))))

    def test_the_hash_is_keyed_and_case_blind_and_never_the_plain_address(self):
        self.assertEqual(deletion.payer_hash('A@B.test'), deletion.payer_hash(' a@b.TEST '))
        self.assertNotEqual(deletion.payer_hash('a@b.test'), deletion.payer_hash('a@c.test'))
        import hashlib
        self.assertNotEqual(deletion.payer_hash('a@b.test'), hashlib.sha256(b'a@b.test').hexdigest())

    def test_staff_can_still_list_the_anonymised_record(self):
        self.purge()
        staff = User.objects.create_user(email='review@example.test', username='review', password=PASSWORD, is_staff=True)
        response = self.api(staff).get('/api/v1/staff/payments/?status=approved')
        self.assertEqual(response.status_code, 200, response.data)
        row = next(item for item in response.data['results'] if item['id'] == str(self.approved.pk))
        self.assertIsNone(row['email'])
        self.assertEqual(row['name'], 'Deleted account')
        self.assertFalse(row['has_proof'])

    def test_deleting_a_user_any_other_way_anonymises_the_payments_too(self):
        email = self.user.email
        self.user.delete()                         # shell / Django admin: the pre_delete signal does the same
        kept = ManualPayment.objects.get(pk=self.approved.pk)
        self.assertEqual((kept.user_id, kept.payer_hash), (None, deletion.payer_hash(email)))
        self.assertFalse(ManualPayment.objects.filter(pk=self.rejected.pk).exists())
        self.assertEqual(kept.notes, '')


# ─── THE AUDIT TRAIL ─────────────────────────────────────────────────────────

class AuditTests(Base):
    def setUp(self):
        super().setUp()
        self.user, _ = make_account('audited1', assets=1)

    def test_the_audit_table_has_no_foreign_key_to_the_users_table(self):
        with connection.cursor() as cursor:
            relations = connection.introspection.get_relations(cursor, 'staff_audit_log')
        self.assertEqual(relations, {})
        for field in StaffAuditLog._meta.get_fields():
            self.assertFalse(field.is_relation, field.name)

    def test_a_user_with_audit_rows_can_be_deleted_and_the_rows_stay_untouched(self):
        staff = User.objects.create_user(email='boss@example.test', username='boss', password=PASSWORD, is_staff=True)
        client = self.api(staff)
        self.assertEqual(client.post(f'/api/v1/staff/users/{self.user.pk}/suspend/', {'reason': 'spam'}, format='json').status_code, 200)
        self.assertEqual(client.post(f'/api/v1/staff/users/{self.user.pk}/reactivate/', {'reason': 'ok'}, format='json').status_code, 200)
        uid = self.user.pk
        rows = list(StaffAuditLog.objects.filter(target_id=uid).values())
        self.assertGreaterEqual(len(rows), 2)
        total = StaffAuditLog.objects.count()
        self.user.delete()                                                   # no IntegrityError, no cascade
        self.assertFalse(User.objects.filter(pk=uid).exists())
        self.assertEqual(StaffAuditLog.objects.count(), total)
        self.assertEqual(list(StaffAuditLog.objects.filter(target_id=uid).values()), rows)
        # an audit row of a DELETED actor can still be read
        self.assertEqual(client.get('/api/v1/staff/audit/').status_code, 200)

    def test_the_three_rows_hold_an_id_a_masked_address_and_a_coarse_reason_only(self):
        self.request_ok(self.user)
        self.api(self.user).post(f'{BASE}cancel/')
        self.user.refresh_from_db()
        self.request_ok(self.user)
        User.objects.filter(pk=self.user.pk).update(deletion_scheduled_for=timezone.now() - timedelta(minutes=1))
        with mock.patch('apps.users.tasks.send_account_deleted_email.delay'), self.captureOnCommitCallbacks(execute=True):
            deletion.run_purge_steps(str(self.user.pk), max_steps=1000)
        rows = list(StaffAuditLog.objects.filter(target_id=self.user.pk, action__startswith='account.deletion').order_by('id'))
        self.assertEqual([r.action for r in rows], [
            Action.ACCOUNT_DELETION_REQUESTED, Action.ACCOUNT_DELETION_CANCELLED,
            Action.ACCOUNT_DELETION_REQUESTED, Action.ACCOUNT_DELETION_COMPLETED])
        self.assertEqual([r.reason for r in rows], ['requested', 'cancelled', 'requested', 'completed'])
        for row in rows:
            self.assertEqual(row.actor_id, self.user.pk)
            self.assertEqual(row.target_email, 'a***@example.test')
            self.assertEqual((row.actor_email, row.ip), ('', None))
            text = ' '.join(str(v) for v in (row.actor_email, row.target_email, row.reason, row.ip))
            self.assertNotIn('audited1', text)
            self.assertNotIn(PASSWORD, text)
        link = StaffAuditLog.objects.filter(action=Action.ACCOUNT_DELETION_CANCELLED).first()
        self.assertEqual(link.reason, 'cancelled')

    def test_a_cancel_by_the_link_has_its_own_coarse_reason(self):
        self.request_ok(self.user)
        deletion.send_requested_email(str(self.user.pk))
        token = mail.outbox[-1].body.split('#token=')[1].split()[0]
        APIClient().post(f'{BASE}cancel-link/', {'token': token}, format='json')
        self.assertTrue(StaffAuditLog.objects.filter(action=Action.ACCOUNT_DELETION_CANCELLED, reason='cancelled_by_link').exists())

    def test_the_audit_log_still_refuses_deletes_and_updates(self):
        from apps.users.models import AuditLogImmutable
        self.request_ok(self.user)
        row = StaffAuditLog.objects.filter(target_id=self.user.pk).first()
        with self.assertRaises(AuditLogImmutable):
            row.delete()
        with self.assertRaises(AuditLogImmutable):
            StaffAuditLog.objects.filter(pk=row.pk).update(reason='x')

    def test_no_log_line_holds_the_password_a_code_a_token_or_the_address(self):
        records = []

        class Collect(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Collect(level=logging.DEBUG)
        root = logging.getLogger()
        root.addHandler(handler)
        previous = root.level
        root.setLevel(logging.DEBUG)
        try:
            self.request_ok(self.user)
            deletion.send_requested_email(str(self.user.pk))
            token = mail.outbox[-1].body.split('#token=')[1].split()[0]
            self.api(self.user).post(f'{BASE}cancel/')
            self.user.refresh_from_db()
            self.request_ok(self.user)
            User.objects.filter(pk=self.user.pk).update(deletion_scheduled_for=timezone.now() - timedelta(minutes=1))
            with mock.patch('apps.users.tasks.send_account_deleted_email.delay'), self.captureOnCommitCallbacks(execute=True):
                deletion.run_purge_steps(str(self.user.pk), max_steps=1000)
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)
        joined = '\n'.join(records)
        for secret in (PASSWORD, token, 'audited1@example.test'):
            self.assertNotIn(secret, joined)


# ─── RACES (real threads) ────────────────────────────────────────────────────

class RaceTests(TransactionTestCase):
    """A cancel and the start of the purge both take the row lock: exactly one wins, never both."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email='racer@example.test', username='racer', password=PASSWORD)
        now = timezone.now()
        User.objects.filter(pk=self.user.pk).update(
            deletion_requested_at=now - timedelta(days=8), deletion_scheduled_for=now - timedelta(minutes=1))

    def test_a_cancel_and_the_purge_start_never_both_win(self):
        results = {}
        barrier = threading.Barrier(2)

        def cancel():
            try:
                barrier.wait(5)
                deletion.cancel_deletion(user=self.user)
                results['cancel'] = 'ok'
            except deletion.DeletionError as problem:
                results['cancel'] = problem.code
            finally:
                connections.close_all()

        def purge():
            try:
                barrier.wait(5)
                results['purge'] = deletion.purge_step(str(self.user.pk))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=cancel), threading.Thread(target=purge)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        user = User.objects.filter(pk=self.user.pk).first()
        if results['cancel'] == 'ok':
            self.assertEqual(results['purge'], 'noop')                   # the purge saw the cancel under the lock
            self.assertIsNone(user.deletion_requested_at)
            self.assertIsNone(user.deletion_started_at)
            self.assertTrue(user.is_active)
        else:
            self.assertEqual(results['cancel'], 'purge_started')         # the purge won; a gallery-less account ends in that step
            self.assertEqual(results['purge'], 'done')
            self.assertIsNone(user)

    def test_two_purge_runners_at_once_delete_the_account_once_and_send_one_notice(self):
        results = []
        barrier = threading.Barrier(2)

        def runner():
            try:
                barrier.wait(5)
                for _ in range(3):
                    results.append(deletion.purge_step(str(self.user.pk)))
            finally:
                connections.close_all()

        with mock.patch('apps.users.tasks.send_account_deleted_email.delay') as sent:
            threads = [threading.Thread(target=runner) for _ in range(2)]
            [t.start() for t in threads]
            [t.join(60) for t in threads]
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(results.count('done'), 1)
        self.assertEqual(sent.call_count, 1)
        self.assertEqual(StaffAuditLog.objects.filter(action=Action.ACCOUNT_DELETION_COMPLETED).count(), 1)
