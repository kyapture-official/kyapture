# backend/apps/users/tests/test_staff_7_5a.py
"""
CHUNK 7.5-A - the staff area: users list, suspend / reactivate, audit log.

  - Staff is Django `is_staff` only. Every staff route answers 401 to nobody-signed-in
    and 403 to a normal user (and to a superuser who is not staff), and a refused call
    changes and logs nothing.
  - The user list returns an allowlist of keys; the SQL never selects the password hash;
    search is one exact email; the list is paginated and throttled.
  - Suspend needs a plain-text reason; the account cannot sign in, every token dies on
    its next use (token_version), reactivation restores the login (old tokens stay dead);
    staff cannot suspend themselves or another staff/superuser.
  - Every staff action and security event writes ONE append-only audit row: actor, action,
    target, time, the trusted-proxy IP (never a client-sent header), and no secret.
"""
import uuid
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib import admin as django_admin
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory, APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from apps.clients import lockout
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.subscriptions.models import ManualPayment, SubscriptionPlan
from apps.subscriptions.testing import grant_plan
from apps.users import staff_api
from apps.users.admin import StaffAuditLogAdmin
from apps.users.audit import Action
from apps.users.models import AuditLogImmutable, Feedback, StaffAuditLog, User
from apps.users.tests import test_password_reset_7c as reset7c
from apps.users.tokens import VersionedRefreshToken
from apps.users.views import LoginAccountRateThrottle, LoginRateThrottle

PASSWORD = 'Sturdy-Pass-8842!'
USERS = '/api/v1/staff/users/'
AUDIT = '/api/v1/staff/audit/'
LOGIN = '/api/v1/auth/login/'
ME = '/api/v1/auth/me/'
REFRESH = '/api/v1/auth/token/refresh/'

LIST_KEYS = {
    'id', 'email', 'name', 'plan', 'plan_name', 'storage_used_bytes', 'storage_limit_bytes', 'collection_count',
    'joined', 'last_login', 'status', 'suspended_at', 'suspension_reason', 'is_staff',
}


def make_user(name, **extra):
    return User.objects.create_user(email=f'{name}@example.com', password=PASSWORD, username=name, **extra)


def suspend_url(user):
    return f'{USERS}{user.pk}/suspend/'


def reactivate_url(user):
    return f'{USERS}{user.pk}/reactivate/'


def audit_rows(action=None, **filters):
    rows = StaffAuditLog.objects.filter(**filters)
    return rows.filter(action=action) if action else rows


class StaffBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.staff = make_user('staffer', is_staff=True)
        self.owner = make_user('ownerone', display_name='Owner Studio')
        self.other = make_user('othertwo')
        self.client.force_authenticate(user=self.staff)

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def suspend(self, user=None, reason='Chargeback fraud', client=None):
        return (client or self.client).post(suspend_url(user or self.owner), {'reason': reason}, format='json')

    def reactivate(self, user=None, reason='Resolved with the owner', client=None):
        return (client or self.client).post(reactivate_url(user or self.owner), {'reason': reason}, format='json')


class StaffOnlyEverywhereTests(StaffBase):
    """403 to a normal user on every route, 401 to nobody; a refused call writes and changes nothing."""

    def routes(self):
        return [
            ('get', USERS, None),
            ('get', f'{USERS}?q={self.owner.email}', None),
            ('get', AUDIT, None),
            ('post', suspend_url(self.owner), {'reason': 'x'}),
            ('post', reactivate_url(self.owner), {'reason': 'x'}),
        ]

    def call(self, client, method, url, body):
        return getattr(client, method)(url, body, format='json') if method == 'post' else client.get(url)

    def test_anonymous_gets_401_everywhere(self):
        for method, url, body in self.routes():
            self.assertEqual(self.call(APIClient(), method, url, body).status_code, 401, url)

    def test_a_normal_user_gets_403_everywhere_and_nothing_changes(self):
        normal = self.as_user(self.other)
        for method, url, body in self.routes():
            response = self.call(normal, method, url, body)
            self.assertEqual(response.status_code, 403, f'{method} {url}')
            self.assertNotIn(self.owner.email, response.content.decode(), url)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
        self.assertEqual(StaffAuditLog.objects.count(), 0)

    def test_a_superuser_who_is_not_staff_gets_403(self):
        boss = make_user('bossnostaff')
        User.objects.filter(pk=boss.pk).update(is_superuser=True, is_staff=False)
        client = self.as_user(User.objects.get(pk=boss.pk))
        for method, url, body in self.routes():
            self.assertEqual(self.call(client, method, url, body).status_code, 403, url)

    def test_a_deactivated_staff_account_is_refused(self):
        User.objects.filter(pk=self.staff.pk).update(is_active=False)
        token = str(VersionedRefreshToken.for_user(User.objects.get(pk=self.staff.pk)).access_token)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(client.get(USERS).status_code, 401)

    def test_staff_reaches_every_route(self):
        self.assertEqual(self.client.get(USERS).status_code, 200)
        self.assertEqual(self.client.get(AUDIT).status_code, 200)
        self.assertEqual(self.suspend().status_code, 200)
        self.assertEqual(self.reactivate().status_code, 200)

    def test_every_view_of_the_staff_area_requires_the_staff_permission(self):
        for view in (staff_api.StaffUserListView, staff_api.StaffUserSuspendView,
                     staff_api.StaffUserReactivateView, staff_api.StaffAuditLogView):
            names = [p.__name__ for p in view.permission_classes]
            self.assertEqual(names, ['IsStaffUser'], view.__name__)


