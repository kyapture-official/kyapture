"""
Chunk DB-A: byte counts are 64-bit.

`MediaAsset.file_size` used to be a 32-bit column (max 2,147,483,647 bytes), so a
2-5 GiB video made the insert fail and the upload answer 500. Covered here:
the column type, save/load/serialize of a 4 GiB row, storage usage (an int in
JSON, not a Decimal string), the 5 GB video ceiling and plan rules for a video
above 2 GiB (accepted or refused, never a 500), and ZIP/download job sizes
above 2 GiB. A real file of that size is never created: the multipart file's
reported size is patched, the stored bytes are a tiny real clip.
"""
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.clients.download_jobs import size_limit_error
from apps.clients.tests.test_download_jobs import JobBase
from apps.photos.models import MediaAsset
from apps.photos.serializers import MAX_VIDEO_FILE_SIZE_BYTES, MediaAssetSerializer
from apps.photos.tests.test_storage_limit import StorageBase
from apps.photos.tests.test_video_pipeline import _make_video_bytes
from apps.subscriptions.entitlements import GB

INT32_MAX = 2 ** 31 - 1
FOUR_GIB = 4 * GB
FIVE_GB = 5 * GB


def _row(gallery, size, name='big.mp4', media_type='video', order=1):
    return MediaAsset.objects.create(
        gallery=gallery, media_type=media_type, original_file=SimpleUploadedFile(name, b'x'),
        original_name=name, file_size=size, order=Decimal(order),
        processing_status=MediaAsset.ProcessingStatus.READY)


