"""
Chunk BILL-C: the plan's photo storage (`storage_gb`) is enforced at upload.

Usage = sum of the account's original files (MediaAsset.file_size). A file that
would pass the limit is refused with 403 / storage_limit_reached (used and limit
in GB); a mixed batch uploads what fits and reports the rest. The limit is the
plan row's value, read per request: an admin edit applies to every subscriber at
once, and an account already over a lowered limit keeps everything (view,
download, delete) but cannot add more. Real ffmpeg clips for the video cases.
"""
import io
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.photos.tests.test_video_pipeline import _make_video_bytes
from apps.subscriptions import entitlements
from apps.subscriptions.entitlements import GB, storage_fits
from apps.subscriptions.models import SubscriptionPlan, UserSubscription
from apps.subscriptions.testing import grant_plan

User = get_user_model()
STATS = '/api/v1/galleries/dashboard/stats/'


def jpeg_bytes(size=(50, 50), noisy=False):
    image = Image.new('RGB', size, 'white')
    if noisy:
        import os
        image = Image.frombytes('RGB', size, os.urandom(size[0] * size[1] * 3))
    buf = io.BytesIO()
    image.save(buf, 'JPEG')
    return buf.getvalue()


def jpeg(name, **kwargs):
    return SimpleUploadedFile(name, jpeg_bytes(**kwargs), content_type='image/jpeg')


class StorageBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='bill-c-owner@kyapture.com', password='SecurePassword123!', username='billcowner')
        self.gallery = Gallery.objects.create(photographer=self.user, title='Store', slug='store-limit')
        self.url = f'/api/v1/photos/{self.gallery.slug}/upload/'
        self.client.force_authenticate(user=self.user)

    def plan(self, name='Pro', storage_gb=1, video_minutes=60):
        plan = grant_plan(self.user, name=name)
        plan.storage_gb, plan.video_minutes = storage_gb, video_minutes
        plan.save(update_fields=['storage_gb', 'video_minutes'])
        return plan

    def fill(self, total_bytes):
        """Existing usage of exactly `total_bytes` (rows are capped by the column's 32-bit range)."""
        order = 1
        while total_bytes > 0:
            chunk = min(total_bytes, GB)
            MediaAsset.objects.create(
                gallery=self.gallery, original_file=SimpleUploadedFile(f'fill-{order}.jpg', b'x'),
                original_name=f'fill-{order}.jpg', file_size=chunk, order=Decimal(order),
                processing_status=MediaAsset.ProcessingStatus.READY)
            total_bytes -= chunk
            order += 1

    def post(self, **files):
        with self.captureOnCommitCallbacks(execute=False):
            return self.client.post(self.url, files, format='multipart')

    def stored(self, name):
        return MediaAsset.objects.filter(original_name=name).exists()

    def stats(self):
        return self.client.get(STATS).data


class StorageFitsRuleTests(APITestCase):
    def metrics(self, used, limit):
        return {'current_total_storage_bytes': used, 'storage_bytes_limit': limit}

    def test_exactly_the_limit_fits_one_byte_over_does_not(self):
        self.assertEqual(storage_fits(self.metrics(90, 100), [10]), [True])
        self.assertEqual(storage_fits(self.metrics(90, 100), [11]), [False])

    def test_files_take_space_in_order_and_a_later_small_one_can_still_fit(self):
        self.assertEqual(storage_fits(self.metrics(0, 100), [60, 60, 30]), [True, False, True])
        self.assertEqual(storage_fits(self.metrics(0, 100), [30, 30, 30, 30]), [True, True, True, False])

    def test_an_account_over_a_lowered_limit_fits_nothing(self):
        self.assertEqual(storage_fits(self.metrics(300, 100), [1, 5]), [False, False])