class UserListTests(StaffBase):
    def setUp(self):
        super().setUp()
        self.gallery = Gallery.objects.create(
            photographer=self.owner, title='Secret one', slug='secret-one', is_published=True, is_active=True,
            password_hash='$2b$12$galleryPasswordHashValueXXXXXXXXXXXXXXXXXXXXXXXXXXXXX', is_password_protected=True,
            download_pin_hash='$2b$12$downloadPinHashValueYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY',
        )
        Gallery.objects.create(photographer=self.owner, title='Gone', slug='gone', is_active=False)
        asset = MediaAsset(
            gallery=self.gallery, media_type=MediaAsset.MediaType.IMAGE, original_name='a.jpg',
            file_size=3 * 1024 ** 3, processing_status=MediaAsset.ProcessingStatus.READY,
        )
        asset.original_file.save('a.jpg', ContentFile(b'x'), save=False)
        asset.save()

    def row(self, user, **params):
        data = self.client.get(USERS, {'q': user.email, **params}).data
        self.assertEqual(data['count'], 1, data)
        return data['results'][0]

    def test_a_row_carries_exactly_the_allowlisted_keys_and_the_right_numbers(self):
        row = self.row(self.owner)
        self.assertEqual(set(row), LIST_KEYS)
        self.assertEqual(row['email'], self.owner.email)
        self.assertEqual(row['name'], 'Owner Studio')
        self.assertEqual(row['plan'], 'free')
        self.assertEqual(row['storage_used_bytes'], 3 * 1024 ** 3)           # beyond 32 bits, a plain int
        self.assertIsInstance(row['storage_used_bytes'], int)
        self.assertEqual(row['storage_limit_bytes'], SubscriptionPlan.get_free().storage_gb * 1024 ** 3)
        self.assertEqual(row['collection_count'], 1)                         # the trashed one is not counted
        self.assertEqual(row['status'], 'active')
        self.assertIsNone(row['last_login'])

    def test_no_secret_is_returned_anywhere(self):
        self.owner.set_password(PASSWORD)
        self.owner.save()
        for url in (USERS, f'{USERS}?q={self.owner.email}'):
            body = self.client.get(url).content.decode()
            for secret in (self.owner.password, self.gallery.password_hash, self.gallery.download_pin_hash):
                self.assertNotIn(secret, body)
            for word in ('password_hash', 'pin_hash', 'access_token', 'refresh_token', 'storage_path', 'original_file'):
                self.assertNotIn(word, body)

    def test_the_password_column_is_never_selected(self):
        with CaptureQueriesContext(connection) as queries:
            self.client.get(USERS)
        users_sql = [q['sql'] for q in queries if 'FROM "users"' in q['sql'] and 'subscription' not in q['sql'][:30]]
        self.assertTrue(users_sql)
        for sql in users_sql:
            self.assertNotIn('"users"."password"', sql)
            self.assertNotIn('"users"."token_version"', sql)

    def test_a_paid_plan_shows_its_name_and_limit(self):
        plan = grant_plan(self.owner, 'Pro')
        row = self.row(self.owner)
        self.assertEqual((row['plan'], row['plan_name']), (plan.key, plan.name))
        self.assertEqual(row['storage_limit_bytes'], plan.storage_gb * 1024 ** 3)
        self.assertEqual(self.client.get(USERS, {'plan': plan.key}).data['count'], 1)
        self.assertEqual(self.client.get(USERS, {'plan': 'free'}).data['count'], 2)         # staff + other

    def test_search_is_one_exact_email_and_nothing_else(self):
        self.assertEqual(self.client.get(USERS, {'q': self.owner.email.upper()}).data['count'], 1)
        self.assertEqual(self.client.get(USERS, {'q': 'nobody@example.com'}).data['count'], 0)
        for wildcard in ('%@example.com', 'owner%@example.com', '_wnerone@example.com'):
            response = self.client.get(USERS, {'q': wildcard})             # a valid address shape: matched literally
            self.assertEqual((response.status_code, response.data.get('count')), (200, 0), f'{wildcard} {response.data}')
        for bad in ('owner', 'ownerone@exam%.com', 'ownerone@', '@example.com', 'example.com', '%', '_', '*', '', '   ', 'a@b',
                    'ownerone@example.com, other@example.com', 'x' * 300):
            response = self.client.get(USERS, {'q': bad})
            self.assertEqual((response.status_code, response.data.get('code')), (400, 'invalid_email_query'), f'{bad!r} {response.data}')

    def test_filters(self):
        Q = lambda **p: {r['email'] for r in self.client.get(USERS, p).data['results']}      # noqa: E731
        self.assertEqual(Q(status='active'), {self.staff.email, self.owner.email, self.other.email})
        User.objects.filter(pk=self.other.pk).update(is_active=False)
        self.assertEqual(Q(status='suspended'), {self.other.email})
        free_gb = SubscriptionPlan.get_free().storage_gb
        self.assertEqual(Q(storage='empty'), {self.staff.email, self.other.email})
        self.assertEqual(Q(storage='full'), set() if free_gb > 3 else {self.owner.email})
        MediaAsset.objects.filter(gallery=self.gallery).update(file_size=free_gb * 1024 ** 3)
        self.assertEqual(Q(storage='full'), {self.owner.email})
        MediaAsset.objects.filter(gallery=self.gallery).update(file_size=int(free_gb * 1024 ** 3 * 0.85))
        self.assertEqual(Q(storage='near_full'), {self.owner.email})
        self.assertEqual(Q(storage='full'), set())
        for params in ({'plan': 'nope'}, {'status': 'x'}, {'storage': 'x'}, {'sort': 'x'}):
            self.assertEqual(self.client.get(USERS, params).status_code, 400, params)

    def test_sort_by_storage_puts_the_biggest_first(self):
        first = self.client.get(USERS, {'sort': 'storage'}).data['results'][0]
        self.assertEqual(first['email'], self.owner.email)

    def test_pagination_caps_the_page(self):
        for i in range(30):
            make_user(f'bulk{i:02d}')
        page = self.client.get(USERS).data
        self.assertEqual((len(page['results']), page['count']), (25, 33))
        self.assertIsNotNone(page['next'])
        self.assertEqual(len(self.client.get(USERS, {'page': 2}).data['results']), 8)
        self.assertEqual(len(self.client.get(USERS, {'page_size': 100000}).data['results']), 33)
        self.assertLessEqual(staff_api.StaffPagination.max_page_size, 100)

    def test_the_list_is_throttled_per_staff_user(self):
        with mock.patch.dict(staff_api.StaffListThrottle.THROTTLE_RATES, {'staff_list': '3/minute'}):
            codes = [self.client.get(USERS).status_code for _ in range(5)]
            self.assertEqual(codes, [200, 200, 200, 429, 429])
            another = make_user('secondstaff', is_staff=True)
            self.assertEqual(self.as_user(another).get(USERS).status_code, 200)       # its own bucket

    def test_there_is_no_export_route(self):
        for path in (f'{USERS}export/', f'{USERS}?format=csv', '/api/v1/staff/export/'):
            response = self.client.get(path)
            self.assertNotIn('text/csv', response.get('Content-Type', ''))
        self.assertEqual(self.client.get('/api/v1/staff/export/').status_code, 404)

    def test_reading_the_list_is_audited(self):
        self.client.get(USERS, {'status': 'active'})
        row = audit_rows(Action.USER_LIST).get()
        self.assertEqual((row.actor_id, row.actor_email), (self.staff.pk, self.staff.email))
        self.assertEqual(row.reason, 'status=active page=1')
        self.client.get(USERS, {'q': self.owner.email})
        lookup = audit_rows(Action.USER_LOOKUP).get()
        self.assertEqual((lookup.target_id, lookup.reason), (self.owner.pk, 'found'))
        self.client.get(USERS, {'q': 'ghost@example.com'})
        ghost = audit_rows(Action.USER_LOOKUP).exclude(pk=lookup.pk).get()
        self.assertEqual((ghost.target_id, ghost.target_email, ghost.reason), (None, '', 'not found'))
        self.assertNotIn('ghost', repr(list(StaffAuditLog.objects.values())))


