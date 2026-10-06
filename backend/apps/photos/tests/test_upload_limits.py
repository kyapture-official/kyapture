"""
Chunk UP-A: admin-editable per-file upload limits (UploadLimits row).

max_image_mb, max_image_pixels and max_video_mb are read at request time from the
one admin-edited row (nothing hard-coded). Covered: exactly at and one byte/pixel
over each limit, an image refused from its header without being decoded, a video
over the limit refused before ffprobe, a mixed batch where only the refused file
is dropped, an admin form edit changing the next upload with no restart, the
limits in the usage API, and never a 500. Test files are generated in memory (a
PNG header for the huge image, a real tiny clip with a patched size for video).
"""
import io
import struct
import zlib
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.test import Client
from PIL import Image
from rest_framework import status

from apps.photos.models import MediaAsset
from apps.photos.tests.test_storage_limit import StorageBase, jpeg
from apps.photos.tests.test_video_pipeline import _make_video_bytes
from apps.subscriptions.models import UploadLimits
from apps.subscriptions.upload_limits import MB, apply_pillow_pixel_guard, get_upload_limits

User = get_user_model()
STATS = '/api/v1/galleries/dashboard/stats/'
ADMIN_URL = '/admin/subscriptions/uploadlimits/1/change/'


def set_limits(**values):
    row = UploadLimits.load()
    for name, value in values.items():
        setattr(row, name, value)
    row.save()
    return row


def jpeg_of_size(name, size_bytes):
    """A valid 50x50 JPEG padded (after its end marker, which Pillow ignores) to exactly `size_bytes`."""
    data = jpeg(name).read()
    assert len(data) <= size_bytes
    return SimpleUploadedFile(name, data + b'\0' * (size_bytes - len(data)), content_type='image/jpeg')


def jpeg_of_dims(name, width, height):
    buf = io.BytesIO()
    Image.new('RGB', (width, height), 'white').save(buf, 'JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


def fake_png(width, height):
    """A PNG with a valid header declaring width x height and no pixel data (nothing to decode)."""
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IEND', b'')


class LimitsBase(StorageBase):
    def upload(self, **files):
        return self.post(**files)

    def assertRefused(self, response, code, **body):
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content[:300])
        self.assertEqual(response.json()['code'], code)
        for key, value in body.items():
            self.assertEqual(response.json()[key], value, key)


class DefaultsTests(LimitsBase):
    def test_the_row_defaults_and_it_is_a_singleton(self):
        limits = get_upload_limits()
        self.assertEqual((limits.max_image_mb, limits.max_image_pixels, limits.max_video_mb), (100, 144_000_000, 2048))
        UploadLimits(max_image_mb=7).save()                    # a second save writes the same row
        self.assertEqual(UploadLimits.objects.count(), 1)
        self.assertEqual(UploadLimits.load().max_image_mb, 7)

    def test_the_usage_api_returns_the_limits_for_free_paid_and_staff(self):
        set_limits(max_image_mb=11, max_image_pixels=12_345, max_video_mb=13)
        expected = {'max_image_mb': 11, 'max_image_pixels': 12_345, 'max_video_mb': 13}
        self.assertEqual(self.client.get(STATS).json()['upload_limits'], expected)          # Free
        self.plan()
        self.assertEqual(self.client.get(STATS).json()['upload_limits'], expected)          # Pro
        self.user.is_staff = True
        self.user.save()
        self.assertEqual(self.client.get(STATS).json()['upload_limits'], expected)          # staff


class ImageSizeLimitTests(LimitsBase):
    def setUp(self):
        super().setUp()
        self.plan(storage_gb=100)
        set_limits(max_image_mb=1)

    def test_exactly_at_the_limit_uploads(self):
        response = self.upload(image=[jpeg_of_size('at.jpg', 1 * MB)])
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.content[:300])
        self.assertTrue(self.stored('at.jpg'))

    def test_one_byte_over_is_refused_with_the_limit_and_before_any_processing(self):
        with mock.patch('apps.subscriptions.upload_limits.PILImage.open', side_effect=AssertionError('read the file')) as opened, \
                mock.patch('apps.photos.views.strip_exif_gps', side_effect=AssertionError('processed')), \
                mock.patch('apps.photos.views.get_user_subscription_metrics', side_effect=AssertionError('plan check')):
            response = self.upload(image=[jpeg_of_size('over.jpg', 1 * MB + 1)])
        self.assertRefused(response, 'file_too_large', limit_mb=1, limit_bytes=MB, size_bytes=MB + 1,
                           message='Size exceeds 1 MB limit', file_name='over.jpg')
        opened.assert_not_called()                       # the file was not even opened
        self.assertFalse(self.stored('over.jpg'))

    def test_staff_are_held_to_the_same_limit(self):
        self.user.is_staff = True
        self.user.save()
        self.assertRefused(self.upload(image=[jpeg_of_size('over.jpg', MB + 1)]), 'file_too_large')


