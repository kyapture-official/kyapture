# backend/apps/users/tests/test_privilege_7a.py
"""
CHUNK 7-A (tenancy) - the account side.

  1. Privilege escalation: no write endpoint that touches the user lets a normal
     user set is_staff, is_superuser, is_active, is_active_plan, email, plan,
     email_verified, password or any other privileged field (6.3-B added
     is_staff to /auth/me/ as a READ-only field).
  2. Feedback tenancy: /mine/ is the caller's own rows; /inbox/ and PATCH are
     staff-only; nobody reads, edits or deletes another user's feedback by id.
  3. Staff: a normal user reaches no staff endpoint (API or Django admin), and a
     staff account has no ownership of other photographers' data on the API.
  4. A deactivated user's existing access and refresh tokens stop working.
"""
import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.galleries.models import Gallery
from apps.subscriptions.models import UserSubscription
from apps.users.models import Feedback

User = get_user_model()
PASSWORD = 'Sturdy-Pass-8842!'

PRIVILEGED = {
    'is_staff': True, 'is_superuser': True, 'is_active': False, 'is_active_plan': True,
    'email': 'owned@evil.example', 'plan': 'pro', 'email_verified': True, 'id': str(uuid.uuid4()),
    'date_joined': '2000-01-01T00:00:00Z', 'last_login': '2000-01-01T00:00:00Z', 'created_at': '2000-01-01T00:00:00Z',
    'groups': [1], 'user_permissions': [1], 'password': 'Hijacked-Pass-1234!', 'subscription': 'pro',
}


def snapshot(user):
    user.refresh_from_db()
    return {
        'is_staff': user.is_staff, 'is_superuser': user.is_superuser, 'is_active': user.is_active,
        'is_active_plan': user.is_active_plan, 'email': user.email, 'id': user.id,
        'date_joined': user.date_joined, 'last_login': user.last_login, 'created_at': user.created_at,
        'groups': list(user.groups.all()), 'perms': list(user.user_permissions.all()),
        'password_ok': user.check_password(PASSWORD),
        'subscription': UserSubscription.objects.filter(user=user).exists(),
    }


class Base(APITestCase):
    def make_user(self, name, **extra):
        return User.objects.create_user(email=f'{name}@kyapture.com', password=PASSWORD, username=name, **extra)

    def setUp(self):
        cache.clear()
        self.user = self.make_user('privuser', display_name='Priv')
        self.client.force_authenticate(self.user)