class SuspendTests(StaffBase):
    def login_owner(self):
        client = APIClient()
        response = client.post(LOGIN, {'email': self.owner.email, 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return client, response.cookies['access_token'].value, response.cookies['refresh_token'].value

    def test_suspend_switches_the_account_off_and_says_why(self):
        response = self.suspend(reason='Chargeback fraud')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), LIST_KEYS)
        self.assertEqual((response.data['status'], response.data['suspension_reason']), ('suspended', 'Chargeback fraud'))
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)
        self.assertIsNotNone(self.owner.suspended_at)
        self.assertEqual(self.owner.suspension_reason, 'Chargeback fraud')

    def test_a_suspended_user_cannot_sign_in(self):
        self.suspend()
        client = APIClient()
        right = client.post(LOGIN, {'email': self.owner.email, 'password': PASSWORD}, format='json')
        self.assertEqual(right.status_code, 400)
        self.assertIn('suspended', str(right.data))
        self.assertNotIn('access_token', right.cookies)
        wrong = client.post(LOGIN, {'email': self.owner.email, 'password': 'Wrong-Pass-1!'}, format='json')
        self.assertIn('Invalid email or password', str(wrong.data))            # nothing learned without the password
        self.assertNotIn('suspended', str(wrong.data))

    def test_every_token_dies_on_its_next_use(self):
        client, access, refresh = self.login_owner()
        self.assertEqual(client.get(ME).status_code, 200)
        bearer = APIClient()
        bearer.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        before = User.objects.get(pk=self.owner.pk).token_version
        self.suspend()
        self.assertEqual(User.objects.get(pk=self.owner.pk).token_version, before + 1)
        self.assertEqual(client.get(ME).status_code, 401)                       # cookie
        self.assertEqual(bearer.get(ME).status_code, 401)                       # bearer
        self.assertEqual(client.post(REFRESH).status_code, 401)                 # refresh cookie
        self.assertTrue(BlacklistedToken.objects.filter(token__user=self.owner).exists())

    def test_reactivation_restores_the_login_but_not_the_old_tokens(self):
        client, access, _ = self.login_owner()
        self.suspend()
        response = self.reactivate()
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data['status'], response.data['suspension_reason']), ('active', ''))
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
        self.assertIsNone(self.owner.suspended_at)
        self.assertEqual(client.get(ME).status_code, 401)                       # the old session stays dead
        fresh, _, _ = self.login_owner()
        self.assertEqual(fresh.get(ME).status_code, 200)

    def test_staff_cannot_suspend_themselves_or_another_staff_or_superuser(self):
        other_staff = make_user('otherstaff', is_staff=True)
        root = make_user('rootuser')
        User.objects.filter(pk=root.pk).update(is_superuser=True)
        for target, code in ((self.staff, 'cannot_change_self'), (other_staff, 'cannot_change_staff'),
                             (root, 'cannot_change_staff')):
            response = self.suspend(target)
            self.assertEqual((response.status_code, response.data['code']), (403, code), target.email)
            self.assertTrue(User.objects.get(pk=target.pk).is_active)
        User.objects.filter(pk=other_staff.pk).update(is_active=False)
        self.assertEqual(self.reactivate(other_staff).status_code, 403)         # staff accounts are admin-only
        self.assertEqual(StaffAuditLog.objects.filter(action__in=[Action.SUSPEND, Action.REACTIVATE]).count(), 0)

    def test_unknown_id_and_wrong_state(self):
        self.assertEqual(self.client.post(f'{USERS}{uuid.uuid4()}/suspend/', {'reason': 'x'}, format='json').status_code, 404)
        self.assertEqual(self.client.post(f'{USERS}not-a-uuid/suspend/', {'reason': 'x'}, format='json').status_code, 404)
        self.assertEqual(self.reactivate().data['code'], 'not_suspended')
        self.suspend()
        again = self.suspend()
        self.assertEqual((again.status_code, again.data['code']), (409, 'already_suspended'))
        self.assertEqual(audit_rows(Action.SUSPEND).count(), 1)

    def test_the_reason_is_required_plain_text_and_limited(self):
        for body in ({}, {'reason': ''}, {'reason': '   \n\t '}, {'reason': None}, {'reason': 5}, {'reason': ['x']}):
            response = self.client.post(suspend_url(self.owner), body, format='json')
            self.assertEqual((response.status_code, response.data['code']), (400, 'reason_required'), body)
        too_long = self.client.post(suspend_url(self.owner), {'reason': 'x' * 301}, format='json')
        self.assertEqual((too_long.status_code, too_long.data['code']), (400, 'reason_too_long'))
        self.assertTrue(User.objects.get(pk=self.owner.pk).is_active)
        self.assertEqual(self.reactivate(reason='  ').data['code'], 'reason_required')      # reactivation needs one too
        ok = self.client.post(suspend_url(self.owner), {'reason': 'y' * 300}, format='json')
        self.assertEqual(ok.status_code, 200)

    def test_the_reason_is_stored_and_returned_as_plain_one_line_text(self):
        text = '<script>alert(1)</script> & "quotes"\nsecond\tline\x00 end'
        self.suspend(reason=text)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.suspension_reason, '<script>alert(1)</script> & "quotes" second line end')
        response = self.client.get(USERS, {'q': self.owner.email})
        self.assertTrue(response['Content-Type'].startswith('application/json'))       # JSON string: never HTML
        self.assertEqual(response.data['results'][0]['suspension_reason'], self.owner.suspension_reason)

    def test_the_audit_row_names_who_what_whom_and_when(self):
        self.suspend(reason='Spam galleries')
        row = audit_rows(Action.SUSPEND).get()
        self.assertEqual((row.actor_id, row.actor_email), (self.staff.pk, self.staff.email))
        self.assertEqual((row.target_id, row.target_email), (self.owner.pk, self.owner.email))
        self.assertEqual((row.reason, row.ip), ('Spam galleries', '127.0.0.1'))
        self.assertIsNotNone(row.created_at)
        self.reactivate(reason='Appeal accepted')
        back = audit_rows(Action.REACTIVATE).get()
        self.assertEqual((back.actor_id, back.target_id, back.reason), (self.staff.pk, self.owner.pk, 'Appeal accepted'))

    def test_the_audit_ip_comes_from_the_trusted_proxy_setup_not_a_client_header(self):
        self.suspend(reason='one')
        self.client.post(reactivate_url(self.owner), {'reason': 'two'}, format='json',
                         HTTP_X_FORWARDED_FOR='9.9.9.9, 8.8.8.8', REMOTE_ADDR='203.0.113.5')
        self.assertEqual(audit_rows(Action.REACTIVATE).get().ip, '203.0.113.5')          # NUM_PROXIES=0: the peer
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'NUM_PROXIES': 1}):
            self.client.post(suspend_url(self.owner), {'reason': 'three'}, format='json',
                             HTTP_X_FORWARDED_FOR='6.6.6.6, 198.51.100.7', REMOTE_ADDR='10.0.0.2')
        self.assertEqual(audit_rows(Action.SUSPEND).order_by('-id').first().ip, '198.51.100.7')
        self.assertFalse(audit_rows(ip='6.6.6.6').exists() or audit_rows(ip='9.9.9.9').exists())

    def test_the_change_and_its_audit_row_commit_together(self):
        with mock.patch('apps.users.staff_api.audit.record', side_effect=RuntimeError('disk full')):
            response = self.suspend()
        self.assertEqual(response.status_code, 500)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)                                    # rolled back with it
        self.assertEqual(self.owner.suspension_reason, '')

    def test_the_owners_public_media_is_rotated_to_new_keys(self):
        Gallery.objects.create(photographer=self.owner, title='A', slug='a-gal', is_published=True)
        Gallery.objects.create(photographer=self.owner, title='B', slug='b-gal')
        Gallery.objects.create(photographer=self.other, title='C', slug='c-gal', is_published=True)
        with mock.patch('apps.photos.public_media.queue_rotation') as queued:
            self.suspend()
        self.assertEqual({call.args[0].slug for call in queued.call_args_list}, {'a-gal', 'b-gal'})

    def test_the_throttle_limits_account_actions(self):
        with mock.patch.dict(staff_api.StaffActionThrottle.THROTTLE_RATES, {'staff_action': '2/hour'}):
            codes = [self.client.post(suspend_url(self.owner), {'reason': 'x'}, format='json').status_code
                     for _ in range(3)]
        self.assertEqual(codes, [200, 409, 429])