class PhotoUploadLimitTests(StorageBase):
    def test_under_the_limit_uploads(self):
        self.plan()
        response = self.post(image=[jpeg('under.jpg')])
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(len(response.data), 1)                         # unchanged shape: a list of assets
        self.assertTrue(self.stored('under.jpg'))

    def test_landing_exactly_on_the_limit_uploads_and_the_meter_reads_full(self):
        self.plan()
        size = len(jpeg_bytes())
        self.fill(GB - size)
        self.assertEqual(self.post(image=[jpeg('exact.jpg')]).status_code, status.HTTP_202_ACCEPTED)
        stats = self.stats()
        self.assertEqual((stats['storage_used_bytes'], stats['storage_state']), (GB, 'full'))

    def test_one_byte_over_is_refused_403_with_used_and_limit_and_nothing_stored(self):
        self.plan()
        size = len(jpeg_bytes())
        self.fill(GB - size + 1)
        response = self.post(image=[jpeg('over.jpg')])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'storage_limit_reached')
        self.assertEqual((response.data['used_gb'], response.data['plan_limit_gb']), (1.0, 1.0))
        self.assertEqual(response.data['plan_name'], 'Pro')
        self.assertEqual(response.data['refused_count'], 1)
        self.assertFalse(self.stored('over.jpg'))
        self.assertEqual(MediaAsset.objects.count(), 1)                 # only the fill row

    def test_direct_api_call_by_a_free_user_at_the_free_limit_is_refused(self):
        free = SubscriptionPlan.get_free()
        self.assertFalse(UserSubscription.objects.filter(user=self.user).exists())     # no subscription at all
        self.fill(free.storage_gb * GB)
        response = self.post(image=[jpeg('free.jpg')])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'storage_limit_reached')
        self.assertEqual(response.data['plan_name'], 'Free')
        self.assertEqual(response.data['plan_limit_gb'], free.storage_gb)
        self.assertFalse(self.stored('free.jpg'))

    def test_unauthenticated_upload_is_still_refused(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.post(image=[jpeg('anon.jpg')]).status_code, (401, 403))

    def test_staff_are_not_metered(self):
        staff = User.objects.create_user(
            email='bill-c-staff@kyapture.com', password='SecurePassword123!', username='billcstaff', is_staff=True)
        gallery = Gallery.objects.create(photographer=staff, title='Staff', slug='staff-store')
        MediaAsset.objects.create(
            gallery=gallery, original_file=SimpleUploadedFile('s.jpg', b'x'), original_name='s.jpg',
            file_size=GB, order=Decimal(1), processing_status=MediaAsset.ProcessingStatus.READY)
        self.client.force_authenticate(user=staff)
        with self.captureOnCommitCallbacks(execute=False):
            response = self.client.post(f'/api/v1/photos/{gallery.slug}/upload/', {'image': [jpeg('ok.jpg')]}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)


class VideoUploadLimitTests(StorageBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clip_bytes = _make_video_bytes(duration=2)       # one clip, so every upload has the same exact size

    def video(self, name='clip.mp4'):
        return SimpleUploadedFile(name, self.clip_bytes, content_type='video/mp4')

    def test_video_under_and_exactly_at_the_limit_uploads(self):
        self.plan()
        self.assertEqual(self.post(video=[self.video('under.mp4')]).status_code, status.HTTP_202_ACCEPTED)
        MediaAsset.objects.all().delete()
        self.fill(GB - len(self.clip_bytes))
        self.assertEqual(self.post(video=[self.video('exact.mp4')]).status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(self.stats()['storage_state'], 'full')

    def test_video_one_byte_over_is_refused_with_the_storage_code(self):
        self.plan()
        self.fill(GB - len(self.clip_bytes) + 1)
        response = self.post(video=[self.video('over.mp4')])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'storage_limit_reached')    # not a video-minutes code
        self.assertFalse(self.stored('over.mp4'))

    def test_photo_that_fits_uploads_and_the_video_that_does_not_is_reported(self):
        self.plan()
        image = jpeg('fits.jpg')
        self.fill(GB - len(jpeg_bytes()))
        response = self.post(image=[image], video=[self.video('nofit.mp4')])
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual([a['original_name'] for a in response.data['uploaded']], ['fits.jpg'])
        self.assertEqual([r['name'] for r in response.data['refused']], ['nofit.mp4'])
        self.assertEqual(response.data['storage']['code'], 'storage_limit_reached')
        self.assertTrue(self.stored('fits.jpg'))
        self.assertFalse(self.stored('nofit.mp4'))


class BatchTests(StorageBase):
    def test_a_batch_that_partly_fits_uploads_what_fits_and_reports_the_rest(self):
        self.plan()
        size = len(jpeg_bytes())
        self.fill(GB - 2 * size)
        response = self.post(image=[jpeg('a.jpg'), jpeg('b.jpg'), jpeg('c.jpg')])
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual([a['original_name'] for a in response.data['uploaded']], ['a.jpg', 'b.jpg'])
        self.assertEqual(response.data['refused'], [{'name': 'c.jpg', 'size_bytes': size, 'code': 'storage_limit_reached'}])
        self.assertEqual((self.stored('a.jpg'), self.stored('b.jpg'), self.stored('c.jpg')), (True, True, False))
        self.assertEqual(response.data['storage']['refused_count'], 1)

    def test_a_big_file_that_does_not_fit_does_not_block_a_smaller_one_after_it(self):
        self.plan()
        big, small = jpeg('big.jpg', size=(200, 200), noisy=True), jpeg('small.jpg')
        self.fill(GB - small.size)
        response = self.post(image=[big, small])
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual((self.stored('big.jpg'), self.stored('small.jpg')), (False, True))

    def test_a_batch_where_nothing_fits_is_a_plain_403_and_stores_nothing(self):
        self.plan()
        self.fill(GB)
        response = self.post(image=[jpeg('a.jpg'), jpeg('b.jpg')])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['refused_count'], 2)
        self.assertEqual(MediaAsset.objects.count(), 1)

    def test_the_decision_is_remade_under_a_lock_so_a_parallel_upload_cannot_claim_the_same_space(self):
        self.plan()
        stale = mock.Mock(return_value=None)
        from apps.core.utils import get_user_subscription_metrics as real

        def metrics_for(user):
            # 1st read (early check): usage before a parallel upload landed. 2nd read (under the lock): after it.
            if not stale.called:
                stale.return_value = True
                stale()
                return real(user)
            return {**real(user), 'current_total_storage_bytes': GB}

        with mock.patch('apps.photos.views.get_user_subscription_metrics', side_effect=metrics_for):
            response = self.post(image=[jpeg('race.jpg')])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'storage_limit_reached')
        self.assertFalse(self.stored('race.jpg'))


