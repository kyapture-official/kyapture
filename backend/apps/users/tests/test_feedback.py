# backend/apps/users/tests/test_feedback.py
"""
Chunk 6.3-A — feedback submit, "my feedback", staff inbox + status PATCH, and the
staff bell notification. No attachments, no email, no websocket.
"""
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.users.feedback_api import FeedbackRateThrottle, browser_class, clean_route
from apps.users.models import Feedback, Notification

User = get_user_model()

URL = '/api/v1/feedback/'
MINE = '/api/v1/feedback/mine/'
INBOX = '/api/v1/feedback/inbox/'
CHROME_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
PASSWORD = 'Sturdy-Pass-8842!'


def payload(**over):
    body = {'category': 'bug', 'subject': 'Upload stuck', 'message': 'The progress bar never finishes.'}
    body.update(over)
    return body


class FeedbackBase(APITestCase):
    def make_user(self, name, **extra):
        return User.objects.create_user(email=f'{name}@kyapture.com', password=PASSWORD, username=name, **extra)

    def setUp(self):
        cache.clear()
        self.user = self.make_user('fbuser')
        self.other = self.make_user('fbother')
        self.staff = self.make_user('fbstaff', is_staff=True)
        self.client.force_authenticate(user=self.user)

    def submit(self, **over):
        return self.client.post(URL, payload(**over), format='json')

    def submit_fresh(self, **over):
        """Submit with a clean throttle: every attempt, valid or not, counts toward the per-user limit."""
        cache.clear()
        return self.submit(**over)

    def as_user(self, user):
        self.client.force_authenticate(user=user)


class SubmitTests(FeedbackBase):
    def test_submit_creates_a_row_owned_by_the_caller(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.data)
        row = Feedback.objects.get()
        self.assertEqual(row.user, self.user)
        self.assertEqual((row.category, row.subject, row.status), ('bug', 'Upload stuck', 'new'))
        self.assertEqual(response.data['id'], str(row.pk))
        self.assertEqual(response.data['status'], 'new')

    def test_anonymous_cannot_submit(self):
        self.client.force_authenticate(user=None)
        response = self.submit()
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(Feedback.objects.count(), 0)

    def test_response_never_exposes_the_user_or_internal_fields(self):
        data = self.submit().data
        for field in ('user', 'user_email', 'browser_class', 'app_version'):
            self.assertNotIn(field, data)

    def test_extra_and_privileged_fields_are_ignored(self):
        response = self.submit(
            status='resolved', user=str(self.other.pk), id='00000000-0000-0000-0000-000000000001',
            browser_class='firefox', created_at='2001-01-01T00:00:00Z', is_staff=True, attachment='x.png',
        )
        self.assertEqual(response.status_code, 201, response.data)
        row = Feedback.objects.get()
        self.assertEqual(row.status, 'new')
        self.assertEqual(row.user, self.user)
        self.assertNotEqual(str(row.pk), '00000000-0000-0000-0000-000000000001')
        self.assertEqual(row.browser_class, 'other')          # from the User-Agent header, never the body
        self.assertEqual(row.created_at.year, row.updated_at.year)
        self.assertGreater(row.created_at.year, 2020)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)


