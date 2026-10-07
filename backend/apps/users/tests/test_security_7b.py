# backend/apps/users/tests/test_security_7b.py
"""
CHUNK 7-B - throttles, identity, admin, errors and headers (the auth side).

Every test here was written before its fix and failed first (or is the proof
that a control already holds: marked "holds" in its docstring).

  - Row 78 (SEC-01): a client-sent X-Forwarded-For never picks the throttle
    bucket: login, gallery password and download PIN stay limited when every
    request carries a new XFF value; the stored client IP is the real peer.
  - Row 108: DRF throttles count in ONE shared cache (Redis), so several
    processes share a limit.
  - Throttles on register (own scope), login per account, token refresh
    (row 92: keyed on the user, not the anonymous 100/day IP bucket).
  - Row 90 (SEC-15): Django admin login is throttled and locks; hash/token
    fields never render in admin forms.
  - Row 88 (SEC-13): SECRET_KEY_FALLBACKS and a separate JWT signing key are
    read from the environment.
  - Errors never carry a stack trace, SQL or a server path (holds).
  - CORS, CSRF and auth cookie flags (holds).
"""
import json
import os
import subprocess
import sys
from unittest import mock

import bcrypt
from django.conf import settings
from django.core.cache import cache, caches
from django.core import signing
from django.db import DatabaseError
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.clients.models import ClientSession
from apps.galleries.models import Gallery
from apps.users.models import User

BACKEND_DIR = settings.BACKEND_DIR
FAST_PIN = '482193'
FAST_PASSWORD = 'gallery-pass-7b'


def spoof(i):
    """A different, client-chosen X-Forwarded-For on every request."""
    return {'HTTP_X_FORWARDED_FOR': f'203.0.113.{i % 250}, 198.51.100.{i % 250}'}


