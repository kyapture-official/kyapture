# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/tests/test_views.py
"""
Focused regression tests for PasswordResetRequestView / PasswordResetConfirmView
(Phase 0 — Task 11: "make the complete password-reset request flow functional").

These specifically guard the two properties Phase 0 requires:
  1. The request endpoint never reveals whether an email is registered —
     same status code, same body, whether the account exists, is inactive,
     or the outbound email itself fails to send.
  2. The confirm endpoint actually works end-to-end (real token, real
     template render, real password change) and fails safely (no 500s,
     no internal exception leakage) on bad input.
"""
from unittest.mock import patch

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from rest_framework.test import APITestCase
from rest_framework import status

from apps.users.models import User

RESET_URL = '/api/v1/auth/password/reset/'
CONFIRM_URL = '/api/v1/auth/password/reset/confirm/'


class PasswordResetRequestTests(APITestCase):
    """POST /api/v1/auth/password/reset/"""

    def setUp(self):
        # AnonRateThrottle (scope='password_reset', 5/hour) keys off the
        # test client's fixed IP, so a cold cache per test keeps these
        # independent instead of tripping the rate limit across tests.
        cache.clear()
        self.existing_user = User.objects.create_user(
            username='photog',
            email='photog@example.com',
            password='OldPassword123!',
            display_name='Photog',
        )

    def test_existing_active_account_returns_generic_message_and_sends_mail(self):
        response = self.client.post(RESET_URL, {'email': 'photog@example.com'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('photog@example.com', mail.outbox[0].to)
        self.assertIn('/auth/password/reset/confirm/', mail.outbox[0].body)

    def test_nonexistent_account_returns_identical_response_and_sends_no_mail(self):
        existing_response = self.client.post(RESET_URL, {'email': 'photog@example.com'})
        cache.clear()  # isolate the second call from the first request's throttle hit
        missing_response = self.client.post(RESET_URL, {'email': 'nobody-here@example.com'})

        # Anti-enumeration contract: identical status + identical body.
        self.assertEqual(existing_response.status_code, missing_response.status_code)
        self.assertEqual(existing_response.data, missing_response.data)
        # Only the real account should have triggered an actual email send.
        self.assertEqual(len(mail.outbox), 1)

    def test_inactive_account_returns_identical_generic_response(self):
        User.objects.create_user(
            username='inactivephotog',
            email='inactive@example.com',
            password='OldPassword123!',
            is_active=False,
        )

        active_response = self.client.post(RESET_URL, {'email': 'photog@example.com'})
        cache.clear()
        inactive_response = self.client.post(RESET_URL, {'email': 'inactive@example.com'})

        self.assertEqual(active_response.status_code, inactive_response.status_code)
        self.assertEqual(active_response.data, inactive_response.data)
        # Only the active account's email should have actually been sent.
        self.assertEqual(len(mail.outbox), 1)

    def test_missing_email_returns_400(self):
        response = self.client.post(RESET_URL, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.users.views.send_mail', side_effect=RuntimeError('SES is down'))
    def test_send_failure_for_real_account_still_returns_generic_200(self, mock_send_mail):
        """
        Regression guard for the exact bug this phase fixed: previously only
        User.DoesNotExist was caught, so a send-path failure for a REAL
        account propagated as an uncaught 500 — while a fake email still
        quietly returned 200. That asymmetry is itself an enumeration
        oracle. Now every failure past "does this user exist" is caught,
        logged, and swallowed behind the same generic response.
        """
        response = self.client.post(RESET_URL, {'email': 'photog@example.com'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        mock_send_mail.assert_called_once()


class PasswordResetConfirmTests(APITestCase):
    """POST /api/v1/auth/password/reset/confirm/"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='photog2',
            email='photog2@example.com',
            password='OldPassword123!',
        )
        self.uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.token = default_token_generator.make_token(self.user)

    def test_valid_token_actually_changes_the_password(self):
        response = self.client.post(CONFIRM_URL, {
            'uidb64': self.uidb64,
            'token': self.token,
            'new_password': 'BrandNewPassword456!',
            'new_password2': 'BrandNewPassword456!',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPassword456!'))
        self.assertFalse(self.user.check_password('OldPassword123!'))

    def test_token_is_single_use(self):
        payload = {
            'uidb64': self.uidb64,
            'token': self.token,
            'new_password': 'BrandNewPassword456!',
            'new_password2': 'BrandNewPassword456!',
        }
        first = self.client.post(CONFIRM_URL, payload)
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        # Django's default token generator embeds the password hash, so
        # replaying the same token after a successful change must fail —
        # otherwise a leaked reset link would remain valid forever.
        second = self.client.post(CONFIRM_URL, payload)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mismatched_passwords_returns_400_and_does_not_change_password(self):
        response = self.client.post(CONFIRM_URL, {
            'uidb64': self.uidb64,
            'token': self.token,
            'new_password': 'BrandNewPassword456!',
            'new_password2': 'SomethingElse789!',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPassword123!'))

    def test_invalid_token_returns_400_not_500(self):
        response = self.client.post(CONFIRM_URL, {
            'uidb64': self.uidb64,
            'token': 'not-a-real-token',
            'new_password': 'BrandNewPassword456!',
            'new_password2': 'BrandNewPassword456!',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # No leaked traceback/internal exception detail in the response body.
        self.assertNotIn('Traceback', str(response.data))

    def test_malformed_uid_returns_400_not_500(self):
        response = self.client.post(CONFIRM_URL, {
            'uidb64': 'not-valid-base64!!!',
            'token': self.token,
            'new_password': 'BrandNewPassword456!',
            'new_password2': 'BrandNewPassword456!',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_fields_returns_400(self):
        response = self.client.post(CONFIRM_URL, {'uidb64': self.uidb64})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