class ValidationTests(FeedbackBase):
    def test_every_allowlisted_category_is_accepted(self):
        for value in ('bug', 'feature_request', 'design', 'performance', 'download', 'upload', 'security_privacy', 'other'):
            cache.clear()
            self.assertEqual(self.submit(category=value).status_code, 201, value)
        self.assertEqual(Feedback.objects.count(), 8)

    def test_category_outside_the_allowlist_is_refused(self):
        for bad in ('praise', 'BUG', '', None, 5, ['bug'], {'a': 1}, 'bug; drop table'):
            response = self.submit_fresh(category=bad)
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn('category', response.data['details'])
        self.assertEqual(Feedback.objects.count(), 0)

    def test_missing_category_or_message_is_refused(self):
        for missing in ('category', 'message'):
            body = payload()
            del body[missing]
            response = self.client.post(URL, body, format='json')
            self.assertEqual(response.status_code, 400, missing)
            self.assertIn(missing, response.data['details'])

    def test_empty_or_whitespace_message_is_refused(self):
        for bad in ('', '   ', '\n\t  \n'):
            self.assertEqual(self.submit_fresh(message=bad).status_code, 400, bad)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_subject_is_optional(self):
        body = payload()
        del body['subject']
        self.assertEqual(self.client.post(URL, body, format='json').status_code, 201)
        self.assertEqual(self.submit_fresh(subject='   ').status_code, 201)
        self.assertEqual(list(Feedback.objects.values_list('subject', flat=True)), ['', ''])
        notes = Notification.objects.filter(user=self.staff, kind='feedback')
        self.assertEqual({n.message for n in notes}, {'New bug feedback'})          # no dangling colon

    def test_text_is_trimmed_and_subject_is_one_line(self):
        self.submit(subject='  Slow\n  gallery\t load  ', message='\n  hello there  \n')
        row = Feedback.objects.get()
        self.assertEqual(row.subject, 'Slow gallery load')
        self.assertEqual(row.message, 'hello there')

    def test_length_caps(self):
        self.assertEqual(self.submit_fresh(subject='s' * 121).status_code, 400)
        self.assertEqual(self.submit_fresh(message='m' * 4001).status_code, 400)
        self.assertEqual(self.submit_fresh(subject='s' * 120, message='m' * 4000).status_code, 201)

    def test_null_byte_is_refused_not_a_500(self):
        self.assertEqual(self.submit(message='a\x00b').status_code, 400)

    def test_non_json_body_types_do_not_crash(self):
        for body in ('[]', '"x"', '5'):
            response = self.client.post(URL, data=body, content_type='application/json')
            self.assertEqual(response.status_code, 400, body)


class ContextCaptureTests(FeedbackBase):
    def test_route_loses_query_string_and_fragment(self):
        self.submit(route='/g/aster/wedding?token=SECRET&pin=1234#access=SECRET2')
        self.assertEqual(Feedback.objects.get().route, '/g/aster/wedding')

    def test_full_url_is_reduced_to_its_path(self):
        self.submit(route='https://evil.example/dashboard/galleries?sig=abc#frag')
        self.assertEqual(Feedback.objects.get().route, '/dashboard/galleries')

    def test_id_and_token_segments_are_masked(self):
        uuid = '0190e5b0-5c1d-7a3e-8f20-1234567890ab'
        self.assertEqual(clean_route(f'/dashboard/galleries/{uuid}/design'), '/dashboard/galleries/:id/design')
        self.assertEqual(clean_route('/auth/password/reset/confirm/MQ/cx7k2p-1a2b3c4d5e6f7a8b9c0d'),
                         '/auth/password/reset/confirm/MQ/:token')
        self.assertEqual(clean_route('/x/' + 'A' * 40), '/x/:token')

    def test_unusable_route_is_discarded(self):
        for bad in ('not a path', 'javascript:alert(1)', '/a b', '/<script>', None, 5, ['/x'], {'a': 1}):
            self.assertEqual(clean_route(bad), '', bad)

    def test_route_is_capped(self):
        self.submit(route='/' + 'a' * 500)
        self.assertLessEqual(len(Feedback.objects.get().route), Feedback.ROUTE_MAX)

    def test_gallery_slug_is_kept_only_when_slug_shaped(self):
        self.submit(gallery_slug='  summer-2026_set ')
        self.assertEqual(Feedback.objects.get().gallery_slug, 'summer-2026_set')
        cache.clear()
        for bad in ('<b>x</b>', 'a b', 'x' * 226, 5, ['a']):
            Feedback.objects.all().delete()
            cache.clear()
            self.assertEqual(self.submit(gallery_slug=bad).status_code, 201)
            self.assertEqual(Feedback.objects.get().gallery_slug, '', bad)

    def test_app_version_is_allowlisted(self):
        with override_settings(APP_VERSION='1.4.0', FEEDBACK_ACCEPTED_APP_VERSIONS=['1.3.9']):
            self.submit(app_version='1.4.0')
            cache.clear()
            self.submit(app_version='1.3.9')
            cache.clear()
            self.submit(app_version='<img src=x onerror=alert(1)>')
            cache.clear()
            self.submit()
        versions = list(Feedback.objects.order_by('created_at').values_list('app_version', flat=True))
        self.assertEqual(versions, ['1.4.0', '1.3.9', 'unknown', 'unknown'])

    def test_browser_class_comes_from_the_user_agent_allowlist(self):
        self.client.post(URL, payload(), format='json', HTTP_USER_AGENT=CHROME_UA)
        self.assertEqual(Feedback.objects.get().browser_class, 'chrome')
        cases = {
            CHROME_UA + ' Edg/126.0.0.0': 'edge',
            'Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0': 'firefox',
            'Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15': 'safari',
            CHROME_UA + ' OPR/111.0.0.0': 'opera',
            'curl/8.0 <script>alert(1)</script>': 'other',
            '': 'other',
        }
        for ua, expected in cases.items():
            self.assertEqual(browser_class(ua), expected, ua)
        self.assertTrue(set(Feedback.Browser.values) >= set(cases.values()))

    def test_no_secret_headers_or_cookies_are_stored(self):
        self.client.cookies['access_token'] = 'COOKIE-TOKEN-VALUE'
        self.client.post(
            URL, payload(route='/g/a/b?download_token=DLTOKEN'), format='json',
            HTTP_AUTHORIZATION='Bearer BEARER-VALUE', HTTP_USER_AGENT=CHROME_UA,
        )
        row = Feedback.objects.get()
        stored = ' '.join(str(getattr(row, f.name)) for f in Feedback._meta.fields)
        for secret in ('COOKIE-TOKEN-VALUE', 'BEARER-VALUE', 'DLTOKEN'):
            self.assertNotIn(secret, stored)

    def test_model_has_no_file_field(self):
        from django.db.models import FileField
        self.assertFalse([f for f in Feedback._meta.get_fields() if isinstance(f, FileField)])