class AdminEditTests(StorageBase):
    def admin_save(self, plan, **changes):
        """A real submit of the Django admin change form (not an ORM shortcut)."""
        if not hasattr(self, 'admin_client'):
            self.admin_client = self.client_class()
            self.admin_client.force_login(User.objects.create_user(
                email='bill-c-boss@kyapture.com', password='SecurePassword123!', username='billcboss',
                is_staff=True, is_superuser=True))
        data = {
            'name': plan.name, 'price': str(plan.price), 'is_active': 'on', 'storage_gb': plan.storage_gb,
            'max_collections': '' if plan.max_collections is None else plan.max_collections,
            'video_minutes': '' if plan.video_minutes is None else plan.video_minutes,
        }
        for flag in ('original_download', 'watermark', 'branding'):
            if getattr(plan, flag):
                data[flag] = 'on'
        data.update(changes)
        response = self.admin_client.post(f'/admin/subscriptions/subscriptionplan/{plan.pk}/change/', data)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['adminform'].form.errors)

    def test_no_subscription_row_stores_its_own_copy_of_the_limit(self):
        names = {f.name for f in UserSubscription._meta.get_fields()}
        self.assertFalse({n for n in names if 'storage' in n or 'limit' in n or n.endswith('_gb')})
        self.assertEqual([f.name for f in SubscriptionPlan._meta.get_fields() if f.name == 'storage_gb'], ['storage_gb'])

    def test_editing_storage_gb_in_admin_changes_the_next_request_for_free_users(self):
        free = SubscriptionPlan.get_free()
        self.fill(free.storage_gb * GB)
        self.assertEqual(self.post(image=[jpeg('before.jpg')]).status_code, status.HTTP_403_FORBIDDEN)

        self.admin_save(free, storage_gb=free.storage_gb + 1)                      # raised: same process, no restart
        self.assertEqual(self.stats()['plan_storage_limit_gb'], free.storage_gb + 1)
        self.assertEqual(self.post(image=[jpeg('after.jpg')]).status_code, status.HTTP_202_ACCEPTED)

        self.admin_save(SubscriptionPlan.get_free(), storage_gb=free.storage_gb)    # lowered again
        self.assertEqual(self.post(image=[jpeg('again.jpg')]).status_code, status.HTTP_403_FORBIDDEN)

    def test_lowering_a_paid_plan_in_admin_reaches_every_subscriber_without_touching_their_row(self):
        pro = self.plan('Pro', storage_gb=100)
        other = User.objects.create_user(email='bill-c-two@kyapture.com', password='SecurePassword123!', username='billctwo')
        grant_plan(other, name='Pro')
        other_gallery = Gallery.objects.create(photographer=other, title='Two', slug='store-two')
        rows_before = list(UserSubscription.objects.order_by('pk').values_list('pk', 'updated_at', 'plan_id'))

        self.admin_save(pro, storage_gb=1)
        self.assertEqual(list(UserSubscription.objects.order_by('pk').values_list('pk', 'updated_at', 'plan_id')), rows_before)

        self.fill(GB)
        self.assertEqual(self.post(image=[jpeg('mine.jpg')]).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=other)
        MediaAsset.objects.create(
            gallery=other_gallery, original_file=SimpleUploadedFile('o.jpg', b'x'), original_name='o.jpg',
            file_size=GB, order=Decimal(1), processing_status=MediaAsset.ProcessingStatus.READY)
        with self.captureOnCommitCallbacks(execute=False):
            refused = self.client.post(f'/api/v1/photos/{other_gallery.slug}/upload/', {'image': [jpeg('theirs.jpg')]}, format='multipart')
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)


