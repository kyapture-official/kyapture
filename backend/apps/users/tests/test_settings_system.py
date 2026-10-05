# backend/apps/users/tests/test_settings_system.py
"""
Settings system — profile, security/sessions, notifications, plan & billing
reads, Collection Defaults, privacy.

Every Settings API is scoped to request.user: none takes an id, and the tests
below probe for that explicitly (mass-assignment, foreign ids, unknown keys).
"""
import io
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.clients.models import DownloadLog, Favorite
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.subscriptions.models import ManualPayment, SubscriptionPlan
from apps.subscriptions.testing import grant_plan
from apps.users.notifications import deliver_notification

User = get_user_model()

ME = '/api/v1/auth/me/'
SETTINGS = '/api/v1/auth/settings/'
CHANGE_PW = '/api/v1/auth/change-password/'
LOGOUT_ALL = '/api/v1/auth/logout-all/'
LOGIN = '/api/v1/auth/login/'
REFRESH = '/api/v1/auth/token/refresh/'
PASSWORD = 'Sturdy-Pass-8842!'


def png(size=(120, 120), color=(30, 90, 160), name='avatar.png'):
    out = io.BytesIO()
    Image.new('RGBA', size, color + (255,)).save(out, format='PNG')
    return SimpleUploadedFile(name, out.getvalue(), 'image/png')


class SettingsBase(APITestCase):
    def make_user(self, name, **extra):
        return User.objects.create_user(
            email=f'{name}@kyapture.com', password=PASSWORD, username=name,
            display_name=name.title(), **extra,
        )

    def setUp(self):
        cache.clear()
        self.user = self.make_user('settingsuser')
        self.other = self.make_user('someoneelse')
        self.client.force_authenticate(user=self.user)


