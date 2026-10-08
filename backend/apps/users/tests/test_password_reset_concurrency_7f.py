# backend/apps/users/tests/test_password_reset_concurrency_7f.py
"""
7F (debt row 150, reviewer F5): one reset link submitted several times AT ONCE
is used exactly once. PasswordResetConfirmView takes a row lock on the link
(select_for_update); the requests that wait for it find the row deleted and get
the "link is not valid" answer. Real threads on real Postgres, so this is a
TransactionTestCase.
No serialized_rollback: a TransactionTestCase flushes every table after each
test, so setUp re-creates the plan rows it needs (ensure_seed_plans) and the
result does not depend on which test class ran before it.
"""
import threading
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.subscriptions.testing import ensure_seed_plans
from apps.users import tasks, views as user_views
from apps.users.models import PasswordResetToken, User
from apps.users.password_reset import issue_token

CONFIRM_URL = '/api/v1/auth/password/reset/confirm/'


class ParallelResetConfirmTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.assertEqual(ensure_seed_plans(), 4)
        for patcher in (
            mock.patch.object(user_views.PasswordResetConfirmRateThrottle, 'allow_request', return_value=True),
            mock.patch.object(tasks.send_password_changed_email_task, 'delay'),   # no broker, no real mail
        ):
            self.mocked = patcher.start()
            self.addCleanup(patcher.stop)
        self.user = User.objects.create_user(
            username='reset7f', email='reset-7f@example.com', password='OldPassword123!')

    def test_six_simultaneous_submissions_of_one_link_succeed_exactly_once(self):
        raw = issue_token(self.user)
        n = 6
        passwords = [f'Parallel-Lantern-{i}84' for i in range(n)]
        barrier = threading.Barrier(n)
        results, lock = {}, threading.Lock()

        def worker(i):
            try:
                barrier.wait()
                response = APIClient().post(CONFIRM_URL, {
                    'token': raw, 'new_password': passwords[i], 'new_password2': passwords[i],
                }, format='json')
                with lock:
                    results[i] = (response.status_code, response.data.get('code'))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        print(f'\n  7F parallel reset confirm, {len(results)} threads: {sorted(results.values(), key=str)}')
        self.assertEqual(len(results), n)                     # every thread really posted
        winners = [i for i, (code, _) in results.items() if code == 200]
        self.assertEqual(len(winners), 1, results)
        losers = [results[i] for i in results if i not in winners]
        self.assertEqual(losers, [(400, 'reset_link_invalid')] * (n - 1), results)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(passwords[winners[0]]))
        for i in set(range(n)) - set(winners):
            self.assertFalse(self.user.check_password(passwords[i]))
        self.assertFalse(PasswordResetToken.objects.filter(user=self.user).exists())
        self.assertEqual(self.mocked.call_count, 1)         # one "password changed" email
