# backend/apps/clients/tests/test_atomic_counters_7f.py
"""
7F (reviewer 7R, F6): attempt counters must hold under parallel requests.

  - 20 parallel wrong email codes give at most 5 real comparisons (the tries
    count used to be read, changed and written back);
  - 20 parallel wrong PINs from one client give at most 5 bcrypt checks (the
    lockout used to check before bcrypt and count only after it);
  - wrong email codes count in the per-client lockout;
  - a daily cap per gallery + address bounds the guesses across fresh codes.

Threads need committed rows, so the parallel tests are a TransactionTestCase.
No serialized_rollback: a TransactionTestCase flushes every table after each
test, so setUp re-creates the plan rows it needs (ensure_seed_plans) and the
result does not depend on which test class ran before it.
"""
import re
import threading
from unittest import mock

import bcrypt
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase
from django.utils import crypto
from rest_framework.test import APIClient

from apps.subscriptions.testing import ensure_seed_plans

from apps.clients import download_access, views as client_views
from apps.galleries.models import Gallery

User = get_user_model()
PIN = '4821'
VIP = 'vip@example.com'


def fast_hash(value):
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt(4)).decode()


class CounterBase(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.assertEqual(ensure_seed_plans(), 4)
        patcher = mock.patch.object(client_views.PasswordUnlockRateThrottle, 'allow_request', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.owner = User.objects.create_user(email='count7f@kyapture.com', password='SecurePassword123!',
                                              username='count7f')
        self.gallery = Gallery.objects.create(
            photographer=self.owner, title='Counters', slug='count-7f', is_published=True, is_active=True,
            allow_download=True, download_pin_hash=fast_hash(PIN),
            design_settings={'downloads': {'restrict_contacts': True, 'allowed_emails': [VIP]}},
        )
        self.url = '/api/v1/public/count7f/count-7f/download-access/'

    def ask(self, code=None, pin=PIN, ip='192.0.2.50'):
        body = {'email': VIP, 'pin': pin}
        if code is not None:
            body['email_code'] = code
        return APIClient(REMOTE_ADDR=ip).post(self.url, body, format='json')

    def sent_code(self):
        return re.search(r'\b(\d{6})\b', mail.outbox[-1].body).group(1)

    def wrong(self, code):
        return '000000' if code != '000000' else '111111'

    def parallel(self, n, fn):
        barrier = threading.Barrier(n)
        results, lock = [], threading.Lock()

        def worker(i):
            try:
                barrier.wait()
                value = fn(i)
                with lock:
                    results.append(value)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        return results


class ParallelEmailCodeTests(CounterBase):
    def test_20_parallel_wrong_codes_make_at_most_5_real_comparisons(self):
        self.assertEqual(self.ask().status_code, 202)
        wrong = self.wrong(self.sent_code())
        real = crypto.constant_time_compare
        compared = []

        def counting(a, b):
            compared.append(1)
            return real(a, b)

        gallery = Gallery.objects.get(pk=self.gallery.pk)
        with mock.patch('django.utils.crypto.constant_time_compare', side_effect=counting):
            self.parallel(20, lambda i: download_access.check_email_code(gallery, VIP, wrong))
        self.assertLessEqual(len(compared), 5, len(compared))

    def test_20_parallel_wrong_codes_through_the_api_make_at_most_5_real_comparisons(self):
        self.assertEqual(self.ask().status_code, 202)
        wrong = self.wrong(self.sent_code())
        real = crypto.constant_time_compare
        compared = []

        def counting(a, b):
            compared.append(1)
            return real(a, b)

        with mock.patch('django.utils.crypto.constant_time_compare', side_effect=counting):
            codes = self.parallel(20, lambda i: self.ask(code=wrong, ip=f'198.51.100.{i + 1}').status_code)
        print(f'\n  7F parallel wrong codes via the API, {len(codes)} threads: {len(compared)} comparisons')
        self.assertEqual(len(codes), 20)
        self.assertLessEqual(len(compared), 5, (len(compared), codes))


class ParallelPinTests(CounterBase):
    def test_20_parallel_wrong_pins_from_one_client_make_at_most_5_bcrypt_checks(self):
        real = client_views.verify_pin
        checked = []

        def counting(gallery, pin):
            checked.append(1)
            return real(gallery, pin)

        with mock.patch.object(client_views, 'verify_pin', side_effect=counting):
            codes = self.parallel(20, lambda i: self.ask(pin=f'{100000 + i}').status_code)
        print(f'\n  7F parallel wrong PINs, {len(codes)} threads: {len(checked)} bcrypt checks, {sorted(codes)}')
        self.assertEqual(len(codes), 20)
        self.assertLessEqual(len(checked), 5, (len(checked), codes))
        self.assertEqual(codes.count(401), len(checked))
        self.assertEqual(codes.count(429), 20 - len(checked))


class EmailCodeLockoutTests(CounterBase):
    def test_wrong_codes_count_in_the_client_lockout(self):
        self.assertEqual(self.ask().status_code, 202)
        code = self.sent_code()
        for _ in range(5):
            self.assertEqual(self.ask(code=self.wrong(code)).status_code, 401)
        # A fresh code for the same address: this client is locked out of the code step.
        download_access.send_email_code(Gallery.objects.get(pk=self.gallery.pk), VIP)
        locked = self.ask(code=self.sent_code())
        self.assertEqual((locked.status_code, locked.data['code']), (429, 'too_many_attempts'))
        # Another client with the right fresh code still gets in.
        self.assertEqual(self.ask(code=self.sent_code(), ip='192.0.2.99').status_code, 200)

    def test_a_daily_cap_per_address_bounds_guesses_across_fresh_codes(self):
        cap = download_access.EMAIL_CODE_DAILY_MAX_FAILURES
        gallery = Gallery.objects.get(pk=self.gallery.pk)
        failures, n = 0, 0
        while failures < cap:                                  # fresh codes, fresh client addresses
            key = download_access._email_code_key(gallery, VIP)
            cache.delete(f'{key}:sends')                       # as if 10 minutes had passed
            self.assertEqual(download_access.send_email_code(gallery, VIP), 'sent')
            wrong = self.wrong(self.sent_code())
            for _ in range(2):
                n += 1
                self.assertEqual(self.ask(code=wrong, ip=f'203.0.113.{n}').status_code, 401)
                failures += 1
        cache.delete(f'{key}:sends')
        self.assertEqual(download_access.send_email_code(gallery, VIP), 'too_many')
        refused = self.ask(code='123456', ip='203.0.113.250')
        self.assertEqual((refused.status_code, refused.data['code']), (429, 'too_many_codes'))
        self.assertIn('today', refused.data['error'])
