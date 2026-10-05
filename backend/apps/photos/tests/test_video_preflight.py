"""
Chunk VID-C: POST /api/v1/photos/video-preflight/ answers "would these videos
fit my plan?" BEFORE the browser uploads anything. It must give exactly the
refusal the upload gives (one rule: video_quota_violation) and read the plan
table at request time. The upload keeps its own authoritative check.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.photos.serializers import MAX_PREFLIGHT_SECONDS, MAX_PREFLIGHT_VIDEOS
from apps.photos.tests.test_video_pipeline import _video_upload_file
from apps.subscriptions.models import SubscriptionPlan
from apps.subscriptions.testing import grant_plan

User = get_user_model()
URL = '/api/v1/photos/video-preflight/'


class VideoPreflightTests(APITestCase):
    def setUp(self):
        cache.clear()                      # the throttle counts live in the cache
        self.user = User.objects.create_user(
            email='preflight@kyapture.com', password='SecurePassword123!', username='preflight')
        self.gallery = Gallery.objects.create(photographer=self.user, title='Pre', slug='pre-flight')
        self.client.force_authenticate(user=self.user)

    # ── helpers ──
    def ask(self, durations, count=None):
        body = {'durations': durations, 'video_count': len(durations) if count is None else count}
        return self.client.post(URL, body, format='json')

    def set_plan(self, name, minutes):
        plan = grant_plan(self.user, name=name)
        plan.video_minutes = minutes
        plan.save(update_fields=['video_minutes'])
        return plan

    def existing_video(self, seconds, user=None, slug=None):
        gallery = self.gallery if slug is None else Gallery.objects.create(
            photographer=user, title=slug, slug=slug)
        return MediaAsset.objects.create(
            gallery=gallery, media_type=MediaAsset.MediaType.VIDEO,
            original_file=SimpleUploadedFile('old.mp4', b'x', content_type='video/mp4'),
            original_name='old.mp4', file_size=1, duration=seconds, order=Decimal('1.0'),
            processing_status=MediaAsset.ProcessingStatus.READY,
        )

    def admin_save_video_minutes(self, plan, minutes):
        """A real submit of the Django admin change form (not an ORM shortcut)."""
        if not hasattr(self, 'admin_client'):
            self.admin_client = self.client_class()
            self.admin_client.force_login(User.objects.create_user(
                email='preflight-boss@kyapture.com', password='SecurePassword123!', username='pfboss',
                is_staff=True, is_superuser=True))
        admin_client = self.admin_client
        data = {
            'name': plan.name, 'price': str(plan.price), 'is_active': 'on', 'storage_gb': plan.storage_gb,
            'max_collections': '' if plan.max_collections is None else plan.max_collections,
            'video_minutes': minutes,
        }
        for flag in ('original_download', 'watermark', 'branding'):
            if getattr(plan, flag):
                data[flag] = 'on'
        response = admin_client.post(f'/admin/subscriptions/subscriptionplan/{plan.pk}/change/', data)
        self.assertEqual(response.status_code, 302)

    # ── access ──
    def test_unauthenticated_is_refused(self):
        self.client.force_authenticate(user=None)
        response = self.ask([30])
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertNotIn('allowed', response.data)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_only_the_callers_own_videos_count(self):
        self.set_plan('Pro', 1)
        other = User.objects.create_user(
            email='pf-other@kyapture.com', password='SecurePassword123!', username='pfother')
        self.existing_video(60, user=other, slug='others-gallery')      # someone else's full minute
        self.assertEqual(self.ask([60]).status_code, status.HTTP_200_OK)

    # ── the plan rule ──
    def test_free_plan_is_refused_as_not_in_plan(self):
        self.assertEqual(SubscriptionPlan.get_free().video_minutes, 0)
        response = self.ask([30])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'video_not_in_plan')
        self.assertEqual(response.data['plan_limit_minutes'], 0)
        self.assertEqual(response.data['used_minutes'], 0)

    def test_pro_under_the_limit_is_allowed(self):
        self.set_plan('Pro', 60)
        response = self.ask([600, 300])
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'allowed': True})

    def test_over_the_limit_is_refused_with_all_the_figures(self):
        self.set_plan('Pro', 1)
        self.existing_video(30)
        response = self.ask([20, 20])                       # 30 + 40 = 70 s > 60 s
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'video_minutes_exceeded')
        self.assertEqual(response.data['plan_limit_minutes'], 1)
        self.assertEqual(response.data['used_minutes'], 0.5)
        self.assertEqual(response.data['upload_minutes'], 0.7)

    def test_exact_boundary_is_allowed_and_a_hair_more_is_refused(self):
        self.set_plan('Pro', 1)
        self.existing_video(30)
        self.assertEqual(self.ask([30]).status_code, status.HTTP_200_OK)          # 60 s == 1 min
        self.assertEqual(self.ask([30.5]).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.ask([15, 15]).status_code, status.HTTP_200_OK)      # the batch is summed
        self.assertEqual(self.ask([15, 15.5]).status_code, status.HTTP_403_FORBIDDEN)

    def test_a_video_whose_length_the_browser_could_not_read_is_counted_not_measured(self):
        self.assertEqual(self.ask([], count=2).data['code'], 'video_not_in_plan')   # Free: refused on count alone
        self.set_plan('Pro', 1)
        self.assertEqual(self.ask([], count=2).status_code, status.HTTP_200_OK)     # nothing to add up: the upload decides
        self.assertEqual(self.ask([61], count=2).status_code, status.HTTP_403_FORBIDDEN)

    def test_unlimited_plan_allows_any_length(self):
        self.set_plan('Studio', None)
        self.assertEqual(self.ask([MAX_PREFLIGHT_SECONDS]).status_code, status.HTTP_200_OK)

    def test_staff_are_never_limited_like_the_upload(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.assertEqual(self.ask([3600]).status_code, status.HTTP_200_OK)

    def test_refusal_is_the_same_body_the_upload_gives(self):
        self.set_plan('Pro', 1)
        self.existing_video(59)
        refusal = self.ask([2])
        clip = _video_upload_file(name='clip.mp4', duration=2)
        upload = self.client.post(
            f'/api/v1/photos/{self.gallery.slug}/upload/', {'video': [clip]}, format='multipart')
        self.assertEqual(upload.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(refusal.data, upload.data)

    def test_the_upload_still_checks_for_itself_when_the_client_lied(self):
        self.set_plan('Pro', 1)
        self.existing_video(59)
        self.assertEqual(self.ask([1]).status_code, status.HTTP_200_OK)    # client claims 1 s...
        clip = _video_upload_file(name='long.mp4', duration=2)             # ...the file is 2 s
        upload = self.client.post(
            f'/api/v1/photos/{self.gallery.slug}/upload/', {'video': [clip]}, format='multipart')
        self.assertEqual(upload.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(upload.data['code'], 'video_minutes_exceeded')

    # ── admin edits apply with no restart ──
    def test_admin_changing_video_minutes_changes_the_answer_at_once(self):
        plan = self.set_plan('Pro', 1)
        self.assertEqual(self.ask([90]).status_code, status.HTTP_403_FORBIDDEN)
        self.admin_save_video_minutes(plan, 2)
        self.assertEqual(self.ask([90]).status_code, status.HTTP_200_OK)
        self.admin_save_video_minutes(plan, 0)
        self.assertEqual(self.ask([90]).data['code'], 'video_not_in_plan')
        self.admin_save_video_minutes(plan, '')                      # empty = unlimited
        self.assertEqual(self.ask([90]).status_code, status.HTTP_200_OK)

    # ── input validation ──
    def test_bad_input_is_a_400_and_never_an_allow(self):
        self.set_plan('Pro', 60)
        cases = {
            'no body': {},
            'no count': {'durations': [10]},
            'zero count': {'video_count': 0, 'durations': []},
            'negative count': {'video_count': -1, 'durations': []},
            'count too big': {'video_count': MAX_PREFLIGHT_VIDEOS + 1, 'durations': []},
            'count not a number': {'video_count': 'many', 'durations': []},
            'durations not a list': {'video_count': 1, 'durations': 'ten'},
            'zero duration': {'video_count': 1, 'durations': [0]},
            'negative duration': {'video_count': 1, 'durations': [-5]},
            'text duration': {'video_count': 1, 'durations': ['abc']},
            'null duration': {'video_count': 1, 'durations': [None]},
            'boolean duration': {'video_count': 1, 'durations': [True]},
            'huge duration': {'video_count': 1, 'durations': [MAX_PREFLIGHT_SECONDS + 1]},
            'more durations than videos': {'video_count': 1, 'durations': [5, 5]},
            'too many durations': {'video_count': MAX_PREFLIGHT_VIDEOS, 'durations': [1] * (MAX_PREFLIGHT_VIDEOS + 1)},
        }
        for label, body in cases.items():
            with self.subTest(label):
                response = self.client.post(URL, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['code'], 'invalid_preflight')

    def test_not_a_number_and_infinity_are_rejected(self):
        self.set_plan('Pro', 60)
        for raw in ('{"video_count": 1, "durations": [NaN]}', '{"video_count": 1, "durations": [Infinity]}',
                    '{"video_count": 1, "durations": ["nan"]}', '{"video_count": 1, "durations": ["inf"]}'):
            with self.subTest(raw):
                response = self.client.post(URL, raw, content_type='application/json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_the_largest_allowed_batch_is_accepted(self):
        self.set_plan('Studio', None)
        self.assertEqual(self.ask([1] * MAX_PREFLIGHT_VIDEOS).status_code, status.HTTP_200_OK)

    # ── rate limit ──
    def test_it_is_rate_limited_per_user(self):
        self.set_plan('Pro', 60)
        statuses = [self.ask([5]).status_code for _ in range(61)]
        self.assertEqual(statuses[:60], [status.HTTP_200_OK] * 60)
        self.assertEqual(statuses[60], status.HTTP_429_TOO_MANY_REQUESTS)
        other = User.objects.create_user(
            email='pf-second@kyapture.com', password='SecurePassword123!', username='pfsecond')
        self.client.force_authenticate(user=other)
        self.assertNotEqual(self.ask([5]).status_code, status.HTTP_429_TOO_MANY_REQUESTS)
