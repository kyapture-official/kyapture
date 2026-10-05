"""
Plan-based video minutes (chunk VID-A): SubscriptionPlan.video_minutes is
enforced at the upload endpoint. 0 = no video, empty = unlimited, N = minutes
across the account's live videos. Uses real ffmpeg clips (2 s) so the ffprobe
measurement at upload is exercised for real.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.photos.tests.test_video_pipeline import _video_upload_file
from apps.subscriptions.models import SubscriptionPlan
from apps.subscriptions.testing import grant_plan

User = get_user_model()
CLIP_SECONDS = 2


class VideoMinutesTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='vidmin@kyapture.com', password='SecurePassword123!', username='vidmin')
        self.gallery = Gallery.objects.create(photographer=self.user, title='Vid', slug='vid-minutes')
        self.url = f'/api/v1/photos/{self.gallery.slug}/upload/'
        self.client.force_authenticate(user=self.user)

    # ── helpers ──
    def set_plan(self, name, minutes):
        plan = grant_plan(self.user, name=name)
        plan.video_minutes = minutes
        plan.save(update_fields=['video_minutes'])
        return plan

    def existing_video(self, seconds):
        return MediaAsset.objects.create(
            gallery=self.gallery, media_type=MediaAsset.MediaType.VIDEO,
            original_file=SimpleUploadedFile('old.mp4', b'x', content_type='video/mp4'),
            original_name='old.mp4', file_size=1, duration=seconds, order=Decimal('1.0'),
            processing_status=MediaAsset.ProcessingStatus.READY,
        )

    def upload(self, name='clip.mp4'):
        video = _video_upload_file(name=name, duration=CLIP_SECONDS)
        with self.captureOnCommitCallbacks(execute=False):
            return self.client.post(self.url, {'video': [video]}, format='multipart')

    def video_count(self):
        return MediaAsset.objects.filter(media_type=MediaAsset.MediaType.VIDEO).count()

    # ── 0 = no video ──
    def test_free_user_is_refused_with_403_and_nothing_is_stored(self):
        free = SubscriptionPlan.get_free()
        self.assertEqual(free.video_minutes, 0)                       # seeded dummy value
        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'video_not_in_plan')
        self.assertEqual(response.data['plan_limit_minutes'], 0)
        self.assertEqual(response.data['used_minutes'], 0)
        self.assertEqual(self.video_count(), 0)

    def test_paid_plan_with_zero_video_minutes_is_refused(self):
        self.set_plan('Basic', 0)
        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'video_not_in_plan')
        self.assertEqual(self.video_count(), 0)

    def test_direct_api_call_by_a_free_user_is_403_even_with_images_mixed_in(self):
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.new('RGB', (20, 20), 'red').save(buf, 'JPEG')
        image = SimpleUploadedFile('a.jpg', buf.getvalue(), content_type='image/jpeg')
        video = _video_upload_file(duration=CLIP_SECONDS)
        response = self.client.post(self.url, {'image': [image], 'video': [video]}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(MediaAsset.objects.count(), 0)                # no partial batch

    # ── number = minutes ──
    def test_pro_under_limit_is_accepted_and_duration_is_stored(self):
        self.set_plan('Pro', 60)
        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        asset = MediaAsset.objects.get(media_type=MediaAsset.MediaType.VIDEO)
        self.assertEqual(asset.duration, CLIP_SECONDS)                 # measured by ffprobe at upload
        self.assertEqual(response.data[0]['duration'], CLIP_SECONDS)

    def test_over_the_limit_is_refused_with_limit_and_used_minutes(self):
        self.set_plan('Pro', 1)
        self.existing_video(59)                                        # 59 + 2 = 61 s > 60 s
        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'video_minutes_exceeded')
        self.assertEqual(response.data['plan_limit_minutes'], 1)
        self.assertEqual(response.data['used_minutes'], 1.0)
        self.assertEqual(self.video_count(), 1)                        # only the pre-existing one

    def test_exact_boundary_is_accepted_and_one_second_more_is_refused(self):
        self.set_plan('Pro', 1)
        self.existing_video(58)                                        # 58 + 2 = 60 s == 1 minute
        self.assertEqual(self.upload().status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(self.upload('again.mp4').status_code, status.HTTP_403_FORBIDDEN)

    def test_whole_batch_is_counted_not_each_file_alone(self):
        self.set_plan('Pro', 1)
        self.existing_video(57)                                        # one clip fits (59), two do not (61)
        clips = [_video_upload_file(name=f'c{i}.mp4', duration=CLIP_SECONDS) for i in range(2)]
        response = self.client.post(self.url, {'video': clips}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.video_count(), 1)

    def test_deleting_a_video_frees_minutes_at_once(self):
        self.set_plan('Pro', 1)
        full = self.existing_video(60)
        self.assertEqual(self.upload().status_code, status.HTTP_403_FORBIDDEN)
        with self.captureOnCommitCallbacks(execute=False):
            deleted = self.client.delete(f'/api/v1/photos/photo/{full.id}/')
        self.assertEqual(deleted.status_code, status.HTTP_200_OK)
        self.assertEqual(self.upload().status_code, status.HTTP_202_ACCEPTED)

    def test_images_do_not_count_toward_video_minutes(self):
        self.set_plan('Pro', 1)
        MediaAsset.objects.create(
            gallery=self.gallery, media_type=MediaAsset.MediaType.IMAGE,
            original_file=SimpleUploadedFile('p.jpg', b'x'), original_name='p.jpg',
            file_size=1, duration=9999, order=Decimal('1.0'))          # stray value must be ignored
        self.assertEqual(self.upload().status_code, status.HTTP_202_ACCEPTED)

    def test_empty_limit_means_unlimited(self):
        self.set_plan('Studio', None)
        self.existing_video(10 ** 6)
        self.assertEqual(self.upload().status_code, status.HTTP_202_ACCEPTED)

    # ── admin-editable, no restart ──
    def test_changing_video_minutes_in_the_plan_table_changes_behaviour_immediately(self):
        plan = self.set_plan('Pro', 0)
        self.assertEqual(self.upload().status_code, status.HTTP_403_FORBIDDEN)
        SubscriptionPlan.objects.filter(pk=plan.pk).update(video_minutes=5)   # what the admin form does
        self.assertEqual(self.upload().status_code, status.HTTP_202_ACCEPTED)
        SubscriptionPlan.objects.filter(pk=plan.pk).update(video_minutes=0)
        self.assertEqual(self.upload('two.mp4').status_code, status.HTTP_403_FORBIDDEN)

    def test_free_row_edited_in_admin_grants_video_to_unpaid_accounts(self):
        SubscriptionPlan.objects.filter(key='free').update(video_minutes=10)
        self.assertEqual(self.upload().status_code, status.HTTP_202_ACCEPTED)

    # ── input safety ──
    def test_unreadable_video_is_rejected_cleanly(self):
        self.set_plan('Pro', 60)
        junk = SimpleUploadedFile('bad.mp4', b'\x00\x00\x00\x18ftypmp42' + b'not a video' * 20, content_type='video/mp4')
        response = self.client.post(self.url, {'video': [junk]}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'video_unreadable')
        self.assertEqual(self.video_count(), 0)

    def test_wrong_extension_is_rejected_before_probing(self):
        self.set_plan('Pro', 60)
        response = self.client.post(
            self.url, {'video': [SimpleUploadedFile('x.exe', b'MZ', content_type='video/mp4')]}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'upload_validation_failed')


class VideoMinutesSurfaceTests(APITestCase):
    def test_seeded_dummy_values_are_in_the_plans_api(self):
        response = self.client.get('/api/v1/subscriptions/plans/')
        self.assertEqual({p['key']: p['video_minutes'] for p in response.data},
                         {'free': 0, 'basic': 0, 'pro': 60, 'studio': 120})

    def test_metrics_report_limit_and_used_seconds(self):
        user = User.objects.create_user(email='usage@kyapture.com', password='SecurePassword123!', username='usage')
        grant_plan(user, name='Pro')
        SubscriptionPlan.objects.filter(key='pro').update(video_minutes=60)
        gallery = Gallery.objects.create(photographer=user, title='U', slug='usage-g')
        MediaAsset.objects.create(
            gallery=gallery, media_type=MediaAsset.MediaType.VIDEO,
            original_file=SimpleUploadedFile('v.mp4', b'x'), original_name='v.mp4',
            file_size=1, duration=90, order=Decimal('1.0'))
        from apps.core.utils import get_user_subscription_metrics
        metrics = get_user_subscription_metrics(user)
        self.assertEqual((metrics['video_minutes_limit'], metrics['current_video_seconds']), (60, 90))


class BackfillVideoDurationsTests(APITestCase):
    def setUp(self):
        user = User.objects.create_user(email='bf@kyapture.com', password='SecurePassword123!', username='bf')
        gallery = Gallery.objects.create(photographer=user, title='B', slug='bf-g')
        self.asset = MediaAsset.objects.create(
            gallery=gallery, media_type=MediaAsset.MediaType.VIDEO,
            original_file=_video_upload_file(name='b.mp4', duration=3), original_name='b.mp4',
            file_size=1, order=Decimal('1.0'))

    def run_command(self, *args):
        out = StringIO()
        call_command('backfill_video_durations', *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_dry_run_is_the_default_and_writes_nothing(self):
        output = self.run_command()
        self.assertIn('Would update 1 of 1', output)
        self.asset.refresh_from_db()
        self.assertIsNone(self.asset.duration)

    def test_apply_stores_the_measured_duration(self):
        self.run_command('--apply')
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.duration, 3)
        self.assertIn('Would update 0 of 0', self.run_command())       # idempotent