class AuditLogTests(StaffBase):
    def test_staff_can_read_it_and_nothing_else(self):
        self.suspend()
        data = self.client.get(AUDIT).data
        row = next(r for r in data['results'] if r['action'] == Action.SUSPEND)
        self.assertEqual(set(row), {'id', 'created_at', 'action', 'action_label', 'actor_id', 'actor_email',
                                    'target_id', 'target_email', 'ip', 'reason'})
        self.assertEqual((row['actor_email'], row['target_email'], row['action_label']),
                         (self.staff.email, self.owner.email, 'Suspended an account'))
        for method in ('post', 'put', 'patch', 'delete'):
            response = getattr(self.client, method)(AUDIT, {'reason': 'x'}, format='json')
            self.assertEqual(response.status_code, 405, method)
        self.assertEqual(self.client.delete(f'{AUDIT}{row["id"]}/').status_code, 404)
        self.assertEqual(audit_rows(Action.SUSPEND).count(), 1)

    def test_filter_order_and_the_view_itself_is_logged(self):
        self.suspend()
        self.reactivate()
        only = self.client.get(AUDIT, {'action': Action.REACTIVATE}).data
        self.assertEqual({r['action'] for r in only['results']}, {Action.REACTIVATE})
        self.assertEqual(self.client.get(AUDIT, {'action': 'nope'}).status_code, 400)
        newest_first = [r['created_at'] for r in self.client.get(AUDIT).data['results']]
        self.assertEqual(newest_first, sorted(newest_first, reverse=True))
        self.assertTrue(audit_rows(Action.AUDIT_VIEW, actor_id=self.staff.pk).exists())

    def test_the_orm_refuses_to_change_or_remove_a_row(self):
        self.suspend()
        row = audit_rows(Action.SUSPEND).get()
        row.reason = 'edited'
        for attempt in (row.save, row.delete,
                        lambda: StaffAuditLog.objects.all().update(reason='x'),
                        lambda: StaffAuditLog.objects.all().delete(),
                        lambda: StaffAuditLog.objects.filter(pk=row.pk).delete(),
                        lambda: StaffAuditLog.objects.bulk_update([row], ['reason'])):
            with self.assertRaises(AuditLogImmutable):
                attempt()
        self.assertEqual(audit_rows(Action.SUSPEND).get().reason, 'Chargeback fraud')

    def test_the_database_refuses_it_too(self):
        if connection.vendor != 'postgresql':
            self.skipTest('the trigger is PostgreSQL only')
        self.suspend()
        for sql in ("UPDATE staff_audit_log SET reason = 'x'", 'DELETE FROM staff_audit_log'):
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql)
        self.assertEqual(audit_rows(Action.SUSPEND).count(), 1)

    def test_the_admin_shows_it_read_only(self):
        root = make_user('adminroot', is_staff=True, is_superuser=True)
        request = RequestFactory().get('/admin/')
        request.user = root
        model_admin = StaffAuditLogAdmin(StaffAuditLog, django_admin.site)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertEqual(model_admin.get_actions(request), {})
        self.suspend()
        row = audit_rows(Action.SUSPEND).get()
        browser = APIClient()
        browser.force_login(root)
        self.assertEqual(browser.get('/admin/users/staffauditlog/').status_code, 200)
        self.assertEqual(browser.post(f'/admin/users/staffauditlog/{row.pk}/change/', {'reason': 'x'}).status_code, 403)
        self.assertEqual(browser.post(f'/admin/users/staffauditlog/{row.pk}/delete/', {'post': 'yes'}).status_code, 403)
        self.assertEqual(browser.get('/admin/users/staffauditlog/add/').status_code, 403)

    def test_a_row_outlives_the_deletion_of_its_accounts(self):
        self.suspend()
        self.owner.delete()
        row = audit_rows(Action.SUSPEND).get()
        self.assertEqual((row.target_email, row.actor_email), (self.owner.email, self.staff.email))


