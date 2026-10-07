# backend/apps/users/tests/test_auth_hardening.py
"""
Phase 4 regression tests — AUTH HARDENING.

Covers:
  - F-36: refresh token rotation actually mints a NEW refresh token and
    blacklists the old one (previously just re-serialized the same token)
  - password change (self-service) and password reset (via email token)
    both invalidate every other outstanding refresh token
"""
from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework import status

from apps.users.models import User
from apps.users.password_reset import issue_token

LOGIN_URL = '/api/v1/auth/login/'
REFRESH_URL = '/api/v1/auth/token/refresh/'
CHANGE_PW_URL = '/api/v1/auth/change-password/'
RESET_CONFIRM_URL = '/api/v1/auth/password/reset/confirm/'


class RefreshTokenRotationTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='rotationuser',
            email='rotation@kyapture.com',
            password='SecurePassword123!',
        )

    def _login(self):
        response = self.client.post(
            LOGIN_URL, {'email': 'rotation@kyapture.com', 'password': 'SecurePassword123!'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.cookies['access_token'].value, response.cookies['refresh_token'].value

    def test_refresh_mints_a_genuinely_new_refresh_token(self):
        _, refresh_token = self._login()
        self.client.cookies['refresh_token'] = refresh_token

        response = self.client.post(REFRESH_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        new_refresh_token = response.cookies['refresh_token'].value
        new_access_token = response.cookies['access_token'].value

        # Not just a re-serialization of the same token — a different
        # jti/signature entirely.
        self.assertNotEqual(new_refresh_token, refresh_token)
        self.assertTrue(new_access_token)

    def test_old_refresh_token_is_blacklisted_after_rotation(self):
        _, old_refresh_token = self._login()
        self.client.cookies['refresh_token'] = old_refresh_token

        first_refresh = self.client.post(REFRESH_URL)
        self.assertEqual(first_refresh.status_code, status.HTTP_200_OK)

        # Reuse the OLD (pre-rotation) refresh token — must now be rejected.
        self.client.cookies['refresh_token'] = old_refresh_token
        second_attempt = self.client.post(REFRESH_URL)
        self.assertEqual(second_attempt.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_new_refresh_token_still_works(self):
        _, old_refresh_token = self._login()
        self.client.cookies['refresh_token'] = old_refresh_token
        first_refresh = self.client.post(REFRESH_URL)
        new_refresh_token = first_refresh.cookies['refresh_token'].value

        self.client.cookies['refresh_token'] = new_refresh_token
        second_refresh = self.client.post(REFRESH_URL)
        self.assertEqual(second_refresh.status_code, status.HTTP_200_OK, second_refresh.data)


class PasswordChangeInvalidatesSessionsTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='pwchangeuser',
            email='pwchange@kyapture.com',
            password='OldPassword123!',
        )

    def _login(self):
        response = self.client.post(
            LOGIN_URL, {'email': 'pwchange@kyapture.com', 'password': 'OldPassword123!'}, format='json'
        )
        return response.cookies['access_token'].value, response.cookies['refresh_token'].value

    def test_changing_password_blacklists_outstanding_refresh_token(self):
        access_token, refresh_token = self._login()
        self.client.cookies['access_token'] = access_token

        response = self.client.put(CHANGE_PW_URL, {
            'old_password': 'OldPassword123!',
            'new_password': 'BrandNewPassword456!',
            'new_password2': 'BrandNewPassword456!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # The refresh token issued before the password change must no
        # longer work afterward.
        self.client.cookies = self.client.cookies.__class__()
        self.client.cookies['refresh_token'] = refresh_token
        refresh_response = self.client.post(REFRESH_URL)
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordResetInvalidatesSessionsTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='pwresetuser',
            email='pwreset@kyapture.com',
            password='OldPassword123!',
        )

    def _login(self):
        response = self.client.post(
            LOGIN_URL, {'email': 'pwreset@kyapture.com', 'password': 'OldPassword123!'}, format='json'
        )
        return response.cookies['refresh_token'].value

    def test_resetting_password_blacklists_outstanding_refresh_token(self):
        refresh_token = self._login()

        # 7-C: the link carries one random token (apps/users/password_reset.py).
        token = issue_token(self.user)

        response = self.client.post(RESET_CONFIRM_URL, {
            'token': token,
            'new_password': 'ResetPassword789!',
            'new_password2': 'ResetPassword789!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.client.cookies['refresh_token'] = refresh_token
        refresh_response = self.client.post(REFRESH_URL)
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)
