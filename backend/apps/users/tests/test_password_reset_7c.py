# backend/apps/users/tests/test_password_reset_7c.py
"""
CHUNK 7-C - forgot password -> one-time short-lived link -> new password ->
link dead -> every session revoked -> "password changed" email.

  - The link: 256 random bits, only its SHA-256 stored, in the URL fragment of a
    FRONTEND_URL link (a forged Host / X-Forwarded-Host never changes it), works
    once, expires after PASSWORD_RESET_TOKEN_MINUTES, dies when a newer link is
    requested and when any password change revokes the sessions.
  - Enumeration: known, unknown and inactive addresses get the same status and
    body; the request does no database work at all (the Celery task looks the
    account up), so its timing cannot depend on the account.
  - Abuse: per typed address 3 emails an hour, silently (same 200); per client
    address a 429.
  - Revocation (one mechanism, `User.token_version` in every JWT's `tv` claim):
    after a reset or a change, every access token (cookie AND bearer) and every
    refresh token is refused on its next use; Django admin sessions end; pending
    links are deleted; the login failure counters of the account are cleared.
  - Policy: the registration validators, not the email, not the current password.
  - Accounts without a usable password can reset (and nothing 500s).
  - No password or token in logs, error bodies, emails other than the link, or the bell.
"""
import hashlib
import logging
import re
import statistics
import time
from contextlib import contextmanager
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users import tasks
from apps.users.models import Notification, PasswordResetToken, User
from apps.users.password_reset import hash_token, issue_token

RESET_URL = '/api/v1/auth/password/reset/'
CHECK_URL = '/api/v1/auth/password/reset/check/'
CONFIRM_URL = '/api/v1/auth/password/reset/confirm/'
LOGIN_URL = '/api/v1/auth/login/'
REFRESH_URL = '/api/v1/auth/token/refresh/'
ME_URL = '/api/v1/auth/me/'
CHANGE_URL = '/api/v1/auth/change-password/'
LOGOUT_ALL_URL = '/api/v1/auth/logout-all/'

OLD_PASSWORD = 'OldPassword123!'
NEW_PASSWORD = 'Fresh-Lantern-842'
LINK_RE = re.compile(r'(\S+)/reset-password#token=([A-Za-z0-9_-]+)')


def run_inline(*task_objs):
    """Run the given Celery tasks synchronously in the test process (never through a broker)."""
    @contextmanager
    def ctx():
        patches = [
            mock.patch.object(t, 'delay', side_effect=lambda *a, _t=t, **k: _t.apply(args=a, kwargs=k))
            for t in task_objs
        ]
        for p in patches:
            p.start()
        try:
            yield
        finally:
            for p in patches:
                p.stop()
    return ctx()