class SecurityEventTests(reset7c.ResetTestBase):
    """Password change, password reset, login lockouts and gallery lockouts each leave one row, with no secret."""

    def assert_no_secret(self, *secrets):
        dump = repr(list(StaffAuditLog.objects.values()))
        for secret in secrets:
            self.assertNotIn(secret, dump)

    def test_a_password_change_is_recorded_without_the_passwords(self):
        client, _ = self.login()
        with reset7c.run_inline(reset7c.tasks.send_password_changed_email_task), self.captureOnCommitCallbacks(execute=True):
            response = client.put(reset7c.CHANGE_URL, {
                'old_password': reset7c.OLD_PASSWORD, 'new_password': reset7c.NEW_PASSWORD,
                'new_password2': reset7c.NEW_PASSWORD}, format='json', REMOTE_ADDR='198.51.100.20')
        self.assertEqual(response.status_code, 200, response.data)
        row = audit_rows(Action.PASSWORD_CHANGE).get()
        self.assertEqual((row.actor_id, row.target_id, row.reason, row.ip),
                         (self.user.pk, self.user.pk, 'self', '198.51.100.20'))
        self.assert_no_secret(reset7c.OLD_PASSWORD, reset7c.NEW_PASSWORD, self.user.password)

    def test_a_password_reset_is_recorded_without_the_link_or_password(self):
        self.request_reset(self.user.email)
        _, token = self.last_link()
        response = self.confirm(token)
        self.assertEqual(response.status_code, 200, response.data)
        row = audit_rows(Action.PASSWORD_RESET).get()
        self.assertEqual((row.actor_id, row.target_id, row.reason, row.ip), (None, self.user.pk, 'reset', '127.0.0.1'))
        self.assert_no_secret(token, reset7c.NEW_PASSWORD)
        self.assertEqual(audit_rows(Action.PASSWORD_CHANGE).count(), 0)         # a reset is its own event

    def test_a_password_set_in_django_admin_is_recorded(self):
        root = make_user('adminchanger', is_staff=True, is_superuser=True)
        admin_client = APIClient()
        admin_client.force_login(root)
        with reset7c.run_inline(reset7c.tasks.send_password_changed_email_task), self.captureOnCommitCallbacks(execute=True):
            page = admin_client.post(f'/admin/users/user/{self.user.pk}/password/', {
                'password1': reset7c.NEW_PASSWORD, 'password2': reset7c.NEW_PASSWORD, 'usable_password': 'true'})
        self.assertEqual(page.status_code, 302)
        row = audit_rows(Action.PASSWORD_CHANGE).get()
        self.assertEqual((row.actor_id, row.target_id, row.reason), (root.pk, self.user.pk, 'admin'))
        self.assert_no_secret(reset7c.NEW_PASSWORD)

    def test_switching_an_account_off_in_django_admin_is_a_suspension(self):
        root = make_user('adminswitch', is_staff=True, is_superuser=True)
        admin_client = APIClient()
        admin_client.force_login(root)
        form = {'username': self.user.username, 'email': self.user.email, 'date_joined_0': '2026-01-01',
                'date_joined_1': '00:00:00', 'branding_color': '#111827', 'portfolio_public': 'on'}
        before = User.objects.get(pk=self.user.pk).token_version
        page = admin_client.post(f'/admin/users/user/{self.user.pk}/change/', form)       # is_active unchecked
        self.assertEqual(page.status_code, 302, getattr(page, 'content', b'')[:800])
        self.assertFalse(User.objects.get(pk=self.user.pk).is_active)
        self.assertEqual(User.objects.get(pk=self.user.pk).token_version, before + 1)
        row = audit_rows(Action.SUSPEND).get()
        self.assertEqual((row.actor_id, row.target_id, row.reason), (root.pk, self.user.pk, 'django admin'))
        page = admin_client.post(f'/admin/users/user/{self.user.pk}/change/', {**form, 'is_active': 'on'})
        self.assertEqual(page.status_code, 302)
        self.assertTrue(User.objects.get(pk=self.user.pk).is_active)
        self.assertEqual(audit_rows(Action.REACTIVATE).get().reason, 'django admin')

    @override_settings(ADMIN_LOGIN_MAX_FAILURES_PER_IP=2, ADMIN_LOGIN_MAX_FAILURES_PER_ACCOUNT=50)
    def test_an_admin_login_lock_is_recorded_once_and_names_only_a_real_account(self):
        for typed in (self.user.email, 'ghost@example.com'):
            cache.clear()
            for _ in range(3):
                APIClient().post('/admin/login/', {'username': typed, 'password': 'Wrong-Pass-9!'},
                                 REMOTE_ADDR='198.51.100.31')
        rows = list(audit_rows(Action.LOGIN_LOCKOUT).order_by('id'))
        self.assertEqual([(r.target_id, r.reason, r.ip) for r in rows],
                         [(self.user.pk, 'admin_ip', '198.51.100.31'), (None, 'admin_ip', '198.51.100.31')])
        self.assert_no_secret('ghost@example.com', 'Wrong-Pass-9!')

    def test_an_account_login_lockout_is_recorded_once_per_window(self):
        rates = {'login_account': '2/hour', 'login': '1000/minute'}
        with mock.patch.dict(LoginAccountRateThrottle.THROTTLE_RATES, rates, clear=False), \
                mock.patch.dict(LoginRateThrottle.THROTTLE_RATES, rates, clear=False):
            for _ in range(5):
                APIClient().post(reset7c.LOGIN_URL, {'email': self.user.email, 'password': 'Wrong-Pass-9!'},
                                 format='json', REMOTE_ADDR='198.51.100.32')
            for _ in range(4):
                APIClient().post(reset7c.LOGIN_URL, {'email': 'ghost2@example.com', 'password': 'x'},
                                 format='json', REMOTE_ADDR='198.51.100.33')
        rows = list(audit_rows(Action.LOGIN_LOCKOUT).order_by('id'))
        self.assertEqual([(r.target_id, r.reason, r.ip) for r in rows],
                         [(self.user.pk, 'account_rate', '198.51.100.32'), (None, 'account_rate', '198.51.100.33')])
        self.assert_no_secret('ghost2@example.com', 'Wrong-Pass-9!')

    @override_settings(GATE_GALLERY_MAX_FAILURES=1)
    def test_a_gallery_gate_lock_is_recorded_from_the_lockouts_own_notification(self):
        gallery = Gallery.objects.create(photographer=self.user, title='Locked', slug='locked-gal', is_published=True)
        request = APIRequestFactory().post('/x', REMOTE_ADDR='198.51.100.40')
        lockout.record_failure(gallery, lockout.PIN, request)
        row = audit_rows(Action.GALLERY_LOCKOUT).get()
        self.assertEqual((row.target_id, row.actor_id, row.reason), (self.user.pk, None, 'pin'))
        self.assert_no_secret('Locked')
        lockout.record_failure(gallery, lockout.PIN, request)        # still inside the window: no second lock event
        self.assertEqual(audit_rows(Action.GALLERY_LOCKOUT).count(), 1)

    def test_a_failing_audit_write_never_breaks_a_sign_in_or_a_password_change(self):
        client, response = self.login()
        self.assertEqual(response.status_code, 200)
        with mock.patch('apps.users.audit.record', side_effect=RuntimeError('db down')), \
                reset7c.run_inline(reset7c.tasks.send_password_changed_email_task), \
                self.captureOnCommitCallbacks(execute=True):
            done = client.put(reset7c.CHANGE_URL, {
                'old_password': reset7c.OLD_PASSWORD, 'new_password': reset7c.NEW_PASSWORD,
                'new_password2': reset7c.NEW_PASSWORD}, format='json')
        self.assertEqual(done.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(reset7c.NEW_PASSWORD))
        self.assertEqual(StaffAuditLog.objects.count(), 0)

    def test_last_login_is_set_by_a_real_sign_in(self):
        self.assertIsNone(User.objects.get(pk=self.user.pk).last_login)
        self.login()
        self.assertIsNotNone(User.objects.get(pk=self.user.pk).last_login)