class BigSizeRowTests(StorageBase):
    def test_the_column_is_a_64_bit_integer_with_its_non_negative_check(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "select data_type from information_schema.columns "
                "where table_name = 'media_assets' and column_name = 'file_size'")
            self.assertEqual(cursor.fetchone()[0], 'bigint')
            cursor.execute(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid = 'media_assets'::regclass and conname = 'media_assets_file_size_check'")
            self.assertIn('file_size >= 0', cursor.fetchone()[0])

    def test_a_4_gib_row_saves_loads_and_serializes(self):
        saved = _row(self.gallery, FOUR_GIB)
        self.assertGreater(FOUR_GIB, INT32_MAX)
        loaded = MediaAsset.objects.get(pk=saved.pk)
        self.assertEqual(loaded.file_size, FOUR_GIB)
        data = MediaAssetSerializer(loaded, context={'request': None}).data
        self.assertEqual(data['file_size'], FOUR_GIB)
        self.assertIsInstance(data['file_size'], int)

    def test_the_largest_allowed_video_and_a_negative_size(self):
        self.assertEqual(_row(self.gallery, MAX_VIDEO_FILE_SIZE_BYTES).file_size, FIVE_GB)
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            _row(self.gallery, -1, name='neg.mp4', order=2)

    def test_the_photo_listing_returns_the_big_size_as_a_json_number(self):
        self.plan(storage_gb=100)
        _row(self.gallery, FOUR_GIB)
        body = self.client.get(self.url).json()
        self.assertEqual(body[0]['file_size'], FOUR_GIB)
        self.assertIsInstance(body[0]['file_size'], int)

    def test_a_4_gib_row_counts_toward_storage_usage_as_an_int(self):
        from apps.core.utils import get_user_subscription_metrics
        self.plan(storage_gb=10)
        _row(self.gallery, FOUR_GIB)
        _row(self.gallery, FOUR_GIB, name='b.mp4', order=2)      # 8 GiB: the SUM is also past 2^31
        metrics = get_user_subscription_metrics(self.user)
        self.assertEqual(metrics['current_total_storage_bytes'], 2 * FOUR_GIB)
        self.assertIs(type(metrics['current_total_storage_bytes']), int)     # never a Decimal

        stats = self.stats()
        self.assertEqual(stats['storage_used_bytes'], 2 * FOUR_GIB)
        raw = self.client.get('/api/v1/galleries/dashboard/stats/').json()
        for key in ('storage_used_bytes', 'plan_storage_limit_bytes', 'storage_remaining_bytes'):
            self.assertIsInstance(raw[key], int, key)            # JSON number, not a string
        self.assertEqual(raw['storage_remaining_bytes'], 2 * GB)
        self.assertEqual(raw['storage_state'], 'ok')

    def test_usage_over_the_plan_is_reported_as_over_with_big_numbers(self):
        self.plan(storage_gb=3)
        _row(self.gallery, FOUR_GIB)
        stats = self.stats()
        self.assertEqual((stats['storage_state'], stats['storage_remaining_bytes']), ('over', 0))
        self.assertEqual(stats['storage_used_bytes'], FOUR_GIB)


class _BigVideoUploadBase(StorageBase):
    """Uploads a real 2-second clip whose reported size is patched to `size`."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clip_bytes = _make_video_bytes(duration=2)

    def upload_video(self, size, name='big.mp4'):
        clip = SimpleUploadedFile(name, self.clip_bytes, content_type='video/mp4')
        # Only the server-side copy is parsed from the request, so patch what it reports.
        with mock.patch.object(InMemoryUploadedFile, 'size', new_callable=mock.PropertyMock, return_value=size):
            with self.captureOnCommitCallbacks(execute=False):
                return self.client.post(self.url, {'video': [clip]}, format='multipart')


class BigVideoUploadTests(_BigVideoUploadBase):
    def test_a_4_gib_video_within_the_plan_is_accepted_and_stored_with_its_size(self):
        self.plan(storage_gb=100)
        response = self.upload_video(FOUR_GIB)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
        self.assertEqual(MediaAsset.objects.get(original_name='big.mp4').file_size, FOUR_GIB)
        self.assertEqual(response.json()[0]['file_size'], FOUR_GIB)
        self.assertEqual(self.stats()['storage_used_bytes'], FOUR_GIB)

    def test_a_5_gb_video_passes_the_size_check_and_is_accepted_when_the_plan_has_room(self):
        self.plan(storage_gb=100)
        response = self.upload_video(MAX_VIDEO_FILE_SIZE_BYTES)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
        self.assertEqual(MediaAsset.objects.get(original_name='big.mp4').file_size, FIVE_GB)

    def test_a_5_gb_video_over_the_plan_storage_is_refused_403_not_500(self):
        self.plan(storage_gb=3)
        response = self.upload_video(MAX_VIDEO_FILE_SIZE_BYTES)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'storage_limit_reached')
        self.assertEqual(response.data['refused_bytes'], FIVE_GB)
        self.assertEqual(response.json()['refused_bytes'], FIVE_GB)
        self.assertFalse(self.stored('big.mp4'))

    def test_a_video_that_fills_a_5_gb_plan_exactly_fits_and_one_byte_more_does_not(self):
        self.plan(storage_gb=5)
        self.assertEqual(self.upload_video(FIVE_GB).status_code, status.HTTP_202_ACCEPTED)
        MediaAsset.objects.all().delete()
        self.assertEqual(self.upload_video(FIVE_GB + 1).status_code, status.HTTP_403_FORBIDDEN)

    def test_above_the_5_gb_technical_ceiling_is_a_400_for_a_metered_account(self):
        self.plan(storage_gb=100)
        response = self.upload_video(MAX_VIDEO_FILE_SIZE_BYTES + 1)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'upload_validation_failed')
        self.assertFalse(self.stored('big.mp4'))

    def test_the_free_plan_refuses_a_4_gib_video_and_never_answers_500(self):
        response = self.upload_video(FOUR_GIB)                   # no plan granted: Free
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN,))
        self.assertFalse(self.stored('big.mp4'))


class BigDownloadSizeTests(JobBase):
    def test_the_sync_ceiling_compares_sizes_above_2_gib(self):
        small = MediaAsset(file_size=FOUR_GIB)
        self.assertIsNone(size_limit_error([small]))                              # 4 GiB < 5 GiB ceiling
        self.assertEqual(size_limit_error([small, MediaAsset(file_size=2 * GB)]), 'download_too_large')
        with override_settings(SYNC_ZIP_MAX_TOTAL_BYTES=FOUR_GIB - 1):
            self.assertEqual(size_limit_error([small]), 'download_too_large')

    def test_a_zip_part_above_2_gib_is_listed_with_its_real_size(self):
        token = self.token()
        with mock.patch('apps.clients.download_jobs.os.path.getsize', return_value=3 * GB):
            job_id = self.prepare(token).data['job_id']          # the mixin runs the job inline
        ready = self.status_of(job_id, token)
        self.assertEqual(ready.data['state'], 'ready')
        # getsize is patched for the whole job, so each photo also reads as 3 GiB and the
        # two photos split into two parts (past the 2 GiB part limit): both sizes are listed.
        files = ready.json()['files']
        self.assertEqual(len(files), 2)
        for entry in files:
            self.assertEqual(entry['size_bytes'], 3 * GB)
            self.assertIsInstance(entry['size_bytes'], int)

    def test_a_4_gib_original_is_a_valid_download_selection(self):
        MediaAsset.objects.filter(pk=self.a1.pk).update(file_size=FOUR_GIB)
        token = self.token()
        response = self.prepare(token)
        self.assertEqual(response.status_code, 202, response.data)