# ─────────────────────────────────────────────────────────────────────────────
class ProfileTests(SettingsBase):
    def test_reads_own_profile_without_sensitive_fields(self):
        response = self.client.get(ME)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email'], 'settingsuser@kyapture.com')
        self.assertEqual(response.data['username'], 'settingsuser')
        for field in ('password', 'is_staff', 'is_superuser', 'groups', 'user_permissions',
                      'notify_downloads', 'collection_defaults', 'portfolio_public'):
            self.assertNotIn(field, response.data)

    def test_updates_own_profile(self):
        response = self.client.put(ME, {
            'display_name': 'Aster Studio', 'bio': 'Weddings & portraits', 'phone': '+977 98-1234 5678',
            'website': 'https://aster.example.com',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, 'Aster Studio')
        self.assertEqual(self.user.bio, 'Weddings & portraits')
        self.assertEqual(self.user.phone, '+977 98-1234 5678')
        self.assertEqual(self.client.get(ME).data['display_name'], 'Aster Studio')      # survives a re-read

    def test_markup_is_stripped_from_text_fields(self):
        self.client.put(ME, {'display_name': '<b>Aster</b><script>x()</script>', 'bio': '<img src=x onerror=1>hi'},
                        format='json')
        self.user.refresh_from_db()
        self.assertNotIn('<', self.user.display_name)
        self.assertNotIn('<', self.user.bio)

    def test_invalid_data_is_rejected_with_field_errors(self):
        for payload, field in (
            ({'display_name': '   '}, 'display_name'),
            ({'display_name': 'x' * 101}, 'display_name'),
            ({'phone': 'call me maybe'}, 'phone'),
            ({'website': 'not a url'}, 'website'),
            ({'branding_color': 'red'}, 'branding_color'),
            ({'username': 'UPPER_case!'}, 'username'),
            ({'username': 'admin'}, 'username'),
            ({'username': 'x' * 51}, 'username'),
        ):
            response = self.client.put(ME, payload, format='json')
            self.assertEqual(response.status_code, 400, payload)
            self.assertIn(field, response.data, payload)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'settingsuser')

    def test_username_must_be_unique_case_insensitively(self):
        for taken in ('someoneelse', 'SomeoneElse'):
            response = self.client.put(ME, {'username': taken}, format='json')
            self.assertEqual(response.status_code, 400, taken)
            self.assertIn('username', response.data)
            self.assertIn('already taken', str(response.data['username']))

    def test_keeping_your_own_username_is_not_a_conflict(self):
        self.assertEqual(self.client.put(ME, {'username': 'settingsuser'}, format='json').status_code, 200)

    def test_changing_username_does_not_touch_gallery_slugs(self):
        gallery = Gallery.objects.create(photographer=self.user, title='Keep My Slug', slug='keep-my-slug',
                                         is_published=True, is_active=True)
        self.client.put(ME, {'username': 'renameduser'}, format='json')
        gallery.refresh_from_db()
        self.assertEqual(gallery.slug, 'keep-my-slug')
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/v1/public/renameduser/keep-my-slug/').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/public/settingsuser/keep-my-slug/').status_code, 404)

    def test_mass_assignment_of_privileged_fields_is_ignored(self):
        before_email = self.user.email
        response = self.client.put(ME, {
            'display_name': 'Legit', 'email': 'hijack@evil.com', 'is_staff': True, 'is_superuser': True,
            'is_active_plan': True, 'is_active': False, 'id': str(self.other.id), 'created_at': '2001-01-01T00:00:00Z',
            'password': 'x', 'notify_downloads': True, 'portfolio_public': False,
            'collection_defaults': {'is_published': True},
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, 'Legit')
        self.assertEqual(self.user.email, before_email)
        self.assertFalse(self.user.is_staff or self.user.is_superuser or self.user.is_active_plan)
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.check_password(PASSWORD))
        self.assertFalse(self.user.notify_downloads)
        self.assertTrue(self.user.portfolio_public)
        self.assertEqual(self.user.collection_defaults, {})
        self.assertNotEqual(self.user.id, self.other.id)

    def test_foreign_id_in_the_body_cannot_redirect_the_edit(self):
        self.client.put(ME, {'id': str(self.other.id), 'display_name': 'Hacked'}, format='json')
        self.other.refresh_from_db()
        self.assertEqual(self.other.display_name, 'Someoneelse')

    def test_unauthenticated_access_is_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(ME).status_code, 401)
        self.assertEqual(self.client.put(ME, {'display_name': 'x'}, format='json').status_code, 401)

    def test_avatar_upload_is_validated_reencoded_and_publicly_stored(self):
        response = self.client.put(ME, {'avatar': png()}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertRegex(self.user.avatar.name, rf'^photographers/{self.user.id}/profile/avatar_[0-9a-f]{{12}}\.png$')
        self.assertTrue(response.data['avatar'].startswith('http'))
        from apps.core.storage import PublicMediaStorage
        self.assertIsInstance(User._meta.get_field('avatar').storage, PublicMediaStorage)

    def test_avatar_is_available_to_free_accounts(self):
        # not an entitlement-gated feature (branding logo is; the avatar is not)
        self.assertEqual(self.client.put(ME, {'avatar': png()}, format='multipart').status_code, 200)

    def test_bad_avatars_are_rejected(self):
        for label, upload in (
            ('html', SimpleUploadedFile('a.png', b'<html><script>1</script></html>', 'image/png')),
            ('svg', SimpleUploadedFile('a.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'image/svg+xml')),
            ('tiny', png(size=(4, 4))),
            ('huge file', SimpleUploadedFile('a.png', b'\x89PNG\r\n\x1a\n' + b'0' * (2 * 1024 * 1024 + 5), 'image/png')),
        ):
            response = self.client.put(ME, {'avatar': upload}, format='multipart')
            self.assertEqual(response.status_code, 400, label)
            self.assertIn('avatar', response.data, label)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_removing_the_avatar_clears_it_and_deletes_the_file(self):
        self.client.put(ME, {'avatar': png()}, format='multipart')
        self.user.refresh_from_db()
        name, storage = self.user.avatar.name, self.user.avatar.storage
        response = self.client.put(ME, {'avatar': None}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data['avatar'])
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)
        self.assertFalse(storage.exists(name))

    def test_email_is_read_only(self):
        self.client.put(ME, {'email': 'new@kyapture.com'}, format='json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'settingsuser@kyapture.com')


# ─────────────────────────────────────────────────────────────────────────────
class SecurityTests(SettingsBase):
    def login(self):
        client = self.client_class()
        response = client.post(LOGIN, {'email': self.user.email, 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return client, response.cookies['access_token'].value, response.cookies['refresh_token'].value

    def change(self, **overrides):
        payload = {'old_password': PASSWORD, 'new_password': 'Brand-New-Pass-5531!',
                   'new_password2': 'Brand-New-Pass-5531!', **overrides}
        return self.client.put(CHANGE_PW, payload, format='json')

    def test_change_password_succeeds_and_only_the_new_password_works(self):
        response = self.change()
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Brand-New-Pass-5531!'))
        fresh = self.client_class()
        self.assertEqual(fresh.post(LOGIN, {'email': self.user.email, 'password': PASSWORD}, format='json').status_code, 400)
        self.assertEqual(fresh.post(LOGIN, {'email': self.user.email, 'password': 'Brand-New-Pass-5531!'},
                                    format='json').status_code, 200)

    def test_wrong_current_password_is_rejected_and_nothing_changes(self):
        response = self.change(old_password='nope-wrong')
        self.assertEqual(response.status_code, 400)
        self.assertIn('old_password', response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_weak_passwords_are_rejected_by_the_policy(self):
        for weak in ('short1!', 'password', '12345678', 'settingsuser1', 'qwertyuiop'):
            response = self.change(new_password=weak, new_password2=weak)
            self.assertEqual(response.status_code, 400, weak)
            self.assertIn('new_password', response.data, weak)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_confirmation_mismatch_is_a_field_error_on_the_confirmation(self):
        response = self.change(new_password2='Different-Pass-9999!')
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password2', response.data)

    def test_new_password_must_differ_from_the_current_one(self):
        response = self.change(new_password=PASSWORD, new_password2=PASSWORD)
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password', response.data)

    def test_missing_fields_are_field_errors_not_server_errors(self):
        response = self.client.put(CHANGE_PW, {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertTrue({'old_password', 'new_password', 'new_password2'} <= set(response.data))

    def test_error_bodies_never_echo_passwords_or_internals(self):
        response = self.change(old_password='very-secret-guess')
        self.assertNotIn('very-secret-guess', str(response.data))
        self.assertNotIn('Traceback', str(response.data))

    def test_unauthenticated_cannot_change_password(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.put(CHANGE_PW, {}, format='json').status_code, 401)

    def test_current_password_guessing_is_throttled(self):
        statuses = [self.change(old_password=f'wrong-guess-{i}').status_code for i in range(12)]
        self.assertEqual(statuses[0], 400)
        self.assertIn(429, statuses)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_password_change_revokes_other_devices_but_keeps_this_one_signed_in(self):
        other_device, _, other_refresh = self.login()
        this_device, this_access, this_refresh = self.login()
        this_device.cookies['access_token'] = this_access
        response = this_device.put(CHANGE_PW, {
            'old_password': PASSWORD, 'new_password': 'Brand-New-Pass-5531!',
            'new_password2': 'Brand-New-Pass-5531!'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        # this device got a fresh session in the response...
        new_refresh = response.cookies['refresh_token'].value
        self.assertNotEqual(new_refresh, this_refresh)
        self.assertTrue(response.cookies['access_token'].value)
        probe = self.client_class()
        probe.cookies['refresh_token'] = new_refresh
        self.assertEqual(probe.post(REFRESH).status_code, 200)

        # ...while the refresh tokens that existed before the change are dead
        for stale in (other_refresh, this_refresh):
            probe = self.client_class()
            probe.cookies['refresh_token'] = stale
            self.assertEqual(probe.post(REFRESH).status_code, 401)

    def test_logout_all_revokes_every_session_and_clears_cookies(self):
        _, _, refresh_a = self.login()
        _, _, refresh_b = self.login()
        response = self.client.post(LOGOUT_ALL)
        self.assertEqual(response.status_code, 200)
        for cookie in ('access_token', 'refresh_token'):
            self.assertEqual(response.cookies[cookie].value, '')
        for token in (refresh_a, refresh_b):
            probe = self.client_class()
            probe.cookies['refresh_token'] = token
            self.assertEqual(probe.post(REFRESH).status_code, 401)
        outstanding = OutstandingToken.objects.filter(user=self.user)
        self.assertTrue(outstanding.exists())
        self.assertEqual(BlacklistedToken.objects.filter(token__in=outstanding).count(), outstanding.count())

    def test_logout_all_does_not_touch_other_accounts(self):
        other_client = self.client_class()
        response = other_client.post(LOGIN, {'email': self.other.email, 'password': PASSWORD}, format='json')
        other_refresh = response.cookies['refresh_token'].value
        self.client.post(LOGOUT_ALL)
        probe = self.client_class()
        probe.cookies['refresh_token'] = other_refresh
        self.assertEqual(probe.post(REFRESH).status_code, 200)

    def test_logout_all_requires_authentication_and_post(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post(LOGOUT_ALL).status_code, 401)
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get(LOGOUT_ALL).status_code, 405)

    def test_access_tokens_are_short_lived_which_bounds_what_revocation_cannot_reach(self):
        from django.conf import settings
        self.assertLessEqual(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'], timedelta(minutes=15))

    def test_the_password_policy_also_protects_registration(self):
        response = self.client_class().post('/api/v1/auth/register/', {
            'email': 'weak@kyapture.com', 'username': 'weakling', 'password': 'a', 'password2': 'a'}, format='json')
        self.assertEqual(response.status_code, 400)


# ─────────────────────────────────────────────────────────────────────────────
class NotificationPreferenceTests(SettingsBase):
    def test_defaults(self):
        data = self.client.get(SETTINGS).data['notifications']
        self.assertEqual(data, {'downloads': False, 'favorites': False, 'payments': True})

    def test_preferences_persist_and_a_fresh_read_returns_them(self):
        response = self.client.patch(SETTINGS, {'notifications': {'downloads': True, 'payments': False}}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.notify_downloads)
        self.assertFalse(self.user.notify_payments)
        self.assertFalse(self.user.notify_favorites)          # untouched
        fresh = self.client_class()
        fresh.force_authenticate(user=User.objects.get(pk=self.user.pk))
        self.assertEqual(fresh.get(SETTINGS).data['notifications'],
                         {'downloads': True, 'favorites': False, 'payments': False})

    def test_invalid_values_and_unknown_preferences_are_rejected(self):
        for payload in (
            {'notifications': {'downloads': 'sometimes'}},
            {'notifications': {'downloads': None}},
            {'notifications': {'sms_marketing': True}},
            {'notifications': 'all'},
            {'newsletter': True},
            {'user': str(self.other.id)},
            {'id': str(self.other.id)},
        ):
            response = self.client.patch(SETTINGS, payload, format='json')
            self.assertEqual(response.status_code, 400, payload)
        self.user.refresh_from_db()
        self.assertFalse(self.user.notify_downloads)

    def test_cannot_change_another_users_preferences(self):
        self.client.patch(SETTINGS, {'notifications': {'downloads': True}}, format='json')
        self.other.refresh_from_db()
        self.assertFalse(self.other.notify_downloads)

    def test_unauthenticated_is_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(SETTINGS).status_code, 401)
        self.assertEqual(self.client.patch(SETTINGS, {'notifications': {'downloads': True}}, format='json').status_code, 401)


class NotificationDeliveryTests(SettingsBase):
    """Every preference has a real send path; none is decorative."""

    def setUp(self):
        super().setUp()
        self.gallery = Gallery.objects.create(photographer=self.user, title='Wedding', slug='wedding',
                                              is_published=True, is_active=True)
        self.asset = MediaAsset.objects.create(
            gallery=self.gallery, media_type='image', original_name='a.jpg', file_size=1,
            processing_status='ready', original_file='photographers/x/a.jpg')
        # run the Celery task inline instead of enqueueing it on the real broker
        patcher = mock.patch('apps.users.tasks.send_notification_email.delay',
                             side_effect=lambda *args: deliver_notification(*args))
        self.delay = patcher.start()
        self.addCleanup(patcher.stop)

    def set_pref(self, **prefs):
        for name, value in prefs.items():
            setattr(self.user, f'notify_{name}', value)
        self.user.save(update_fields=[f'notify_{name}' for name in prefs])

    def download(self, email='client@example.com'):
        with self.captureOnCommitCallbacks(execute=True):
            DownloadLog.objects.create(gallery=self.gallery, email=email, download_type='photo')

    def test_download_alert_is_sent_when_enabled(self):
        self.set_pref(downloads=True)
        self.download()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])
        self.assertIn('Wedding', message.subject)
        self.assertIn('client@example.com', message.body)
        self.assertIn('/dashboard/settings/notifications', message.body)       # how to change it

    def test_no_download_alert_when_disabled(self):
        self.download()
        self.assertEqual(mail.outbox, [])
        self.delay.assert_not_called()

    def test_download_alerts_are_coalesced_per_gallery(self):
        self.set_pref(downloads=True)
        for _ in range(5):
            self.download()
        self.assertEqual(len(mail.outbox), 1)
        other_gallery = Gallery.objects.create(photographer=self.user, title='Other', slug='other',
                                               is_published=True, is_active=True)
        with self.captureOnCommitCallbacks(execute=True):
            DownloadLog.objects.create(gallery=other_gallery, download_type='gallery')
        self.assertEqual(len(mail.outbox), 2)

    def test_favorite_alert(self):
        self.set_pref(favorites=True)
        with self.captureOnCommitCallbacks(execute=True):
            Favorite.objects.create(gallery=self.gallery, media_asset=self.asset, client_key='k1', email='fan@example.com')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('fan@example.com', mail.outbox[0].body)
        mail.outbox.clear()
        self.set_pref(favorites=False)
        with self.captureOnCommitCallbacks(execute=True):
            Favorite.objects.create(gallery=self.gallery, media_asset=self.asset, client_key='k2')
        self.assertEqual(mail.outbox, [])

    def test_preference_switched_off_after_queueing_still_wins(self):
        self.set_pref(downloads=True)
        self.delay.side_effect = None                    # capture instead of delivering
        self.download()
        args = self.delay.call_args.args
        self.set_pref(downloads=False)
        self.assertFalse(deliver_notification(*args))
        self.assertEqual(mail.outbox, [])

    def test_inactive_accounts_get_nothing(self):
        self.set_pref(downloads=True)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.user.refresh_from_db()
        self.download()
        self.assertEqual(mail.outbox, [])

    def test_a_mail_failure_never_breaks_the_activity_that_triggered_it(self):
        self.set_pref(downloads=True)
        self.delay.side_effect = RuntimeError('SMTP down')
        with self.assertLogs('apps.users.notifications', level='ERROR'):
            with self.captureOnCommitCallbacks(execute=True):
                log = DownloadLog.objects.create(gallery=self.gallery, download_type='photo')
        self.assertTrue(DownloadLog.objects.filter(pk=log.pk).exists())
        self.assertEqual(mail.outbox, [])


class PaymentNotificationTests(SettingsBase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_user('reviewer', is_staff=True)
        self.plan = SubscriptionPlan.objects.get(key='pro')
        self.payment = ManualPayment(user=self.user, plan=self.plan, amount=self.plan.price)
        self.payment.payment_proof.save('proof.png', ContentFile(png().read()), save=False)
        self.payment.save()
        patcher = mock.patch('apps.users.tasks.send_notification_email.delay',
                             side_effect=lambda *args: deliver_notification(*args))
        patcher.start()
        self.addCleanup(patcher.stop)

    def review(self, action, **extra):
        self.client.force_authenticate(user=self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f'/api/v1/subscriptions/payments/{self.payment.id}/review/',
                                    {'action': action, **extra}, format='json')

    def test_approval_emails_the_photographer(self):
        response = self.review('approve')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn('approved', mail.outbox[0].subject)

    def test_rejection_emails_the_photographer_with_the_note(self):
        self.review('reject', admin_note='Receipt unreadable')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Receipt unreadable', mail.outbox[0].body)

    def test_payment_alerts_can_be_switched_off(self):
        self.user.notify_payments = False
        self.user.save(update_fields=['notify_payments'])
        self.review('approve')
        self.assertEqual(mail.outbox, [])

    def test_a_failed_review_sends_nothing_and_leaks_no_internals(self):
        with mock.patch('apps.subscriptions.models.ManualPayment.save', side_effect=RuntimeError('SECRET-SQL-DETAIL')):
            response = self.review('approve')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('SECRET-SQL-DETAIL', str(response.data))
        self.assertEqual(mail.outbox, [])


# ─────────────────────────────────────────────────────────────────────────────
class PlanAndBillingTests(SettingsBase):
    """Plan & Billing reuses the existing subscription APIs — nothing duplicated."""

    def test_free_account_reads_as_free_with_no_entitlements(self):
        data = self.client.get('/api/v1/subscriptions/my-subscription/').data
        self.assertEqual(data['status'], 'no_subscription')
        self.assertIsNone(data['plan'])
        self.assertEqual(data['entitlements']['branding'], False)

    def test_paid_account_shows_its_real_plan_and_status(self):
        grant_plan(self.user, name='Studio')
        data = self.client.get('/api/v1/subscriptions/my-subscription/').data
        self.assertEqual(data['plan']['name'], 'Studio')
        self.assertEqual(data['status'], 'active')
        self.assertTrue(data['entitlements']['watermark'])
        self.assertGreater(data['days_remaining'], 0)

    def test_lapsed_plan_does_not_read_as_entitled(self):
        grant_plan(self.user, days=-2)
        self.assertFalse(self.client.get('/api/v1/subscriptions/my-subscription/').data['entitlements']['branding'])

    def test_usage_endpoint_reports_the_real_plan_for_free_and_paid(self):
        free = self.client.get('/api/v1/galleries/dashboard/stats/').data
        self.assertEqual(free['subscription_status'], 'no_subscription')
        self.assertEqual(free['plan_name'], 'Free')
        grant_plan(self.user, name='Pro')
        paid = self.client.get('/api/v1/galleries/dashboard/stats/').data
        self.assertEqual(paid['plan_name'], 'Pro')

    def test_existing_billing_routes_still_work(self):
        self.assertEqual(self.client.get('/api/v1/subscriptions/plans/').status_code, 200)
        response = self.client.get('/api/v1/subscriptions/payments/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_a_user_sees_only_their_own_payment_history(self):
        plan = SubscriptionPlan.objects.get(key='basic')
        for owner in (self.user, self.other):
            payment = ManualPayment(user=owner, plan=plan, amount=plan.price)
            payment.payment_proof.save('p.png', ContentFile(png().read()), save=False)
            payment.save()
        emails = [row['email'] for row in self.client.get('/api/v1/subscriptions/payments/').data]
        self.assertEqual(emails, [self.user.email])

    def test_settings_api_cannot_change_plan_or_entitlements(self):
        self.client.patch(SETTINGS, {'plan': 'Studio', 'entitlements': {'branding': True}}, format='json')
        self.client.put(ME, {'is_active_plan': True, 'plan': 'Studio'}, format='json')
        self.assertFalse(self.client.get('/api/v1/subscriptions/my-subscription/').data['entitlements']['branding'])


# ─────────────────────────────────────────────────────────────────────────────
class CollectionDefaultsTests(SettingsBase):
    def set_defaults(self, defaults, user=None):
        self.client.force_authenticate(user=user or self.user)
        return self.client.patch(SETTINGS, {'collection_defaults': defaults}, format='json')

    def create_gallery(self, **payload):
        self.client.force_authenticate(user=self.user)
        payload.setdefault('title', 'Brand New')
        return self.client.post('/api/v1/galleries/', payload, format='json')

    def test_defaults_start_empty_and_persist(self):
        self.assertEqual(self.client.get(SETTINGS).data['collection_defaults'], {})
        defaults = {'is_published': True, 'is_downloadable': True, 'expires_in_days': 30,
                    'design': {'typography': 'timeless', 'colorPalette': 'gold', 'gridStyle': 'horizontal',
                               'thumbSize': 'large', 'layout': 'left', 'gridSpacing': 12}}
        self.assertEqual(self.set_defaults(defaults).status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.collection_defaults, defaults)
        self.assertEqual(self.client.get(SETTINGS).data['collection_defaults'], defaults)

    def test_invalid_defaults_are_rejected_and_nothing_is_saved(self):
        for bad in (
            {'is_published': 'yes'}, {'expires_in_days': 0}, {'expires_in_days': 99999}, {'expires_in_days': 1.5},
            {'expires_in_days': True}, {'favorites_enabled': True}, {'slideshow': 'auto'},
            {'design': {'typography': 'comic-sans'}}, {'design': {'gridSpacing': 999}}, {'design': {'coverPhoto': 'x'}},
            {'design': 'dark'}, 'everything', ['a'],
        ):
            response = self.set_defaults(bad)
            self.assertEqual(response.status_code, 400, bad)
        self.user.refresh_from_db()
        self.assertEqual(self.user.collection_defaults, {})

    def test_new_gallery_receives_the_defaults(self):
        self.user.branding_color = '#336699'
        self.user.save(update_fields=['branding_color'])
        self.set_defaults({'is_published': True, 'is_downloadable': True, 'expires_in_days': 30,
                           'design': {'typography': 'bold', 'colorPalette': 'sea'}})
        response = self.create_gallery()
        self.assertEqual(response.status_code, 201, response.data)
        gallery = Gallery.objects.get(slug=response.data['slug'])
        self.assertTrue(gallery.is_published)
        self.assertTrue(gallery.allow_download)
        self.assertEqual(gallery.branding_color, '#336699')
        self.assertEqual(gallery.design_settings, {'typography': 'bold', 'colorPalette': 'sea'})
        delta = gallery.expires_at - timezone.now()
        self.assertTrue(timedelta(days=29) < delta <= timedelta(days=30))

    def test_a_gallery_created_without_defaults_behaves_as_before(self):
        gallery = Gallery.objects.get(slug=self.create_gallery().data['slug'])
        self.assertFalse(gallery.is_published)
        self.assertFalse(gallery.allow_download)
        self.assertIsNone(gallery.expires_at)
        self.assertEqual(gallery.design_settings, {})

    def test_explicit_request_values_override_defaults(self):
        self.set_defaults({'is_published': True, 'is_downloadable': True, 'expires_in_days': 30})
        response = self.create_gallery(is_published=False, is_downloadable=False, branding_color='#112233',
                                       expires_at='2030-01-01')
        gallery = Gallery.objects.get(slug=response.data['slug'])
        self.assertFalse(gallery.is_published)
        self.assertFalse(gallery.allow_download)
        self.assertEqual(gallery.branding_color, '#112233')
        self.assertEqual(gallery.expires_at.year, 2030)

    def test_existing_galleries_are_never_overwritten(self):
        existing = Gallery.objects.create(photographer=self.user, title='Old', slug='old', is_published=False,
                                          allow_download=False, design_settings={'typography': 'sans'})
        self.set_defaults({'is_published': True, 'is_downloadable': True, 'expires_in_days': 7,
                           'design': {'typography': 'bold'}})
        existing.refresh_from_db()
        self.assertFalse(existing.is_published)
        self.assertFalse(existing.allow_download)
        self.assertIsNone(existing.expires_at)
        self.assertEqual(existing.design_settings, {'typography': 'sans'})
        # editing the old gallery does not consult the defaults either
        self.client.patch(f'/api/v1/galleries/{existing.slug}/', {'title': 'Old, renamed'}, format='json')
        existing.refresh_from_db()
        self.assertFalse(existing.is_published or existing.allow_download)

    def test_changing_defaults_later_does_not_touch_galleries_created_earlier(self):
        self.set_defaults({'is_downloadable': True})
        gallery = Gallery.objects.get(slug=self.create_gallery().data['slug'])
        self.set_defaults({'is_downloadable': False})
        gallery.refresh_from_db()
        self.assertTrue(gallery.allow_download)

    def test_defaults_are_per_user(self):
        self.set_defaults({'is_published': True})
        self.client.force_authenticate(user=self.other)
        gallery = Gallery.objects.get(slug=self.client.post('/api/v1/galleries/', {'title': 'Theirs'}, format='json').data['slug'])
        self.assertFalse(gallery.is_published)

    def test_watermark_default_is_pro_only_when_set(self):
        response = self.set_defaults({'watermark_enabled': True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'watermark_requires_upgrade')
        self.user.refresh_from_db()
        self.assertEqual(self.user.collection_defaults, {})
        grant_plan(self.user)
        self.assertEqual(self.set_defaults({'watermark_enabled': True}).status_code, 200)

    def test_watermark_default_applies_to_new_galleries_only_while_entitled(self):
        grant_plan(self.user)
        self.set_defaults({'watermark_enabled': True})
        self.assertTrue(Gallery.objects.get(slug=self.create_gallery().data['slug']).watermark_enabled)
        grant_plan(self.user, days=-1)                       # plan lapses
        response = self.create_gallery(title='After Lapse')
        self.assertEqual(response.status_code, 201, response.data)    # creation still succeeds
        self.assertFalse(Gallery.objects.get(slug=response.data['slug']).watermark_enabled)

    def test_leaving_an_already_saved_watermark_default_never_needs_the_plan(self):
        grant_plan(self.user)
        self.set_defaults({'watermark_enabled': True, 'is_published': True})
        grant_plan(self.user, days=-1)
        self.assertEqual(self.set_defaults({'watermark_enabled': True, 'is_published': False}).status_code, 200)
        self.assertEqual(self.set_defaults({'is_published': False}).status_code, 200)       # and turning it off

    def test_unauthenticated_cannot_read_or_write_defaults(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.patch(SETTINGS, {'collection_defaults': {}}, format='json').status_code, 401)

    def test_corrupt_stored_defaults_are_ignored_not_applied_or_crashing(self):
        User.objects.filter(pk=self.user.pk).update(
            collection_defaults={'is_published': 'banana', 'is_downloadable': True, 'junk': 1})
        self.user.refresh_from_db()                         # a request loads the user fresh
        gallery = Gallery.objects.get(slug=self.create_gallery().data['slug'])
        self.assertTrue(gallery.allow_download)             # the valid key still applies
        self.assertFalse(gallery.is_published)               # the invalid one never does
        self.assertEqual(self.client.get(SETTINGS).data['collection_defaults'], {'is_downloadable': True})


# ─────────────────────────────────────────────────────────────────────────────
class PrivacyTests(SettingsBase):
    def setUp(self):
        super().setUp()
        self.gallery = Gallery.objects.create(photographer=self.user, title='Public One', slug='public-one',
                                              is_published=True, is_active=True)
        self.portfolio = f'/api/v1/public/{self.user.username}/'

    def public_get(self, url):
        client = self.client_class()
        return client.get(url)

    def set_privacy(self, **values):
        return self.client.patch(SETTINGS, {'privacy': values}, format='json')

    def test_portfolio_is_public_by_default(self):
        self.assertTrue(self.client.get(SETTINGS).data['privacy']['portfolio_public'])
        self.assertEqual(self.public_get(self.portfolio).status_code, 200)

    def test_turning_it_off_persists_and_hides_the_portfolio(self):
        self.assertEqual(self.set_privacy(portfolio_public=False).status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.portfolio_public)
        self.assertFalse(self.client.get(SETTINGS).data['privacy']['portfolio_public'])
        self.assertEqual(self.public_get(self.portfolio).status_code, 404)

    def test_hidden_portfolio_is_indistinguishable_from_a_missing_one(self):
        self.set_privacy(portfolio_public=False)
        hidden = self.public_get(self.portfolio)
        missing = self.public_get('/api/v1/public/no-such-photographer/')
        self.assertEqual((hidden.status_code, hidden.data), (missing.status_code, missing.data))

    def test_individual_gallery_links_are_unaffected(self):
        self.set_privacy(portfolio_public=False)
        self.assertEqual(self.public_get(f'{self.portfolio}public-one/').status_code, 200)

    def test_turning_it_back_on_restores_the_portfolio(self):
        self.set_privacy(portfolio_public=False)
        self.set_privacy(portfolio_public=True)
        response = self.public_get(self.portfolio)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([g['slug'] for g in response.data['galleries']], ['public-one'])

    def test_other_photographers_are_not_affected(self):
        self.set_privacy(portfolio_public=False)
        self.assertEqual(self.public_get(f'/api/v1/public/{self.other.username}/').status_code, 200)
        self.other.refresh_from_db()
        self.assertTrue(self.other.portfolio_public)

    def test_invalid_privacy_input_is_rejected(self):
        for bad in ({'portfolio_public': 'maybe'}, {'portfolio_public': None}, {'analytics_opt_out': True},
                    {'is_staff': True}):
            self.assertEqual(self.set_privacy(**bad).status_code, 400, bad)
        self.user.refresh_from_db()
        self.assertTrue(self.user.portfolio_public)

    def test_unauthenticated_cannot_change_privacy(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.set_privacy(portfolio_public=False).status_code, 401)
        self.user.refresh_from_db()
        self.assertTrue(self.user.portfolio_public)