class ResetTestBase(APITestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.user = User.objects.create_user(
            username='resetowner', email='owner-7c@example.com', password=OLD_PASSWORD, display_name='Owner',
        )

    def request_reset(self, email, client=None, **extra):
        """POST the forgot form with the email task run inline; returns the response."""
        client = client or self.client
        with run_inline(tasks.send_password_reset_email_task), self.captureOnCommitCallbacks(execute=True):
            return client.post(RESET_URL, {'email': email}, format='json', **extra)

    def last_link(self):
        match = LINK_RE.search(mail.outbox[-1].body)
        self.assertIsNotNone(match, mail.outbox[-1].body)
        return match.group(1), match.group(2)

    def confirm(self, token, password=NEW_PASSWORD, password2=None, client=None):
        client = client or APIClient()
        with run_inline(tasks.send_password_changed_email_task), self.captureOnCommitCallbacks(execute=True):
            return client.post(CONFIRM_URL, {
                'token': token, 'new_password': password,
                'new_password2': password if password2 is None else password2,
            }, format='json')

    def login(self, password=OLD_PASSWORD):
        client = APIClient()
        response = client.post(LOGIN_URL, {'email': self.user.email, 'password': password}, format='json')
        return client, response


class ResetLinkTests(ResetTestBase):
    def test_known_email_gets_one_fragment_link_on_the_frontend_host(self):
        with override_settings(FRONTEND_URL='https://app.example.test'):
            response = self.request_reset('Owner-7C@Example.com ')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['owner-7c@example.com'])
        host, token = self.last_link()
        self.assertEqual(host, 'https://app.example.test')
        self.assertGreaterEqual(len(token), 43)                       # 256 random bits, url-safe
        self.assertIn(f'#token={token}', mail.outbox[0].alternatives[0][0])

    def test_only_the_hash_is_stored(self):
        self.request_reset(self.user.email)
        _, token = self.last_link()
        row = PasswordResetToken.objects.get(user=self.user)
        self.assertEqual(row.token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertFalse(PasswordResetToken.objects.filter(token_hash=token).exists())
        self.assertNotIn(token, str(list(PasswordResetToken.objects.values())))

    @override_settings(ALLOWED_HOSTS=['*'], USE_X_FORWARDED_HOST=True, FRONTEND_URL='https://app.example.test')
    def test_a_forged_host_header_does_not_change_the_link(self):
        """Password-reset poisoning: the link host comes from FRONTEND_URL only."""
        self.request_reset(self.user.email, HTTP_HOST='evil.example', HTTP_X_FORWARDED_HOST='evil.example')
        host, _ = self.last_link()
        self.assertEqual(host, 'https://app.example.test')
        self.assertNotIn('evil.example', mail.outbox[0].body)
        self.assertNotIn('evil.example', mail.outbox[0].alternatives[0][0])

    @override_settings(PASSWORD_RESET_TOKEN_MINUTES=7)
    def test_expiry_comes_from_settings_and_is_in_the_email(self):
        before = timezone.now()
        self.request_reset(self.user.email)
        row = PasswordResetToken.objects.get(user=self.user)
        self.assertAlmostEqual((row.expires_at - before).total_seconds(), 7 * 60, delta=5)
        self.assertIn('expires in 7 minutes', mail.outbox[0].body)

    def test_a_newer_request_kills_the_older_link(self):
        self.request_reset(self.user.email)
        _, first = self.last_link()
        self.request_reset(self.user.email)
        _, second = self.last_link()
        self.assertNotEqual(first, second)
        self.assertEqual(self.client.post(CHECK_URL, {'token': first}, format='json').status_code, 400)
        self.assertEqual(self.confirm(first).data['code'], 'reset_link_invalid')
        self.assertEqual(self.confirm(second).status_code, 200)

    def test_expired_rows_are_purged_when_a_link_is_issued(self):
        other = User.objects.create_user(username='other7c', email='other-7c@example.com', password=OLD_PASSWORD)
        issue_token(other)
        PasswordResetToken.objects.filter(user=other).update(expires_at=timezone.now() - timedelta(seconds=1))
        issue_token(self.user)
        self.assertFalse(PasswordResetToken.objects.filter(user=other).exists())


class EnumerationTests(ResetTestBase):
    def test_known_unknown_and_inactive_addresses_get_the_same_answer(self):
        User.objects.create_user(username='sleeper', email='inactive-7c@example.com', password=OLD_PASSWORD,
                                 is_active=False)
        answers = []
        for email in ('owner-7c@example.com', 'nobody-7c@example.com', 'inactive-7c@example.com'):
            cache.clear()
            response = self.request_reset(email)
            answers.append((response.status_code, response.content, response.get('Content-Type')))
        self.assertEqual(answers[0], answers[1])
        self.assertEqual(answers[0], answers[2])
        self.assertEqual([m.to for m in mail.outbox], [['owner-7c@example.com']])

    def test_the_request_does_no_database_work_for_any_address(self):
        """The account lookup happens in the Celery task, so the request path is identical."""
        with mock.patch.object(tasks.send_password_reset_email_task, 'delay') as delay:
            for email in ('owner-7c@example.com', 'nobody-7c@example.com'):
                cache.clear()
                with self.assertNumQueries(0), self.captureOnCommitCallbacks(execute=True):
                    self.assertEqual(self.client.post(RESET_URL, {'email': email}, format='json').status_code, 200)
        self.assertEqual([c.args for c in delay.call_args_list], [('owner-7c@example.com',), ('nobody-7c@example.com',)])

    def test_known_and_unknown_take_about_the_same_time(self):
        def timed(email):
            cache.clear()
            start = time.perf_counter()
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(RESET_URL, {'email': email}, format='json')
            return time.perf_counter() - start

        with mock.patch.object(tasks.send_password_reset_email_task, 'delay'):
            timed('warm-up@example.com')
            known = [timed('owner-7c@example.com') for _ in range(9)]
            unknown = [timed('nobody-7c@example.com') for _ in range(9)]
        diff = abs(statistics.median(known) - statistics.median(unknown))
        self.assertLess(diff, 0.02, f'known {statistics.median(known):.4f}s vs unknown {statistics.median(unknown):.4f}s')

    def test_a_malformed_address_is_a_400_whoever_asks(self):
        for bad in ('', 'not-an-email', 'a@b', 'x' * 250 + '@example.com', None):
            response = self.client.post(RESET_URL, {'email': bad}, format='json')
            self.assertEqual(response.status_code, 400, bad)
            self.assertEqual(response.data['code'], 'email_invalid')

    def test_a_broker_outage_still_gives_the_same_answer(self):
        with mock.patch.object(tasks.send_password_reset_email_task, 'delay', side_effect=ConnectionError('down')), \
                self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(RESET_URL, {'email': self.user.email}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_the_check_and_confirm_answers_never_echo_the_token(self):
        bogus = 'A' * 43
        for url, body in ((CHECK_URL, {'token': bogus}),
                          (CONFIRM_URL, {'token': bogus, 'new_password': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})):
            response = self.client.post(url, body, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertNotIn(bogus, response.content.decode())
            self.assertNotIn(NEW_PASSWORD, response.content.decode())


class ResetThrottleTests(ResetTestBase):
    def test_three_emails_an_hour_per_address_then_silence_with_the_same_answer(self):
        with mock.patch.object(tasks.send_password_reset_email_task, 'delay') as delay:
            responses = []
            for i in range(5):
                with self.captureOnCommitCallbacks(execute=True):
                    responses.append(self.client.post(RESET_URL, {'email': self.user.email}, format='json',
                                                      REMOTE_ADDR=f'192.0.2.{i + 1}'))
        self.assertEqual({r.status_code for r in responses}, {200})
        self.assertEqual(len({r.content for r in responses}), 1)
        self.assertEqual(delay.call_count, 3)

    def test_the_per_address_limit_counts_unknown_addresses_too(self):
        with mock.patch.object(tasks.send_password_reset_email_task, 'delay') as delay:
            for i in range(4):
                with self.captureOnCommitCallbacks(execute=True):
                    self.client.post(RESET_URL, {'email': 'ghost-7c@example.com'}, format='json',
                                     REMOTE_ADDR=f'192.0.2.{i + 1}')
        self.assertEqual(delay.call_count, 3)

    def test_the_per_address_limit_also_caps_real_mail(self):
        for i in range(5):
            self.request_reset(self.user.email, REMOTE_ADDR=f'192.0.2.{i + 1}')
        self.assertEqual(len(mail.outbox), 3)

    def test_one_client_address_is_limited_whatever_email_it_types(self):
        with mock.patch.object(tasks.send_password_reset_email_task, 'delay'):
            codes = [self.client.post(RESET_URL, {'email': f'probe{i}@example.com'}, format='json').status_code
                     for i in range(11)]
        self.assertEqual(codes, [200] * 10 + [429])

    def test_a_spoofed_forwarded_for_does_not_reset_the_client_limit(self):
        with mock.patch.object(tasks.send_password_reset_email_task, 'delay'):
            codes = [self.client.post(RESET_URL, {'email': f'probe{i}@example.com'}, format='json',
                                      HTTP_X_FORWARDED_FOR=f'203.0.113.{i}').status_code for i in range(11)]
        self.assertEqual(codes[-1], 429)

    def test_link_checks_and_submissions_are_limited_per_client(self):
        codes = [self.client.post(CHECK_URL, {'token': f'guess-{i}'}, format='json').status_code for i in range(31)]
        self.assertEqual(codes[:30], [400] * 30)
        self.assertEqual(codes[30], 429)


class ConfirmTests(ResetTestBase):
    def test_a_valid_link_sets_the_new_password(self):
        self.request_reset(self.user.email)
        _, token = self.last_link()
        self.assertEqual(self.client.post(CHECK_URL, {'token': token}, format='json').data, {'valid': True})
        response = self.confirm(token)
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertEqual(self.login(OLD_PASSWORD)[1].status_code, 400)
        self.assertEqual(self.login(NEW_PASSWORD)[1].status_code, 200)

    def test_the_check_does_not_use_the_link_up(self):
        token = issue_token(self.user)
        for _ in range(3):
            self.assertEqual(self.client.post(CHECK_URL, {'token': token}, format='json').status_code, 200)
        self.assertEqual(self.confirm(token).status_code, 200)

    def test_a_link_works_once(self):
        token = issue_token(self.user)
        self.assertEqual(self.confirm(token).status_code, 200)
        again = self.confirm(token, password='Another-Lantern-913')
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.data['code'], 'reset_link_invalid')
        self.assertEqual(self.client.post(CHECK_URL, {'token': token}, format='json').status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(PasswordResetToken.objects.filter(user=self.user).exists())

    def test_an_expired_link_is_refused(self):
        token = issue_token(self.user)
        PasswordResetToken.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.post(CHECK_URL, {'token': token}, format='json').status_code, 400)
        response = self.confirm(token)
        self.assertEqual(response.data['code'], 'reset_link_invalid')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_a_link_of_a_deactivated_account_is_refused(self):
        token = issue_token(self.user)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.confirm(token).data['code'], 'reset_link_invalid')

    def test_wrong_missing_and_oversized_tokens_are_refused(self):
        issue_token(self.user)
        for bad in ('wrong-token', '', 'x' * 5000, None, 12345):
            response = self.confirm(bad)
            self.assertEqual(response.status_code, 400, bad)
            self.assertEqual(response.data['code'], 'reset_link_invalid')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_a_link_changes_only_its_own_account(self):
        other = User.objects.create_user(username='bystander', email='bystander-7c@example.com', password=OLD_PASSWORD)
        other_client, _ = APIClient(), None
        other_client.post(LOGIN_URL, {'email': other.email, 'password': OLD_PASSWORD}, format='json')
        other_token = issue_token(other)
        token = issue_token(self.user)

        self.assertEqual(self.confirm(token).status_code, 200)
        other.refresh_from_db()
        self.assertTrue(other.check_password(OLD_PASSWORD))
        self.assertEqual(other.token_version, 0)
        self.assertEqual(other_client.get(ME_URL).status_code, 200)       # their session lives on
        self.assertEqual(self.client.post(CHECK_URL, {'token': other_token}, format='json').status_code, 200)

    def test_mismatched_passwords_are_refused_and_keep_the_link(self):
        token = issue_token(self.user)
        response = self.confirm(token, password2='Something-Else-77')
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password2', response.data)
        self.assertEqual(self.confirm(token).status_code, 200)

    def test_the_password_policy_is_the_registration_policy(self):
        token = issue_token(self.user)
        cases = {
            'short': 'Ab1!',
            'common': 'password123',
            'numeric': '8429137465',
            'email': 'owner-7c@example.com',
            'email-case': 'Owner-7C@Example.com',
            'old': OLD_PASSWORD,
        }
        for label, password in cases.items():
            response = self.confirm(token, password=password)
            self.assertEqual(response.status_code, 400, label)
            self.assertIn('new_password', response.data, label)
            self.assertNotIn(password, response.content.decode(), label)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))
        self.assertEqual(self.confirm(token).status_code, 200)      # the link survived the refusals

    def test_registration_refuses_the_email_as_password_too(self):
        response = self.client.post('/api/v1/auth/register/', {
            'email': 'newbie-7c@example.com', 'username': 'newbie7c', 'display_name': 'N',
            'password': 'newbie-7c@example.com', 'password2': 'newbie-7c@example.com',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data)


class SessionRevocationTests(ResetTestBase):
    def assert_session_dead(self, client, bearer, refresh):
        self.assertEqual(client.get(ME_URL).status_code, 401, 'access cookie still works')
        bearer_client = APIClient()
        bearer_client.credentials(HTTP_AUTHORIZATION=f'Bearer {bearer}')
        self.assertEqual(bearer_client.get(ME_URL).status_code, 401, 'bearer access token still works')
        refresher = APIClient()
        refresher.cookies['refresh_token'] = refresh
        self.assertEqual(refresher.post(REFRESH_URL).status_code, 401, 'refresh token still works')

    def logged_in_device(self, password=OLD_PASSWORD):
        client, response = self.login(password)
        self.assertEqual(response.status_code, 200)
        access = response.cookies['access_token'].value
        refresh = response.cookies['refresh_token'].value
        self.assertEqual(client.get(ME_URL).status_code, 200)
        return client, access, refresh

    def test_a_reset_kills_every_access_and_refresh_token_at_once(self):
        devices = [self.logged_in_device() for _ in range(2)]
        token = issue_token(self.user)
        response = self.confirm(token)
        self.assertEqual(response.status_code, 200)
        # The answer clears this browser's auth cookies too.
        self.assertEqual(response.cookies['access_token'].value, '')
        for client, access, refresh in devices:
            self.assert_session_dead(client, access, refresh)
        self.assertEqual(self.logged_in_device(NEW_PASSWORD)[0].get(ME_URL).status_code, 200)

    def test_a_token_minted_before_7c_dies_on_reset(self):
        """Old tokens carry no `tv` claim (version 0): valid until the first revocation."""
        legacy = RefreshToken.for_user(self.user)
        bearer = APIClient()
        bearer.credentials(HTTP_AUTHORIZATION=f'Bearer {legacy.access_token}')
        self.assertEqual(bearer.get(ME_URL).status_code, 200)
        self.confirm(issue_token(self.user))
        self.assertEqual(bearer.get(ME_URL).status_code, 401)

    def test_a_password_change_kills_other_devices_now_and_keeps_this_one(self):
        other_device, other_access, other_refresh = self.logged_in_device()
        this_device, _, _ = self.logged_in_device()
        pending = issue_token(self.user)
        with run_inline(tasks.send_password_changed_email_task), self.captureOnCommitCallbacks(execute=True):
            response = this_device.put(CHANGE_URL, {
                'old_password': OLD_PASSWORD, 'new_password': NEW_PASSWORD, 'new_password2': NEW_PASSWORD,
            }, format='json', HTTP_X_CSRFTOKEN=this_device.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_session_dead(other_device, other_access, other_refresh)
        self.assertEqual(this_device.get(ME_URL).status_code, 200)
        self.assertEqual(self.confirm(pending).data['code'], 'reset_link_invalid')

    def test_logout_all_kills_access_tokens_too(self):
        other_device, other_access, other_refresh = self.logged_in_device()
        this_device, _, _ = self.logged_in_device()
        response = this_device.post(LOGOUT_ALL_URL, {}, format='json',
                                    HTTP_X_CSRFTOKEN=this_device.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 200)
        self.assert_session_dead(other_device, other_access, other_refresh)

    def test_a_reset_ends_django_admin_sessions(self):
        User.objects.filter(pk=self.user.pk).update(is_staff=True, is_superuser=True)
        admin = APIClient()
        admin.force_login(User.objects.get(pk=self.user.pk))
        self.assertEqual(admin.get('/admin/').status_code, 200)
        self.confirm(issue_token(self.user))
        response = admin.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_a_reset_clears_the_login_failure_counters_of_the_account(self):
        digest = hashlib.sha256(self.user.email.encode()).hexdigest()
        keys = [f'throttle_login_account_{digest}', f'adminlogin:acct:{digest}', f'adminlogin:acct:{digest}:lock']
        for key in keys:
            cache.set(key, [time.time()] * 20, timeout=3600)
        self.confirm(issue_token(self.user))
        self.assertEqual([cache.get(key) for key in keys], [None, None, None])

    def test_the_bell_and_logs_never_see_the_token_or_password(self):
        notifications_before = Notification.objects.count()
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger('apps').info('start')          # assertLogs needs at least one record
            self.request_reset(self.user.email)
            _, token = self.last_link()
            self.client.post(CHECK_URL, {'token': token}, format='json')
            self.confirm(token, password='weak')
            self.confirm(token)
        text = '\n'.join(logs.output)
        self.assertNotIn(token, text)
        self.assertNotIn(hash_token(token), text)
        self.assertNotIn(NEW_PASSWORD, text)
        self.assertEqual(Notification.objects.count(), notifications_before)


class PasswordChangedEmailTests(ResetTestBase):
    def test_a_reset_tells_the_owner(self):
        self.request_reset(self.user.email)
        _, token = self.last_link()
        self.confirm(token)
        changed = mail.outbox[-1]
        self.assertEqual(changed.to, ['owner-7c@example.com'])
        self.assertEqual(changed.subject, 'Your Kyapture password was changed')
        self.assertIn('using a password reset link', changed.body)
        self.assertIn('/forgot-password', changed.body)
        for body in (changed.body, changed.alternatives[0][0]):
            self.assertNotIn(NEW_PASSWORD, body)
            self.assertNotIn(token, body)

    def test_a_password_change_tells_the_owner(self):
        device, _ = self.login()
        with run_inline(tasks.send_password_changed_email_task), self.captureOnCommitCallbacks(execute=True):
            device.put(CHANGE_URL, {
                'old_password': OLD_PASSWORD, 'new_password': NEW_PASSWORD, 'new_password2': NEW_PASSWORD,
            }, format='json', HTTP_X_CSRFTOKEN=device.cookies['csrftoken'].value)
        self.assertEqual([m.subject for m in mail.outbox], ['Your Kyapture password was changed'])
        self.assertNotIn('reset link', mail.outbox[0].body)
        self.assertNotIn(NEW_PASSWORD, mail.outbox[0].body)

    def test_a_refused_reset_sends_nothing(self):
        token = issue_token(self.user)
        self.confirm(token, password='weak')
        self.assertEqual(mail.outbox, [])


class NoUsablePasswordTests(ResetTestBase):
    """A future social-login account has no usable password: the flow must still work."""

    def setUp(self):
        super().setUp()
        self.user.set_unusable_password()
        self.user.save()

    def test_it_can_request_and_use_a_link(self):
        self.request_reset(self.user.email)
        _, token = self.last_link()
        self.assertEqual(self.confirm(token).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_password_change_answers_400_not_500(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.put(CHANGE_URL, {
            'old_password': 'anything', 'new_password': NEW_PASSWORD, 'new_password2': NEW_PASSWORD,
        }, format='json')
        self.assertEqual(response.status_code, 400)


class MailSettingsTests(APITestCase):
    """Mail is configured from the environment only (read from the real production module)."""

    def test_production_uses_ses_unless_smtp_is_configured_with_tls(self):
        from apps.users.tests.test_security_7b import PROD_ENV, settings_in_subprocess

        expr = '[m.EMAIL_BACKEND, m.EMAIL_HOST, m.EMAIL_PORT, m.EMAIL_HOST_USER, m.EMAIL_USE_TLS]'
        self.assertEqual(settings_in_subprocess('config.settings.production', PROD_ENV, expr)[0],
                         'django_ses.SESBackend')
        smtp = {**PROD_ENV, 'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
                'EMAIL_HOST': 'smtp.example.test', 'EMAIL_PORT': '587', 'EMAIL_HOST_USER': 'mailer',
                'EMAIL_HOST_PASSWORD': 'from-env-only', 'EMAIL_USE_TLS': 'true'}
        self.assertEqual(settings_in_subprocess('config.settings.production', smtp, expr),
                         ['django.core.mail.backends.smtp.EmailBackend', 'smtp.example.test', 587, 'mailer', True])
        with self.assertRaises(AssertionError) as caught:
            settings_in_subprocess('config.settings.production', {**smtp, 'EMAIL_USE_TLS': 'false'}, expr)
        self.assertIn('EMAIL_USE_TLS', str(caught.exception))


class AdminPasswordChangeTests(ResetTestBase):
    """A password a staff member sets in Django admin ends the account's sessions too."""

    def test_a_password_set_in_django_admin_ends_the_sessions(self):
        staff = User.objects.create_user(username='staff7c', email='staff-7c@example.com', password=OLD_PASSWORD)
        User.objects.filter(pk=staff.pk).update(is_staff=True, is_superuser=True)
        device, response = self.login()
        bearer = response.cookies['access_token'].value
        admin = APIClient()
        admin.force_login(User.objects.get(pk=staff.pk))
        with run_inline(tasks.send_password_changed_email_task), self.captureOnCommitCallbacks(execute=True):
            page = admin.post(f'/admin/users/user/{self.user.pk}/password/', {
                'password1': NEW_PASSWORD, 'password2': NEW_PASSWORD, 'usable_password': 'true',
            })
        self.assertEqual(page.status_code, 302, getattr(page, 'content', b'')[:500])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertEqual(device.get(ME_URL).status_code, 401)
        other = APIClient()
        other.credentials(HTTP_AUTHORIZATION=f'Bearer {bearer}')
        self.assertEqual(other.get(ME_URL).status_code, 401)
        self.assertEqual([m.subject for m in mail.outbox], ['Your Kyapture password was changed'])
        self.assertIn('by the Kyapture team', mail.outbox[0].body)