class ThrottleTests(FeedbackBase):
    def test_rate_lives_in_settings(self):
        self.assertEqual(
            FeedbackRateThrottle().get_rate(), settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['feedback']
        )

    def test_sixth_post_in_the_window_is_throttled(self):
        for i in range(5):
            self.assertEqual(self.submit(subject=f'n{i}').status_code, 201, i)
        response = self.submit(subject='n6')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(Feedback.objects.count(), 5)

    def test_throttle_is_per_user_not_shared(self):
        for _ in range(5):
            self.submit()
        self.assertEqual(self.submit().status_code, 429)
        self.as_user(self.other)
        self.assertEqual(self.submit().status_code, 201)

    def test_changing_ip_or_forwarded_for_does_not_reset_the_limit(self):
        for i in range(5):
            self.client.post(URL, payload(), format='json', REMOTE_ADDR=f'10.0.0.{i}', HTTP_X_FORWARDED_FOR=f'203.0.113.{i}')
        response = self.client.post(URL, payload(), format='json', REMOTE_ADDR='198.51.100.9', HTTP_X_FORWARDED_FOR='192.0.2.77')
        self.assertEqual(response.status_code, 429)

    def test_two_users_on_one_ip_do_not_share_a_bucket(self):
        for _ in range(5):
            self.client.post(URL, payload(), format='json', REMOTE_ADDR='10.1.1.1')
        self.as_user(self.other)
        self.assertEqual(self.client.post(URL, payload(), format='json', REMOTE_ADDR='10.1.1.1').status_code, 201)

    def test_cache_key_is_the_user_id_and_never_the_ip(self):
        class FakeRequest:
            user = self.user
            META = {'REMOTE_ADDR': '1.2.3.4', 'HTTP_X_FORWARDED_FOR': '5.6.7.8'}

        key = FeedbackRateThrottle().get_cache_key(FakeRequest(), None)
        self.assertIn(str(self.user.pk), key)
        self.assertNotIn('1.2.3.4', key)
        self.assertNotIn('5.6.7.8', key)


class MyFeedbackTests(FeedbackBase):
    def test_lists_only_own_submissions_newest_first(self):
        self.submit(subject='first')
        self.submit(subject='second')
        Feedback.objects.create(user=self.other, category='bug', subject='theirs', message='private')
        data = self.client.get(MINE).data
        self.assertEqual([r['subject'] for r in data['results']], ['second', 'first'])
        self.assertEqual(data['count'], 2)

    def test_no_cross_user_read(self):
        theirs = Feedback.objects.create(user=self.other, category='bug', subject='theirs', message='private note')
        body = self.client.get(MINE).content.decode()
        self.assertNotIn('private note', body)
        self.assertNotIn(str(theirs.pk), body)

    def test_my_feedback_hides_staff_only_fields(self):
        self.submit()
        row = self.client.get(MINE).data['results'][0]
        for field in ('user_email', 'username', 'browser_class', 'app_version'):
            self.assertNotIn(field, row)

    def test_mine_requires_login(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(MINE).status_code, (401, 403))

    def test_owner_cannot_patch_status_on_their_own_row(self):
        row = Feedback.objects.create(user=self.user, category='bug', subject='s', message='m')
        response = self.client.patch(f'{INBOX}{row.pk}/', {'status': 'resolved'}, format='json')
        self.assertEqual(response.status_code, 403)
        row.refresh_from_db()
        self.assertEqual(row.status, 'new')


