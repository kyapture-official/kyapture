# backend/apps/clients/tests/test_lockout_shared_ip_7g.py
"""
7G (reviewer 7R-2, R2): guests behind ONE address (a venue's NAT) who type the
RIGHT value at the same moment must never lock that address out.

7F counted every try (right or wrong) before the check and set the 15-minute
client lock as soon as a 6th try was in flight, and record_failure compared
that inflated count with 5. Now:

  - in-flight tries and real failures are two counts;
  - a try that would exceed the limit (failures + tries in flight) waits for
    the tries in flight to finish instead of being checked, and is refused
    (without any lock) only if they leave the address at the limit;
  - only record_failure sets the lock, from the failure count alone;
  - a success removes only its own in-flight try (and clears the failures).

So 20 parallel WRONG tries still reach the comparison at most 5 times.

Every thread here uses the SAME client address on purpose. Real threads and a
shared Redis cache, so this is a TransactionTestCase (no serialized_rollback:
setUp re-creates the plan rows with ensure_seed_plans).
"""
import re
import threading
from unittest import mock

import bcrypt
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, TransactionTestCase
from rest_framework.test import APIClient

from apps.subscriptions.testing import ensure_seed_plans

from apps.clients import lockout, views as client_views
from apps.galleries.models import Gallery

User = get_user_model()
PIN = '4821'
VENUE_IP = '203.0.113.9'                    # one address for every guest in these tests
GUESTS = [f'guest{i}@example.com' for i in range(8)]


def production_hash(value):
    # The cost set-download-pin uses (bcrypt default): the real width of the window
    # in which parallel tries overlap. A cheap test hash hides the overlap.
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()


