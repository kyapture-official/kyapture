# backend/apps/clients/tests/test_pin_counter_lock_7f.py
"""
7F (reviewer 7R, F1): the "Limit PIN Usage" counter and the owner's gallery
save both write design_settings. Each must lock the gallery row and work on
the fresh row, so that:

  - N parallel correct-PIN requests when one use is left get exactly ONE token;
  - an owner save landing while a PIN use is in flight is not undone by it;
  - a PIN use landing while an owner save is in flight is not undone by it.

Real threads and real Postgres row locks, so this is a TransactionTestCase.
No serialized_rollback: a TransactionTestCase flushes every table after each
test, so setUp re-creates the plan rows it needs (ensure_seed_plans) and the
result does not depend on which test class ran before it.
"""
import threading
from unittest import mock

import bcrypt
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.subscriptions.testing import ensure_seed_plans

from apps.clients import views as client_views
from apps.galleries import serializers as gallery_serializers
from apps.galleries.models import Gallery

User = get_user_model()
PIN = '4821'


class PinCounterLockTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.assertEqual(ensure_seed_plans(), 4)
        self.photographer = User.objects.create_user(
            email='pinlock7f@kyapture.com', password='SecurePassword123!', username='pinlock7f',
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer, title='Lock', slug='lock-7f',
            is_published=True, is_active=True, allow_download=True,
            download_pin_hash=bcrypt.hashpw(PIN.encode(), bcrypt.gensalt()).decode(),
            design_settings={'privacy': {'pin_limit': 3, 'pin_use_count': 2}},
        )
        self.access_url = '/api/v1/public/pinlock7f/lock-7f/download-access/'
        self.detail_url = '/api/v1/galleries/lock-7f/'
        # The 5/min/IP throttle is not what is under test here: every thread
        # shares one test IP, and the point is what the row lock lets through.
        patcher = mock.patch.object(client_views.PasswordUnlockRateThrottle, 'allow_request', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def stored(self):
        return Gallery.objects.get(pk=self.gallery.pk).design_settings

    def use_pin(self, ip='192.0.2.1'):
        # One address per visitor: the per-client lockout (5 tries, counted before the
        # check since 7F F6) is not what these tests are about.
        return APIClient(REMOTE_ADDR=ip).post(self.access_url, {'email': 'c@example.com', 'pin': PIN}, format='json')

    def owner_patch(self, body):
        client = APIClient()
        client.force_authenticate(user=self.photographer)
        return client.patch(self.detail_url, body, format='json')

    def test_parallel_correct_pins_with_one_use_left_get_exactly_one_token(self):
        n = 8
        barrier = threading.Barrier(n)
        codes = []
        lock = threading.Lock()

        def worker(i):
            try:
                barrier.wait()
                response = self.use_pin(ip=f'198.51.100.{i + 1}')
                with lock:
                    codes.append(response.status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        print(f'\n  7F parallel PIN uses, {len(codes)} threads, 1 use left: {sorted(codes)}')
        self.assertEqual(len(codes), n)                       # every thread really posted
        self.assertEqual(codes.count(200), 1, codes)
        self.assertEqual(codes.count(403), n - 1, codes)
        self.assertEqual(self.stored()['privacy']['pin_use_count'], 3)

    OWNER_SAVE = {'design_settings': {
        'downloads': {
            'require_email': True, 'limit_total': 9,
            'high_res': {'enabled': False, 'mode': '3600'}, 'web': {'enabled': True, 'px': 2048},
        },
        'privacy': {'pin_limit': 5},
    }}

    def assert_owner_save_and_pin_use_both_kept(self):
        stored = self.stored()
        self.assertEqual(stored['privacy'], {'pin_limit': 5, 'pin_use_count': 3}, stored)
        self.assertEqual(stored['downloads']['limit_total'], 9, stored)
        self.assertFalse(stored['downloads']['high_res']['enabled'], stored)

    def test_an_owner_save_during_a_pin_use_keeps_both_changes(self):
        """The PIN request has loaded the gallery; the owner saves; then the PIN use is recorded."""
        pin_paused, owner_done = threading.Event(), threading.Event()
        real_success = client_views.lockout.record_success
        result = {}

        def paused_success(*args, **kwargs):
            real_success(*args, **kwargs)
            pin_paused.set()
            owner_done.wait(10)          # the owner's save lands here, mid-request

        def pin_worker():
            try:
                result['pin'] = self.use_pin().status_code
            finally:
                connection.close()

        with mock.patch.object(client_views.lockout, 'record_success', side_effect=paused_success):
            thread = threading.Thread(target=pin_worker)
            thread.start()
            try:
                self.assertTrue(pin_paused.wait(10))
                saved = self.owner_patch(self.OWNER_SAVE)
                self.assertEqual(saved.status_code, 200, saved.data)
            finally:
                owner_done.set()
                thread.join()
                connection.close()
        self.assertEqual(result['pin'], 200)
        self.assert_owner_save_and_pin_use_both_kept()

    def test_a_pin_use_during_an_owner_save_keeps_both_changes(self):
        """The owner's save has read the gallery; a PIN use comes in; then the owner's save is written."""
        pin_done = threading.Event()
        real_normalize = gallery_serializers.normalize_privacy_settings
        result = {}

        def pin_worker():
            try:
                result['pin'] = self.use_pin().status_code
            finally:
                pin_done.set()
                connection.close()

        thread = threading.Thread(target=pin_worker)

        def paused_normalize(*args, **kwargs):
            thread.start()
            pin_done.wait(3)             # with the row locked the PIN use waits instead
            return real_normalize(*args, **kwargs)

        with mock.patch.object(gallery_serializers, 'normalize_privacy_settings', side_effect=paused_normalize):
            saved = self.owner_patch(self.OWNER_SAVE)
        thread.join()
        connection.close()
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(result['pin'], 200)
        self.assert_owner_save_and_pin_use_both_kept()

    def test_setting_a_new_pin_during_a_pin_use_keeps_the_reset(self):
        """set-download-pin zeroes the count; a PIN use already in flight must not write the old count back."""
        pin_paused, owner_done = threading.Event(), threading.Event()
        real_success = client_views.lockout.record_success
        result = {}

        def paused_success(*args, **kwargs):
            real_success(*args, **kwargs)
            pin_paused.set()
            owner_done.wait(10)

        def pin_worker():
            try:
                result['pin'] = self.use_pin().status_code
            finally:
                connection.close()

        patcher = mock.patch.object(client_views.lockout, 'record_success', side_effect=paused_success)
        patcher.start()
        self.addCleanup(patcher.stop)
        thread = threading.Thread(target=pin_worker)
        thread.start()
        try:
            self.assertTrue(pin_paused.wait(10))
            client = APIClient()
            client.force_authenticate(user=self.photographer)
            changed = client.post('/api/v1/galleries/lock-7f/set-download-pin/', {'pin': '9999'}, format='json')
            self.assertEqual(changed.status_code, 200, changed.data)
        finally:
            owner_done.set()
            thread.join()
            connection.close()
        # The in-flight request proved the OLD pin; the new pin's count starts at 0
        # and that old proof may not use up the new pin's allowance.
        self.assertEqual(self.stored()['privacy']['pin_use_count'], 0, (result, self.stored()))