class StaffInboxTests(FeedbackBase):
    def setUp(self):
        super().setUp()
        self.rows = [
            Feedback.objects.create(user=self.user, category='bug', subject='a', message='m1'),
            Feedback.objects.create(user=self.other, category='design', subject='b', message='m2', status='reviewed'),
            Feedback.objects.create(user=self.user, category='bug', subject='c', message='m3', status='resolved'),
        ]
        self.as_user(self.staff)

    def test_normal_user_gets_403_on_list_and_patch(self):
        self.as_user(self.user)
        self.assertEqual(self.client.get(INBOX).status_code, 403)
        self.assertEqual(self.client.patch(f'{INBOX}{self.rows[0].pk}/', {'status': 'resolved'}, format='json').status_code, 403)
        self.rows[0].refresh_from_db()
        self.assertEqual(self.rows[0].status, 'new')

    def test_anonymous_is_refused(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(INBOX).status_code, (401, 403))
        self.assertIn(self.client.patch(f'{INBOX}{self.rows[0].pk}/', {'status': 'resolved'}, format='json').status_code, (401, 403))

    def test_superuser_without_is_staff_is_not_the_staff_role(self):
        sup = self.make_user('supernostaff', is_superuser=True)
        self.as_user(sup)
        self.assertEqual(self.client.get(INBOX).status_code, 403)

    def test_inactive_staff_is_refused(self):
        self.staff.is_active = False
        self.staff.save()
        self.as_user(self.staff)
        self.assertEqual(self.client.get(INBOX).status_code, 403)

    def test_staff_sees_everyones_feedback_newest_first_paginated(self):
        data = self.client.get(INBOX).data
        self.assertEqual([r['subject'] for r in data['results']], ['c', 'b', 'a'])
        self.assertEqual(data['count'], 3)
        self.assertEqual(data['results'][1]['user_email'], 'fbother@kyapture.com')
        page = self.client.get(INBOX, {'page_size': 2}).data
        self.assertEqual(len(page['results']), 2)
        self.assertIsNotNone(page['next'])
        self.assertEqual(len(self.client.get(INBOX, {'page_size': 2, 'page': 2}).data['results']), 1)

    def test_filters_by_status_and_category(self):
        self.assertEqual([r['subject'] for r in self.client.get(INBOX, {'status': 'reviewed'}).data['results']], ['b'])
        self.assertEqual(self.client.get(INBOX, {'category': 'bug'}).data['count'], 2)
        both = self.client.get(INBOX, {'category': 'bug', 'status': 'resolved'}).data
        self.assertEqual([r['subject'] for r in both['results']], ['c'])

    def test_invalid_filter_value_is_400(self):
        self.assertEqual(self.client.get(INBOX, {'status': 'bogus'}).status_code, 400)
        self.assertEqual(self.client.get(INBOX, {'category': 'bogus'}).status_code, 400)

    def test_patch_changes_status_only_and_allows_each_value(self):
        row = self.rows[0]
        for value in ('reviewed', 'in_progress', 'resolved', 'dismissed', 'new'):
            response = self.client.patch(f'{INBOX}{row.pk}/', {'status': value}, format='json')
            self.assertEqual(response.status_code, 200, value)
            self.assertEqual(response.data['status'], value)
            row.refresh_from_db()
            self.assertEqual(row.status, value)

    def test_patch_rejects_unknown_status(self):
        for bad in ('done', '', None, 3, 'RESOLVED'):
            response = self.client.patch(f'{INBOX}{self.rows[0].pk}/', {'status': bad}, format='json')
            self.assertEqual(response.status_code, 400, bad)
        self.rows[0].refresh_from_db()
        self.assertEqual(self.rows[0].status, 'new')

    def test_patch_cannot_change_anything_else(self):
        row = self.rows[0]
        for field, value in (('message', 'edited'), ('subject', 'edited'), ('category', 'other'),
                             ('user', str(self.other.pk)), ('route', '/x'), ('created_at', '2001-01-01T00:00:00Z')):
            response = self.client.patch(f'{INBOX}{row.pk}/', {'status': 'reviewed', field: value}, format='json')
            self.assertEqual(response.status_code, 400, field)
            self.assertEqual(response.data['code'], 'read_only_fields')
        row.refresh_from_db()
        self.assertEqual((row.message, row.subject, row.category, row.user, row.route, row.status),
                         ('m1', 'a', 'bug', self.user, '', 'new'))
        self.assertEqual(self.client.patch(f'{INBOX}{row.pk}/', {}, format='json').status_code, 400)

    def test_patch_unknown_id_is_404(self):
        self.assertEqual(self.client.patch(f'{INBOX}00000000-0000-0000-0000-000000000009/', {'status': 'new'}, format='json').status_code, 404)

    def test_inbox_has_no_write_or_delete_verbs(self):
        self.assertEqual(self.client.post(INBOX, payload(), format='json').status_code, 405)
        self.assertEqual(self.client.delete(f'{INBOX}{self.rows[0].pk}/').status_code, 405)
        self.assertEqual(self.client.put(f'{INBOX}{self.rows[0].pk}/', {'status': 'new'}, format='json').status_code, 405)