class PrivilegedFieldsTests(Base):
    def assert_unchanged(self, before, label):
        self.assertEqual(snapshot(self.user), before, label)

    def test_profile_put_json_ignores_every_privileged_field(self):
        before = snapshot(self.user)
        response = self.client.put('/api/v1/auth/me/', {**PRIVILEGED, 'bio': 'hello'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['is_staff'], False)
        self.assert_unchanged(before, 'PUT /auth/me/ json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, 'hello')                    # the honest field did save

    def test_profile_put_multipart_ignores_every_privileged_field(self):
        before = snapshot(self.user)
        flat = {k: (v if not isinstance(v, (list, bool)) else str(v).lower()) for k, v in PRIVILEGED.items()}
        response = self.client.put('/api/v1/auth/me/', {**flat, 'bio': 'multi'}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_unchanged(before, 'PUT /auth/me/ multipart')

    def test_profile_patch_is_not_a_second_write_path(self):
        before = snapshot(self.user)
        response = self.client.patch('/api/v1/auth/me/', PRIVILEGED, format='json')
        self.assertEqual(response.status_code, 405)
        self.assert_unchanged(before, 'PATCH /auth/me/')

    def test_settings_patch_rejects_privileged_keys(self):
        before = snapshot(self.user)
        for key, value in PRIVILEGED.items():
            response = self.client.patch('/api/v1/auth/settings/', {key: value}, format='json')
            self.assertEqual(response.status_code, 400, key)
        nested = {'privacy': {'portfolio_public': False, 'is_staff': True},
                  'notifications': {'payments': True, 'is_superuser': True}}
        self.assertEqual(self.client.patch('/api/v1/auth/settings/', nested, format='json').status_code, 400)
        self.assert_unchanged(before, 'PATCH /auth/settings/')

    def test_change_password_ignores_privileged_fields(self):
        response = self.client.put('/api/v1/auth/change-password/', {
            **PRIVILEGED, 'old_password': PASSWORD, 'new_password': 'Another-Pass-5531!',
            'new_password2': 'Another-Pass-5531!'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual((self.user.is_staff, self.user.is_superuser, self.user.is_active, self.user.is_active_plan,
                          self.user.email), (False, False, True, False, 'privuser@kyapture.com'))
        self.assertTrue(self.user.check_password('Another-Pass-5531!'))   # only the password moved

    def test_register_ignores_privileged_fields(self):
        client = APIClient()
        response = client.post('/api/v1/auth/register/', {
            **PRIVILEGED, 'email': 'fresh7a@kyapture.com', 'username': 'fresh7a', 'display_name': 'Fresh',
            'password': PASSWORD, 'password2': PASSWORD, 'is_active': True}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email='fresh7a@kyapture.com')
        self.assertEqual((user.is_staff, user.is_superuser, user.is_active, user.is_active_plan),
                         (False, False, True, False))
        self.assertEqual((user.groups.count(), user.user_permissions.count()), (0, 0))
        self.assertFalse(UserSubscription.objects.filter(user=user).exists())
        self.assertNotEqual(str(user.id), PRIVILEGED['id'])

    def test_gallery_create_and_update_cannot_change_owner_or_account(self):
        other = self.make_user('privother')
        before = snapshot(self.user)
        created = self.client.post('/api/v1/galleries/', {
            'title': 'Mine', 'photographer': str(other.id), 'photographer_id': str(other.id), **PRIVILEGED,
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        gallery = Gallery.objects.get(title='Mine')
        self.assertEqual(gallery.photographer_id, self.user.id)
        self.client.patch(f'/api/v1/galleries/{gallery.slug}/', {'photographer': str(other.id), **PRIVILEGED}, format='json')
        gallery.refresh_from_db()
        self.assertEqual(gallery.photographer_id, self.user.id)
        self.assert_unchanged(before, 'gallery create/update')


class FeedbackTenancyTests(Base):
    def setUp(self):
        super().setUp()
        self.other = self.make_user('fbvictim')
        self.staff = self.make_user('fbstaff', is_staff=True)
        self.victim_row = Feedback.objects.create(user=self.other, category='bug', subject='secret', message='mine only')
        self.own_row = Feedback.objects.create(user=self.user, category='bug', subject='own', message='hello')

    def test_mine_lists_only_the_callers_rows(self):
        data = self.client.get('/api/v1/feedback/mine/').data
        self.assertEqual([r['id'] for r in data['results']], [str(self.own_row.id)])
        self.assertNotIn('secret', repr(data))

    def test_mine_ignores_user_and_id_filters(self):
        data = self.client.get('/api/v1/feedback/mine/', {'user': str(self.other.id), 'id': str(self.victim_row.id)}).data
        self.assertEqual([r['id'] for r in data['results']], [str(self.own_row.id)])

    def test_a_normal_user_cannot_read_or_change_another_users_feedback(self):
        url = f'/api/v1/feedback/inbox/{self.victim_row.id}/'
        self.assertEqual(self.client.get('/api/v1/feedback/inbox/').status_code, 403)
        self.assertEqual(self.client.patch(url, {'status': 'resolved'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 403)
        # the same answer for an id that does not exist: the inbox confirms nothing
        self.assertEqual(self.client.patch(f'/api/v1/feedback/inbox/{uuid.uuid4()}/', {'status': 'resolved'},
                                           format='json').status_code, 403)
        self.victim_row.refresh_from_db()
        self.assertEqual(self.victim_row.status, 'new')

    def test_anonymous_gets_401_everywhere(self):
        anon = APIClient()
        for method, url in (('get', '/api/v1/feedback/mine/'), ('get', '/api/v1/feedback/inbox/'),
                            ('patch', f'/api/v1/feedback/inbox/{self.victim_row.id}/'), ('post', '/api/v1/feedback/')):
            self.assertEqual(getattr(anon, method)(url, {}, format='json').status_code, 401, url)

    def test_the_submit_cannot_write_on_behalf_of_another_user(self):
        response = self.client.post('/api/v1/feedback/', {
            'category': 'bug', 'message': 'x', 'user': str(self.other.id), 'user_id': str(self.other.id),
            'status': 'resolved', 'id': str(self.victim_row.id)}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        row = Feedback.objects.get(pk=response.data['id'])
        self.assertEqual((row.user_id, row.status), (self.user.id, 'new'))
        self.assertNotEqual(row.pk, self.victim_row.pk)

    def test_staff_patch_changes_status_only_and_404s_unknown_ids(self):
        staff = APIClient()
        staff.force_authenticate(self.staff)
        url = f'/api/v1/feedback/inbox/{self.victim_row.id}/'
        self.assertEqual(staff.patch(url, {'status': 'reviewed', 'user': str(self.user.id)}, format='json').status_code, 400)
        self.assertEqual(staff.patch(url, {'status': 'reviewed'}, format='json').status_code, 200)
        self.assertEqual(staff.patch(f'/api/v1/feedback/inbox/{uuid.uuid4()}/', {'status': 'reviewed'},
                                     format='json').status_code, 404)
        self.assertEqual(staff.delete(url).status_code, 405)
        self.victim_row.refresh_from_db()
        self.assertEqual((self.victim_row.status, self.victim_row.user_id), ('reviewed', self.other.id))


class StaffBoundaryTests(Base):
    def test_a_normal_user_reaches_no_staff_endpoint(self):
        payment = uuid.uuid4()
        for method, url, body in (
            ('get', '/api/v1/feedback/inbox/', {}),
            ('patch', f'/api/v1/feedback/inbox/{uuid.uuid4()}/', {'status': 'resolved'}),
            ('get', '/api/v1/staff/payments/', {}),
            ('post', f'/api/v1/staff/payments/{payment}/approve/', {}),
            ('post', f'/api/v1/staff/payments/{payment}/reject/', {'reason': 'x'}),
            ('post', f'/api/v1/staff/payments/{payment}/proof-link/', {}),
            ('get', f'/api/v1/staff/payments/{payment}/proof/', {}),
        ):
            self.assertEqual(getattr(self.client, method)(url, body, format='json').status_code, 403, url)

    def test_a_normal_user_session_cannot_open_django_admin(self):
        from django.test import Client
        browser = Client()
        browser.force_login(self.user)
        response = browser.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])
        self.assertEqual(browser.get('/admin/users/user/').status_code, 302)

    def test_staff_has_no_ownership_of_another_photographers_gallery(self):
        owner = self.make_user('stowner')
        gallery = Gallery.objects.create(photographer=owner, title='Private', slug='private-7a', is_active=True)
        staff = APIClient()
        staff.force_authenticate(self.make_user('stadmin', is_staff=True, is_superuser=True))
        self.assertEqual(staff.get(f'/api/v1/galleries/{gallery.slug}/').status_code, 404)
        self.assertEqual(staff.delete(f'/api/v1/galleries/{gallery.slug}/').status_code, 404)
        self.assertEqual(staff.get(f'/api/v1/photos/{gallery.slug}/').status_code, 404)
        self.assertTrue(Gallery.objects.filter(pk=gallery.pk).exists())


class DeactivatedTokensTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email='deact@kyapture.com', password=PASSWORD, username='deact7a')
        self.refresh = RefreshToken.for_user(self.user)
        self.access = str(self.refresh.access_token)

    def deactivate(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)

    def test_tokens_work_while_active(self):
        self.assertEqual(self.client.get('/api/v1/auth/me/', HTTP_AUTHORIZATION=f'Bearer {self.access}').status_code, 200)

    def test_bearer_access_token_stops_at_once(self):
        self.deactivate()
        self.assertEqual(self.client.get('/api/v1/auth/me/', HTTP_AUTHORIZATION=f'Bearer {self.access}').status_code, 401)

    def test_cookie_access_token_stops_at_once(self):
        self.deactivate()
        self.client.cookies['access_token'] = self.access
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 401)
        self.assertEqual(self.client.get('/api/v1/galleries/').status_code, 401)

    def test_refresh_token_cannot_mint_a_new_session(self):
        self.deactivate()
        self.client.cookies['refresh_token'] = str(self.refresh)
        response = self.client.post('/api/v1/auth/token/refresh/')
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('access_token', response.cookies)

    def test_login_is_refused(self):
        self.deactivate()
        response = self.client.post('/api/v1/auth/login/', {'email': 'deact@kyapture.com', 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('access_token', response.cookies)