class ImagePixelLimitTests(LimitsBase):
    def setUp(self):
        super().setUp()
        self.plan(storage_gb=100)
        set_limits(max_image_pixels=10_000)

    def test_exactly_at_the_pixel_limit_uploads_and_one_pixel_more_is_refused(self):
        self.assertEqual(self.upload(image=[jpeg_of_dims('at.jpg', 100, 100)]).status_code, status.HTTP_202_ACCEPTED)
        response = self.upload(image=[jpeg_of_dims('over.jpg', 100, 101)])
        self.assertRefused(response, 'image_too_many_pixels', limit_pixels=10_000, width=100, height=101, pixels=10_100)
        self.assertFalse(self.stored('over.jpg'))

    def test_a_29952_square_image_is_refused_from_its_header_without_decoding(self):
        set_limits(max_image_pixels=144_000_000)              # the default: 29952 x 29952 = 897 million
        with mock.patch('PIL.ImageFile.ImageFile.load', side_effect=AssertionError('decoded')) as load, \
                mock.patch('apps.photos.views.strip_exif_gps', side_effect=AssertionError('processed')), \
                mock.patch('apps.photos.views.process_photo_asset') as task:
            response = self.upload(image=[SimpleUploadedFile('huge.png', fake_png(29952, 29952), content_type='image/png')])
        self.assertRefused(response, 'image_too_many_pixels', limit_pixels=144_000_000,
                           message='Image exceeds the 144,000,000 pixel limit')
        load.assert_not_called()
        task.delay.assert_not_called()
        self.assertFalse(MediaAsset.objects.filter(gallery=self.gallery).exists())

    def test_a_header_over_the_limit_but_under_twice_it_reports_its_dimensions_without_decoding(self):
        with mock.patch('PIL.ImageFile.ImageFile.load', side_effect=AssertionError('decoded')) as load:
            response = self.upload(image=[SimpleUploadedFile('wide.png', fake_png(150, 100), content_type='image/png')])
        self.assertRefused(response, 'image_too_many_pixels', width=150, height=100, pixels=15_000)
        load.assert_not_called()

    def test_the_pillow_guard_follows_the_setting(self):
        set_limits(max_image_pixels=12_345)
        self.assertEqual(apply_pillow_pixel_guard().max_image_pixels, 12_345)
        self.assertEqual(Image.MAX_IMAGE_PIXELS, 12_345)
        set_limits(max_image_pixels=54_321)
        self.upload(image=[jpeg_of_dims('a.jpg', 10, 10)])        # an upload re-reads the row
        self.assertEqual(Image.MAX_IMAGE_PIXELS, 54_321)

    def test_the_processing_task_applies_the_guard_too(self):
        from apps.photos.tasks import process_photo_asset
        self.upload(image=[jpeg_of_dims('a.jpg', 10, 10)])
        asset = MediaAsset.objects.get(original_name='a.jpg')
        set_limits(max_image_pixels=77_777)
        process_photo_asset.apply(args=[str(asset.id)])
        self.assertEqual(Image.MAX_IMAGE_PIXELS, 77_777)


class VideoSizeLimitTests(LimitsBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clip_bytes = _make_video_bytes(duration=2)

    def setUp(self):
        super().setUp()
        self.plan(storage_gb=10_000)

    def upload_video(self, size, name='clip.mp4'):
        clip = SimpleUploadedFile(name, self.clip_bytes, content_type='video/mp4')
        with mock.patch.object(InMemoryUploadedFile, 'size', new_callable=mock.PropertyMock, return_value=size):
            return self.upload(video=[clip])

    def test_exactly_at_the_default_limit_uploads(self):
        response = self.upload_video(2048 * MB)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.content[:300])
        self.assertTrue(self.stored('clip.mp4'))

    def test_one_byte_over_is_refused_before_ffprobe_with_the_limit(self):
        with mock.patch('apps.photos.views.probe_video_duration', side_effect=AssertionError('probed')):
            response = self.upload_video(2048 * MB + 1)
        self.assertRefused(response, 'file_too_large', limit_mb=2048, message='Size exceeds 2048 MB limit',
                           media_type='video')
        self.assertFalse(self.stored('clip.mp4'))

    def test_the_limit_is_the_row_value(self):
        set_limits(max_video_mb=5)
        self.assertEqual(self.upload_video(5 * MB).status_code, status.HTTP_202_ACCEPTED)
        self.assertRefused(self.upload_video(5 * MB + 1, name='b.mp4'), 'file_too_large', limit_mb=5)