class StaffFlagTests(FeedbackBase):
    """The UI offers the inbox only when /auth/me/ says is_staff; the inbox endpoints still enforce it."""
    ME = '/api/v1/auth/me/'

    def test_me_reports_is_staff_for_staff_and_not_for_others(self):
        self.assertIs(self.client.get(self.ME).data['is_staff'], False)
        self.as_user(self.staff)
        self.assertIs(self.client.get(self.ME).data['is_staff'], True)

    def test_profile_update_cannot_grant_is_staff(self):
        self.client.put(self.ME, {'display_name': 'Me', 'is_staff': True}, format='json')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertIs(self.client.get(self.ME).data['is_staff'], False)


class XssSafetyTests(FeedbackBase):
    PAYLOAD = '<script>alert(1)</script><img src=x onerror=alert(2)>"\'&amp;'

    def test_text_is_stored_verbatim_as_plain_text_and_returned_as_json(self):
        response = self.submit(subject=self.PAYLOAD[:120], message=self.PAYLOAD)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Feedback.objects.get().message, self.PAYLOAD)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json()['message'], self.PAYLOAD)           # as is, never HTML-escaped or marked safe
        self.assertEqual(self.client.get(MINE).json()['results'][0]['message'], self.PAYLOAD)

    def test_inbox_returns_it_as_json_never_html(self):
        self.submit(message=self.PAYLOAD)
        self.as_user(self.staff)
        response = self.client.get(INBOX)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json()['results'][0]['message'], self.PAYLOAD)
        self.assertNotEqual(response.get('X-Content-Type-Options', 'nosniff'), '')

    def test_markup_in_subject_does_not_reach_the_notification_as_html(self):
        self.submit(subject='<b>hi</b>')
        note = Notification.objects.get(user=self.staff)
        self.assertIn('<b>hi</b>', note.message)                              # plain text; the bell renders escaped
        self.assertLessEqual(len(note.message), 300)


class StaffNotificationTests(FeedbackBase):
    def test_new_feedback_notifies_every_active_staff_account(self):
        staff2 = self.make_user('fbstaff2', is_staff=True)
        gone = self.make_user('fbstaffgone', is_staff=True, is_active=False)
        self.submit(category='download', subject='ZIP fails')
        notes = Notification.objects.filter(kind='feedback')
        self.assertEqual({n.user_id for n in notes}, {self.staff.pk, staff2.pk})
        self.assertFalse(Notification.objects.filter(user=gone).exists())
        note = notes.get(user=self.staff)
        self.assertEqual(note.message, 'New download feedback: ZIP fails')
        self.assertFalse(note.is_read)
        self.assertIsNone(note.gallery)

    def test_regular_users_get_no_notification(self):
        self.submit()
        self.assertFalse(Notification.objects.filter(user__in=[self.user, self.other]).exists())

    def test_staff_sees_it_in_the_existing_bell_endpoint_with_a_link(self):
        self.submit()
        self.as_user(self.staff)
        data = self.client.get('/api/v1/notifications/').data
        self.assertEqual(data['unread_count'], 1)
        self.assertEqual(data['results'][0]['kind'], 'feedback')
        self.assertEqual(data['results'][0]['link'], '/dashboard/feedback')

    def test_each_feedback_is_its_own_notification(self):
        self.submit(subject='one')
        self.submit(subject='two')
        self.assertEqual(Notification.objects.filter(user=self.staff, kind='feedback').count(), 2)

    def test_refused_submission_creates_no_notification(self):
        self.submit(category='nope')
        self.assertFalse(Notification.objects.exists())

    def test_no_email_is_sent(self):
        self.submit()
        self.assertEqual(len(mail.outbox), 0)
