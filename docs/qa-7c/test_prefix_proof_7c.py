"""
7-C pre-fix proof. Run against the code at HEAD (before 7-C). Every test here
PASSES when the weakness exists, i.e. it documents the old behaviour.
"""
import time
import statistics

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient, APITestCase

from apps.users.models import User

PW = 'OldPassword123!'
NEW = 'Fresh-Lantern-842'


class PreFixProof(APITestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.user = User.objects.create_user(username='p7c', email='p7c@example.com', password=PW)

    def device(self):
        c = APIClient()
        r = c.post('/api/v1/auth/login/', {'email': 'p7c@example.com', 'password': PW}, format='json')
        assert r.status_code == 200
        return c, r.cookies['access_token'].value

    def test_P1_access_token_survives_a_password_reset(self):
        c, access = self.device()
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        tok = default_token_generator.make_token(self.user)
        r = APIClient().post('/api/v1/auth/password/reset/confirm/', {
            'uidb64': uid, 'token': tok, 'new_password': NEW, 'new_password2': NEW}, format='json')
        self.assertEqual(r.status_code, 200)
        b = APIClient(); b.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        self.assertEqual(b.get('/api/v1/auth/me/').status_code, 200)      # still alive
        self.assertEqual(c.get('/api/v1/auth/me/').status_code, 200)      # cookie too

    def test_P2_access_token_survives_a_password_change_on_another_device(self):
        other, _ = self.device()
        me, _ = self.device()
        r = me.put('/api/v1/auth/change-password/', {
            'old_password': PW, 'new_password': NEW, 'new_password2': NEW}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(other.get('/api/v1/auth/me/').status_code, 200)

    def test_P3_an_older_link_still_works_after_a_newer_request(self):
        old = default_token_generator.make_token(self.user)
        self.client.post('/api/v1/auth/password/reset/', {'email': 'p7c@example.com'}, format='json')
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        r = APIClient().post('/api/v1/auth/password/reset/confirm/', {
            'uidb64': uid, 'token': old, 'new_password': NEW, 'new_password2': NEW}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_P4_link_lifetime_is_three_days(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 259200)

    def test_P5_confirm_tells_unknown_uid_from_bad_token(self):
        bad_uid = urlsafe_base64_encode(force_bytes('00000000-0000-0000-0000-000000000000'))
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        a = APIClient().post('/api/v1/auth/password/reset/confirm/', {
            'uidb64': bad_uid, 'token': 'x', 'new_password': NEW, 'new_password2': NEW}, format='json')
        b = APIClient().post('/api/v1/auth/password/reset/confirm/', {
            'uidb64': uid, 'token': 'x', 'new_password': NEW, 'new_password2': NEW}, format='json')
        self.assertNotEqual(a.data, b.data)

    def test_P6_no_per_email_limit_one_victim_gets_unlimited_mail_from_many_addresses(self):
        for i in range(12):
            r = self.client.post('/api/v1/auth/password/reset/', {'email': 'p7c@example.com'}, format='json',
                                 REMOTE_ADDR=f'192.0.2.{i + 1}')
            self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 12)

    def test_P7_known_address_does_db_and_mail_work_in_the_request(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as known:
            self.client.post('/api/v1/auth/password/reset/', {'email': 'p7c@example.com'}, format='json')
        cache.clear()
        with CaptureQueriesContext(connection) as unknown:
            self.client.post('/api/v1/auth/password/reset/', {'email': 'ghost@example.com'}, format='json')
        print(f'\nP7 queries known={len(known)} unknown={len(unknown)}; mails={len(mail.outbox)}')
        self.assertEqual(len(mail.outbox), 1)   # the send happened synchronously, inside the known request

    @override_settings(ALLOWED_HOSTS=['*'], USE_X_FORWARDED_HOST=True)
    def test_P8_forged_host_header_does_not_change_the_link(self):
        """Holds already (link from FRONTEND_URL)."""
        self.client.post('/api/v1/auth/password/reset/', {'email': 'p7c@example.com'}, format='json',
                         HTTP_HOST='evil.example', HTTP_X_FORWARDED_HOST='evil.example')
        self.assertNotIn('evil.example', mail.outbox[0].body)