class SharedAddressBase(TransactionTestCase):
    restrict_contacts = False

    def setUp(self):
        cache.clear()
        self.assertEqual(ensure_seed_plans(), 4)
        # The 5/min DRF throttle is a separate, short limit (and racy, debt row 154);
        # what is under test is the 15-minute lockout.
        patcher = mock.patch.object(client_views.PasswordUnlockRateThrottle, 'allow_request', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.owner = User.objects.create_user(email='venue7g@kyapture.com', password='SecurePassword123!',
                                              username='venue7g')
        downloads = {'restrict_contacts': True, 'allowed_emails': GUESTS} if self.restrict_contacts else {}
        self.gallery = Gallery.objects.create(
            photographer=self.owner, title='Venue', slug='venue-7g', is_published=True, is_active=True,
            allow_download=True, download_pin_hash=production_hash(PIN), design_settings={'downloads': downloads},
        )
        self.url = '/api/v1/public/venue7g/venue-7g/download-access/'

    def ask(self, pin=PIN, email=GUESTS[0], code=None):
        body = {'email': email, 'pin': pin}
        if code is not None:
            body['email_code'] = code
        return APIClient(REMOTE_ADDR=VENUE_IP).post(self.url, body, format='json')

    def parallel(self, fns):
        barrier = threading.Barrier(len(fns))
        results, lock = [], threading.Lock()

        def worker(fn):
            try:
                barrier.wait()
                response = fn()
                with lock:
                    results.append(response.status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(fn,)) for fn in fns]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(results), len(fns))          # every thread really posted
        return sorted(results)

    def client_locked(self, gate):
        request = RequestFactory().post('/', REMOTE_ADDR=VENUE_IP)
        keys = lockout._keys(Gallery.objects.get(pk=self.gallery.pk), gate, request)
        return cache.get(keys['client_lock']) is not None

    def counting(self, target, name):
        real = getattr(target, name)
        calls = []

        def spy(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        patcher = mock.patch.object(target, name, side_effect=spy)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls


class SharedAddressPinTests(SharedAddressBase):
    def test_8_parallel_correct_pins_from_one_address_all_get_a_token_and_lock_nothing(self):
        codes = self.parallel([lambda: self.ask() for _ in range(8)])
        print(f'\n  7G 8 parallel correct PINs, one address: {codes}')
        self.assertEqual(codes, [200] * 8)
        self.assertFalse(self.client_locked(lockout.PIN))
        self.assertEqual(self.ask().status_code, 200)

    def test_4_wrong_and_4_correct_pins_in_parallel_lock_nothing(self):
        fns = [lambda i=i: self.ask(pin=f'{100000 + i}') for i in range(4)] + [lambda: self.ask() for _ in range(4)]
        codes = self.parallel(fns)
        print(f'\n  7G 4 wrong + 4 correct PINs in parallel, one address: {codes}')
        self.assertEqual(codes, [200] * 4 + [401] * 4)
        self.assertFalse(self.client_locked(lockout.PIN))
        self.assertEqual(self.ask().status_code, 200)

    def test_20_parallel_wrong_pins_from_one_address_make_at_most_5_bcrypt_checks_then_lock(self):
        checked = self.counting(client_views, 'verify_pin')
        codes = self.parallel([lambda i=i: self.ask(pin=f'{100000 + i}') for i in range(20)])
        print(f'\n  7G 20 parallel wrong PINs, one address: {len(checked)} bcrypt checks, {codes}')
        self.assertLessEqual(len(checked), 5)
        self.assertEqual(codes.count(401), len(checked))
        self.assertEqual(codes.count(429), 20 - len(checked))
        self.assertTrue(self.client_locked(lockout.PIN))
        self.assertEqual(self.ask().status_code, 429)      # locked even for the right PIN

    def test_four_real_failures_never_lock(self):
        for i in range(4):
            self.assertEqual(self.ask(pin=f'{100000 + i}').status_code, 401)
        self.assertFalse(self.client_locked(lockout.PIN))
        self.assertEqual(self.ask().status_code, 200)


class SharedAddressEmailCodeTests(SharedAddressBase):
    restrict_contacts = True

    def setUp(self):
        super().setUp()
        for guest in GUESTS:                    # every guest asks for a code (sequentially)
            self.assertEqual(self.ask(email=guest).status_code, 202)
        self.codes = {m.to[0]: re.search(r'\b(\d{6})\b', m.body).group(1) for m in mail.outbox}
        self.assertEqual(set(self.codes), set(GUESTS))

    def wrong(self, guest):
        return '000000' if self.codes[guest] != '000000' else '111111'

    def test_8_parallel_correct_codes_from_one_address_all_get_a_token_and_lock_nothing(self):
        codes = self.parallel([lambda g=g: self.ask(email=g, code=self.codes[g]) for g in GUESTS])
        print(f'\n  7G 8 parallel correct email codes, one address: {codes}')
        self.assertEqual(codes, [200] * 8)
        self.assertFalse(self.client_locked(lockout.EMAIL_CODE))
        self.assertFalse(self.client_locked(lockout.PIN))

    def test_4_wrong_and_4_correct_codes_in_parallel_lock_nothing(self):
        fns = ([lambda g=g: self.ask(email=g, code=self.wrong(g)) for g in GUESTS[:4]]
               + [lambda g=g: self.ask(email=g, code=self.codes[g]) for g in GUESTS[4:]])
        codes = self.parallel(fns)
        print(f'\n  7G 4 wrong + 4 correct email codes in parallel, one address: {codes}')
        self.assertEqual(codes, [200] * 4 + [401] * 4)
        self.assertFalse(self.client_locked(lockout.EMAIL_CODE))

    def test_20_parallel_wrong_codes_from_one_address_make_at_most_5_checks_then_lock(self):
        # Spread over 8 addresses so the per-code limit (5 tries each) is not what stops them.
        checked = self.counting(client_views, 'check_email_code')
        codes = self.parallel([lambda i=i: self.ask(email=GUESTS[i % 8], code=self.wrong(GUESTS[i % 8]))
                               for i in range(20)])
        print(f'\n  7G 20 parallel wrong email codes, one address: {len(checked)} checks, {codes}')
        self.assertLessEqual(len(checked), 5)
        self.assertEqual(codes.count(401), len(checked))
        self.assertEqual(codes.count(429), 20 - len(checked))
        self.assertTrue(self.client_locked(lockout.EMAIL_CODE))