class OverLoweredLimitTests(StorageBase):
    """Nothing is deleted when a plan is lowered: new uploads stop, everything else keeps working."""

    def setUp(self):
        super().setUp()
        self.pro = self.plan('Pro', storage_gb=100)
        with self.captureOnCommitCallbacks(execute=False):
            self.client.post(self.url, {'image': [jpeg('keep.jpg')]}, format='multipart')
        self.keep = MediaAsset.objects.get(original_name='keep.jpg')
        self.fill(3 * GB)                                                         # 3 GB used on a plan about to hold 1
        SubscriptionPlan.objects.filter(pk=self.pro.pk).update(storage_gb=1)       # the admin lowers it

    def test_new_uploads_are_refused_and_state_is_over(self):
        response = self.post(image=[jpeg('new.jpg')])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertGreater(response.data['used_gb'], response.data['plan_limit_gb'])
        stats = self.stats()
        self.assertEqual(stats['storage_state'], 'over')
        self.assertEqual((stats['plan_storage_limit_gb'], stats['storage_remaining_bytes']), (1.0, 0))
        self.assertGreater(stats['storage_used_bytes'], 3 * GB)

    def test_nothing_was_deleted_and_the_owner_can_still_view_the_files(self):
        self.assertEqual(MediaAsset.objects.filter(gallery=self.gallery).count(), 4)
        listing = self.client.get(self.url)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data), 4)
        self.assertEqual(self.client.get(f'/api/v1/photos/photo/{self.keep.id}/').status_code, status.HTTP_200_OK)

    def test_deleting_still_works_and_frees_space_at_once(self):
        fillers = list(MediaAsset.objects.filter(original_name__startswith='fill-'))
        self.assertEqual(self.client.delete(f'/api/v1/photos/photo/{fillers[0].id}/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.stats()['storage_state'], 'over')                    # 2 GB still > 1 GB
        for filler in fillers[1:]:
            self.client.delete(f'/api/v1/photos/photo/{filler.id}/')
        stats = self.stats()                                                        # only keep.jpg left
        self.assertEqual(stats['storage_state'], 'ok')
        self.assertEqual(self.post(image=[jpeg('now-fits.jpg')]).status_code, status.HTTP_202_ACCEPTED)


class DeleteFreesSpaceTests(StorageBase):
    def test_deleting_a_photo_lets_the_next_upload_through_immediately(self):
        self.plan()
        size = len(jpeg_bytes())
        self.fill(GB - size)
        self.assertEqual(self.post(image=[jpeg('one.jpg')]).status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(self.post(image=[jpeg('two.jpg')]).status_code, status.HTTP_403_FORBIDDEN)
        one = MediaAsset.objects.get(original_name='one.jpg')
        self.assertEqual(self.client.delete(f'/api/v1/photos/photo/{one.id}/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.post(image=[jpeg('two.jpg')]).status_code, status.HTTP_202_ACCEPTED)


class UsageEndpointMeterTests(StorageBase):
    def test_figures_and_state_thresholds_come_from_the_plan_and_one_constant(self):
        self.plan(storage_gb=10)
        stats = self.stats()
        self.assertEqual((stats['storage_used_bytes'], stats['plan_storage_limit_gb'], stats['storage_state']), (0, 10.0, 'ok'))
        self.assertEqual(stats['storage_warning_percent'], round(entitlements.STORAGE_WARNING_FRACTION * 100))
        self.assertEqual(stats['storage_remaining_bytes'], 10 * GB)

        def state(used):
            MediaAsset.objects.all().delete()
            self.fill(used)
            return self.stats()['storage_state']

        edge = int(10 * GB * entitlements.STORAGE_WARNING_FRACTION)
        self.assertEqual([state(edge - 1), state(edge), state(10 * GB), state(10 * GB + 1)], ['ok', 'warning', 'full', 'over'])
        self.assertEqual(self.stats()['storage_percent_used'], 100.0)

    def test_changing_the_constant_moves_the_warning_and_the_number_the_frontend_reads(self):
        self.plan(storage_gb=10)
        self.fill(6 * GB)
        self.assertEqual(self.stats()['storage_state'], 'ok')
        with mock.patch.object(entitlements, 'STORAGE_WARNING_FRACTION', 0.5):
            stats = self.stats()
        self.assertEqual((stats['storage_state'], stats['storage_warning_percent']), ('warning', 50))

    def test_free_user_without_a_subscription_gets_the_same_fields(self):
        stats = self.stats()
        self.assertEqual(stats['subscription_status'], 'no_subscription')
        self.assertEqual(stats['plan_storage_limit_gb'], float(SubscriptionPlan.get_free().storage_gb))
        self.assertEqual(stats['storage_state'], 'ok')