class OtherStaffActionsAreAuditedTests(StaffBase):
    def test_feedback_status_changes_and_inbox_reads(self):
        feedback = Feedback.objects.create(user=self.owner, category='bug', subject='s', message='m')
        self.client.get('/api/v1/feedback/inbox/')
        self.assertEqual(audit_rows(Action.INBOX_VIEW).get().reason, 'feedback')
        response = self.client.patch(f'/api/v1/feedback/inbox/{feedback.pk}/', {'status': 'resolved'}, format='json')
        self.assertEqual(response.status_code, 200)
        row = audit_rows(Action.FEEDBACK_STATUS).get()
        self.assertEqual((row.actor_id, row.target_id, row.reason), (self.staff.pk, self.owner.pk, 'status=resolved'))

    def test_payment_queue_reads_and_reviews(self):
        plan = SubscriptionPlan.objects.exclude(key='free').first()
        payment = ManualPayment.objects.create(
            user=self.owner, plan=plan, amount=Decimal('100.00'), payment_proof='payment_proofs/x.png')
        self.assertEqual(self.client.get('/api/v1/subscriptions/admin/payments/').status_code, 200)
        self.assertEqual(audit_rows(Action.INBOX_VIEW).get().reason, 'payments')
        response = self.client.post(
            f'/api/v1/subscriptions/payments/{payment.pk}/review/', {'action': 'reject', 'admin_note': 'blurry'},
            format='json')
        self.assertEqual(response.status_code, 200, response.data)
        row = audit_rows(Action.PAYMENT_REVIEW).get()
        self.assertEqual((row.actor_id, row.target_id, row.reason), (self.staff.pk, self.owner.pk, 'reject'))
        normal = self.as_user(self.other)
        self.assertEqual(normal.post(f'/api/v1/subscriptions/payments/{payment.pk}/review/',
                                     {'action': 'approve'}, format='json').status_code, 403)
        self.assertEqual(audit_rows(Action.PAYMENT_REVIEW).count(), 1)