class ThrottleIdentityTests(APITestCase):
    """Row 78: a new X-Forwarded-For value per request never earns a fresh bucket."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(
            email='xff-owner@example.com', password='SecurePassword123!', username='xffowner')
        self.gallery = Gallery.objects.create(
            photographer=self.owner, title='XFF', slug='xff-gallery', is_published=True, is_active=True,
            allow_download=True, is_password_protected=True,
            password_hash=bcrypt.hashpw(FAST_PASSWORD.encode(), bcrypt.gensalt(4)).decode(),
            download_pin_hash=bcrypt.hashpw(FAST_PIN.encode(), bcrypt.gensalt(4)).decode(),
        )
        self.base = '/api/v1/public/xffowner/xff-gallery/'

    def test_login_throttle_ignores_a_changing_x_forwarded_for(self):
        codes = [
            self.client.post('/api/v1/auth/login/', {'email': f'nobody{i}@example.com', 'password': 'wrong-pass'},
                             format='json', **spoof(i)).status_code
            for i in range(7)
        ]
        self.assertEqual(codes[:5], [400] * 5)
        self.assertEqual(codes[5:], [429, 429])

    def test_gallery_password_throttle_ignores_a_changing_x_forwarded_for(self):
        codes = [
            self.client.post(f'{self.base}unlock/', {'password': f'guess-{i}'}, format='json', **spoof(i)).status_code
            for i in range(7)
        ]
        self.assertNotIn(200, codes)
        self.assertEqual(codes[5:], [429, 429])

    def test_download_pin_throttle_ignores_a_changing_x_forwarded_for(self):
        unlock = self.client.post(f'{self.base}unlock/', {'password': FAST_PASSWORD}, format='json')
        self.assertEqual(unlock.status_code, 200)
        token = unlock.data['access_token']
        codes = [
            self.client.post(f'{self.base}download-access/', {'pin': f'{1000 + i}', 'email': 'c@example.com'},
                             format='json', HTTP_AUTHORIZATION=f'Bearer {token}', **spoof(i)).status_code
            for i in range(6)
        ]
        # 1 unlock + 4 PIN guesses fill the 5/min bucket; the rest are refused.
        self.assertEqual(codes[:4], [401] * 4)
        self.assertEqual(codes[4:], [429, 429])

    def test_the_stored_client_ip_is_the_peer_not_the_header(self):
        self.client.post(f'{self.base}unlock/', {'password': FAST_PASSWORD}, format='json', **spoof(7))
        self.assertEqual(ClientSession.objects.get(gallery=self.gallery).ip_address, '127.0.0.1')

    def test_behind_one_proxy_only_the_proxy_added_address_counts(self):
        from rest_framework.settings import api_settings
        from rest_framework.throttling import BaseThrottle
        from rest_framework.test import APIRequestFactory
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'NUM_PROXIES': 1}):
            self.assertEqual(api_settings.NUM_PROXIES, 1)
            request = APIRequestFactory().get('/', HTTP_X_FORWARDED_FOR='1.2.3.4, 198.51.100.9', REMOTE_ADDR='10.0.0.2')
            self.assertEqual(BaseThrottle().get_ident(request), '198.51.100.9')
            request = APIRequestFactory().get('/', HTTP_X_FORWARDED_FOR='9.9.9.9, 198.51.100.9', REMOTE_ADDR='10.0.0.2')
            self.assertEqual(BaseThrottle().get_ident(request), '198.51.100.9')


class SharedThrottleCacheTests(APITestCase):
    """Row 108: the throttle counters live in Redis, shared by every process."""

    def test_the_default_cache_is_redis(self):
        self.assertEqual(settings.CACHES['default']['BACKEND'], 'django.core.cache.backends.redis.RedisCache')

    def test_a_count_written_by_another_process_is_seen_here(self):
        cache.delete('kyapture-7b-probe')
        child = subprocess.run(
            [sys.executable, 'manage.py', 'shell', '-c',
             "from django.core.cache import cache; cache.set('kyapture-7b-probe', 'from-child', 60)"],
            cwd=BACKEND_DIR, capture_output=True, text=True, timeout=120,
            env={**os.environ, 'CACHE_REDIS_URL': settings.CACHES['default'].get('LOCATION', '')},
        )
        self.assertEqual(child.returncode, 0, child.stderr[-2000:])
        self.assertEqual(cache.get('kyapture-7b-probe'), 'from-child')


class RegisterAndLoginThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()

    def register(self, i, **extra):
        return self.client.post('/api/v1/auth/register/', {
            'email': f'reg7b{i}@example.com', 'username': f'reg7b{i}',
            'password': 'Sup3r-Secret-Pass', 'password2': 'Sup3r-Secret-Pass',
        }, format='json', **extra)

    def test_registration_has_its_own_tight_scope(self):
        codes = [self.register(i, **spoof(i)).status_code for i in range(11)]
        self.assertEqual(codes[:10], [201] * 10)
        self.assertEqual(codes[10], 429)

    def test_one_account_is_limited_even_from_many_addresses(self):
        User.objects.create_user(email='victim7b@example.com', password='SecurePassword123!', username='victim7b')
        codes = [
            self.client.post('/api/v1/auth/login/', {'email': 'victim7b@example.com', 'password': f'guess-{i}'},
                             format='json', REMOTE_ADDR=f'192.0.2.{i + 1}').status_code
            for i in range(21)
        ]
        self.assertEqual(codes[:20], [400] * 20)
        self.assertEqual(codes[20], 429)


class TokenRefreshThrottleTests(APITestCase):
    """Row 92: refresh is limited per user, never by the anonymous 100/day IP bucket."""

    def setUp(self):
        cache.clear()

    def logged_in(self, n):
        user = User.objects.create_user(email=f'nat{n}@example.com', password='SecurePassword123!', username=f'nat{n}')
        client = APIClient()
        client.cookies['refresh_token'] = str(RefreshToken.for_user(user))
        return client

    def test_several_users_behind_one_nat_are_not_logged_out(self):
        clients = [self.logged_in(n) for n in range(3)]
        codes = [clients[i % 3].post('/api/v1/auth/token/refresh/').status_code for i in range(102)]
        self.assertEqual(set(codes), {200})

    def test_one_user_has_a_refresh_limit(self):
        client = self.logged_in(9)
        codes = [client.post('/api/v1/auth/token/refresh/').status_code for _ in range(61)]
        self.assertEqual(set(codes[:60]), {200})
        self.assertEqual(codes[60], 429)


class AdminLoginTests(APITestCase):
    """Row 90: the Django admin login is throttled and its forms hide secrets."""

    def setUp(self):
        cache.clear()
        self.staff = User.objects.create_superuser(
            email='admin7b@example.com', password='Admin-Pass-7b!', username='admin7b')

    def admin_login(self, password, **extra):
        return self.client.post('/admin/login/?next=/admin/', {'username': 'admin7b@example.com', 'password': password},
                                **extra)

    def test_failed_admin_logins_lock_the_form(self):
        codes = [self.admin_login(f'wrong-{i}', **spoof(i)).status_code for i in range(5)]
        self.assertEqual(codes, [200] * 5)            # the form again, with an error
        locked = self.admin_login('wrong-again')
        self.assertEqual(locked.status_code, 429)
        self.assertIn(b'Too many', locked.content)
        # Locked means locked: even the right password is not tried now.
        right = self.admin_login('Admin-Pass-7b!')
        self.assertEqual(right.status_code, 429)
        self.assertNotIn('sessionid', right.cookies)

    def test_the_lock_follows_the_account_across_addresses(self):
        codes = [self.admin_login(f'wrong-{i}', REMOTE_ADDR=f'192.0.2.{i + 1}').status_code for i in range(11)]
        self.assertIn(429, codes)

    def test_a_correct_login_still_works(self):
        response = self.admin_login('Admin-Pass-7b!')
        self.assertEqual(response.status_code, 302)

    def test_gallery_admin_form_never_renders_password_or_pin_hashes(self):
        gallery = Gallery.objects.create(
            photographer=self.staff, title='Hashes', slug='hashes', is_published=True, is_active=True,
            password_hash='$2b$04$abcdefghijklmnopqrstuuX6oV2b6Yp7f0VJmQm1Yw0c2xYqvJ6d2',
            download_pin_hash='$2b$04$zyxwvutsrqponmlkjihgfeAbCdEfGhIjKlMnOpQrStUvWxYz012',
        )
        self.client.force_login(self.staff)
        page = self.client.get(f'/admin/galleries/gallery/{gallery.pk}/change/')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'password_hash', page.content)
        self.assertNotIn(b'download_pin_hash', page.content)
        self.assertNotIn(gallery.password_hash.encode(), page.content)

    def test_client_session_admin_never_renders_the_token(self):
        gallery = Gallery.objects.create(photographer=self.staff, title='S', slug='s', is_published=True)
        session = ClientSession.objects.create(gallery=gallery)
        self.client.force_login(self.staff)
        page = self.client.get(f'/admin/clients/clientsession/{session.pk}/change/')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'access_token', page.content)
        self.assertNotIn(session.access_token.encode(), page.content)


def settings_in_subprocess(module, env, expression):
    """Evaluate `expression` against a freshly imported settings module with `env` (no Django setup)."""
    code = (
        'import importlib, json, os, sys; sys.path.insert(0, os.getcwd()); '
        f'm = importlib.import_module({module!r}); print(json.dumps({expression}))'
    )
    clean = {k: v for k, v in os.environ.items() if not k.startswith(('SECRET_KEY', 'JWT_', 'CACHE_', 'NUM_PROXIES'))}
    result = subprocess.run([sys.executable, '-c', code], cwd=BACKEND_DIR, capture_output=True, text=True,
                            env={**clean, **env}, timeout=60)
    if result.returncode != 0:
        raise AssertionError(result.stderr[-3000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


PROD_ENV = {
    'SECRET_KEY': 'k' * 60, 'DB_NAME': 'x', 'DB_USER': 'x', 'DB_PASSWORD': 'x', 'DB_HOST': 'x',
    'AWS_ACCESS_KEY_ID': 'x', 'AWS_SECRET_ACCESS_KEY': 'x', 'AWS_STORAGE_BUCKET_NAME': 'x',
    'DEFAULT_FROM_EMAIL': 'Kyapture <no-reply@kyapture.com>', 'CACHE_REDIS_URL': 'redis://cache:6379/2',
}


class KeyRotationSettingsTests(APITestCase):
    """Row 88: a rotated SECRET_KEY keeps old signed links alive; JWTs can have their own key."""

    def test_fallback_keys_and_jwt_key_come_from_the_environment(self):
        got = settings_in_subprocess('config.settings.production', {
            **PROD_ENV, 'SECRET_KEY_FALLBACKS': 'old-key-1, old-key-2', 'JWT_SIGNING_KEY': 'j' * 60,
        }, "[m.SECRET_KEY_FALLBACKS, m.SIMPLE_JWT.get('SIGNING_KEY')]")
        self.assertEqual(got, [['old-key-1', 'old-key-2'], 'j' * 60])

    def test_a_link_signed_with_the_old_key_still_verifies_after_rotation(self):
        with override_settings(SECRET_KEY='old-secret-key-' + 'x' * 40):
            token = signing.dumps({'g': 'gallery'}, salt='kyapture.clients.download-access')
        with override_settings(SECRET_KEY='new-secret-key-' + 'y' * 40,
                               SECRET_KEY_FALLBACKS=['old-secret-key-' + 'x' * 40]):
            self.assertEqual(signing.loads(token, salt='kyapture.clients.download-access'), {'g': 'gallery'})


class ProductionHeaderSettingsTests(APITestCase):
    """Holds (read from the real production module): HTTPS, cookie, frame and proxy settings."""

    def test_production_security_settings(self):
        got = settings_in_subprocess('config.settings.production', {
            **PROD_ENV, 'CORS_ALLOWED_ORIGINS': 'https://app.kyapture.com, https://kyapture.com',
            'CSRF_TRUSTED_ORIGINS': 'https://app.kyapture.com, https://kyapture.com',
        }, "[m.DEBUG, m.SECURE_HSTS_SECONDS, m.SESSION_COOKIE_SECURE, m.CSRF_COOKIE_SECURE, m.X_FRAME_OPTIONS, "
           "m.SECURE_CONTENT_TYPE_NOSNIFF, m.REST_FRAMEWORK.get('NUM_PROXIES'), m.CORS_ALLOWED_ORIGINS, "
           "m.CSRF_TRUSTED_ORIGINS, m.CACHES['default']['BACKEND']]")
        self.assertEqual(got, [
            False, 31536000, True, True, 'DENY', True, 1,
            ['https://app.kyapture.com', 'https://kyapture.com'],
            ['https://app.kyapture.com', 'https://kyapture.com'],
            'django.core.cache.backends.redis.RedisCache',
        ])

    def test_production_refuses_to_boot_without_a_shared_cache(self):
        env = {k: v for k, v in PROD_ENV.items() if k != 'CACHE_REDIS_URL'}
        with self.assertRaises(AssertionError) as caught:
            settings_in_subprocess('config.settings.production', env, 'm.CACHES')
        self.assertIn('CACHE_REDIS_URL', str(caught.exception))


class ErrorLeakTests(APITestCase):
    """Holds: an unexpected error is a generic JSON 500 - no trace, no SQL, no path."""

    def test_a_database_error_is_generic(self):
        client = APIClient(raise_request_exception=False)
        boom = DatabaseError('relation "secret_table" does not exist LINE 1: SELECT pin FROM /app/apps/x.py')
        with mock.patch('apps.clients.views.PublicGalleryView.get', side_effect=boom), \
                self.assertLogs('apps.core.middleware', level='ERROR'):
            response = client.get('/api/v1/public/anyone/any-gallery/')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()['code'], 'internal_server_error')
        for leak in (b'secret_table', b'SELECT', b'/app/', b'Traceback', b'.py'):
            self.assertNotIn(leak, response.content)

    def test_a_validation_error_names_fields_not_internals(self):
        response = self.client.post('/api/v1/auth/login/', {'email': 'x'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(b'Traceback', response.content)
        self.assertNotIn(b'/app/', response.content)


class CorsCsrfCookieTests(APITestCase):
    """Holds: CORS allow-list, CSRF on cookie-authenticated writes, HttpOnly + SameSite cookies."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email='cors7b@example.com', password='SecurePassword123!',
                                             username='cors7b')

    def test_an_unknown_origin_gets_no_cors_grant(self):
        response = self.client.get('/api/total-users', HTTP_ORIGIN='https://evil.example')
        self.assertNotIn('Access-Control-Allow-Origin', response)

    def test_the_app_origin_gets_a_credentialed_grant(self):
        response = self.client.get('/api/total-users', HTTP_ORIGIN='http://localhost:3000')
        self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:3000')
        self.assertEqual(response['Access-Control-Allow-Credentials'], 'true')

    def test_auth_cookies_are_httponly_and_samesite(self):
        response = self.client.post('/api/v1/auth/login/', {'email': 'cors7b@example.com',
                                                            'password': 'SecurePassword123!'}, format='json')
        self.assertEqual(response.status_code, 200)
        for name in ('access_token', 'refresh_token'):
            self.assertTrue(response.cookies[name]['httponly'])
            self.assertEqual(response.cookies[name]['samesite'], 'Lax')

    def test_a_cookie_authenticated_write_without_csrf_is_refused(self):
        client = APIClient(enforce_csrf_checks=True)
        login = client.post('/api/v1/auth/login/', {'email': 'cors7b@example.com',
                                                    'password': 'SecurePassword123!'}, format='json')
        self.assertEqual(login.status_code, 200)
        response = client.post('/api/v1/galleries/', {'title': 'CSRF'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertIn('CSRF', json.dumps(response.json()))