class MixedBatchTests(LimitsBase):
    def setUp(self):
        super().setUp()
        self.plan(storage_gb=100)
        set_limits(max_image_mb=1, max_image_pixels=10_000, max_video_mb=1)

    def test_a_batch_of_good_big_and_huge_images_keeps_the_good_one(self):
        batch = [
            jpeg_of_dims('ok.jpg', 50, 50),
            jpeg_of_size('big.jpg', MB + 1),
            jpeg_of_dims('huge.jpg', 100, 101),
        ]
        response = self.upload(image=batch)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.content[:300])
        body = response.json()
        self.assertEqual([a['original_name'] for a in body['uploaded']], ['ok.jpg'])
        self.assertEqual(sorted((r['file_name'], r['code']) for r in body['rejected']),
                         [('big.jpg', 'file_too_large'), ('huge.jpg', 'image_too_many_pixels')])
        self.assertEqual(MediaAsset.objects.filter(gallery=self.gallery).count(), 1)

    def test_a_photo_and_an_oversize_video_in_one_request(self):
        photo = jpeg_of_dims('ok.jpg', 50, 50)
        clip = SimpleUploadedFile('big.mp4', b'\0' * (MB + 1), content_type='video/mp4')
        response = self.upload(image=[photo], video=[clip])
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.content[:300])
        body = response.json()
        self.assertEqual([a['original_name'] for a in body['uploaded']], ['ok.jpg'])
        self.assertEqual([(r['file_name'], r['code']) for r in body['rejected']], [('big.mp4', 'file_too_large')])
        self.assertNotIn('refused', body)                    # no storage refusal in this answer


class NeverA500Tests(LimitsBase):
    def setUp(self):
        super().setUp()
        self.plan(storage_gb=100)

    def test_garbage_and_truncated_files_answer_400_not_500(self):
        for name, data in (('x.jpg', b'not an image at all'), ('y.png', fake_png(10, 10)[:20]), ('z.jpg', b'')):
            response = self.upload(image=[SimpleUploadedFile(name, data, content_type='image/jpeg')])
            self.assertLess(response.status_code, 500, (name, response.content[:200]))
            self.assertGreaterEqual(response.status_code, 400)

    def test_a_pillow_bomb_error_raised_after_the_header_check_is_a_400(self):
        with mock.patch('apps.photos.views.strip_exif_gps', side_effect=Image.DecompressionBombError('boom')):
            response = self.upload(image=[jpeg_of_dims('a.jpg', 10, 10)])
        self.assertRefused(response, 'image_too_many_pixels')
        self.assertFalse(self.stored('a.jpg'))


class AdminEditTests(LimitsBase):
    def setUp(self):
        super().setUp()
        self.plan(storage_gb=100)
        self.staff = User.objects.create_user(email='up-a-admin@kyapture.com', password='SecurePassword123!',
                                              username='upaadmin')
        self.staff.is_staff = self.staff.is_superuser = True
        self.staff.save()
        self.admin = Client()
        self.admin.force_login(self.staff)

    def test_the_changelist_opens_the_single_row_and_it_cannot_be_added_or_deleted(self):
        self.assertEqual(self.admin.get('/admin/subscriptions/uploadlimits/').status_code, 200)
        self.assertEqual(self.admin.get(ADMIN_URL).status_code, 200)
        self.assertEqual(self.admin.get('/admin/subscriptions/uploadlimits/add/').status_code, 403)
        self.assertEqual(self.admin.post('/admin/subscriptions/uploadlimits/1/delete/', {'post': 'yes'}).status_code, 403)
        self.assertEqual(UploadLimits.objects.count(), 1)

    def test_an_admin_form_edit_changes_the_next_upload_with_no_restart(self):
        self.assertEqual(self.upload(image=[jpeg_of_size('first.jpg', 2 * MB)]).status_code, status.HTTP_202_ACCEPTED)

        saved = self.admin.post(ADMIN_URL, {'max_image_mb': 1, 'max_image_pixels': 144_000_000, 'max_video_mb': 2048})
        self.assertEqual(saved.status_code, 302, saved.content[:300])
        self.assertEqual(self.client.get(STATS).json()['upload_limits']['max_image_mb'], 1)
        self.assertRefused(self.upload(image=[jpeg_of_size('second.jpg', 2 * MB)]), 'file_too_large', limit_mb=1)

        self.admin.post(ADMIN_URL, {'max_image_mb': 3, 'max_image_pixels': 144_000_000, 'max_video_mb': 2048})
        self.assertEqual(self.upload(image=[jpeg_of_size('third.jpg', 2 * MB)]).status_code, status.HTTP_202_ACCEPTED)

    def test_the_form_refuses_a_zero_limit(self):
        response = self.admin.post(ADMIN_URL, {'max_image_mb': 0, 'max_image_pixels': 1, 'max_video_mb': 1})
        self.assertEqual(response.status_code, 200, response.get('Location'))            # form re-shown with an error
        self.assertEqual(UploadLimits.load().max_image_mb, 100)
