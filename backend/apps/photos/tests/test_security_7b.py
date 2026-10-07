# backend/apps/photos/tests/test_security_7b.py
"""
CHUNK 7-B - uploads, private keys and media metadata.

  - Row 82 (SEC-05): a private key (original, Download Master) is never derivable
    from a public URL: it carries a random part a visitor never sees. The stored
    extension comes from the file's real type, never from the client's filename.
  - Row 94 (SEC-19): GPS stripping on photos fails CLOSED (the upload is refused
    when location data cannot be removed), and covers XMP and PNG eXIf too;
    location metadata is removed from video originals and never copied into the
    playback MP4 or poster.
  - Row 93 (SEC-18): every ffmpeg call has a timeout.
  - Rows 4 / 31 / 75: an oversized upload body, or any body from an account
    with no storage left, is refused before a byte of it is read.
  - Row 43: a lapsed subscription no longer counts as the paid plan.
  - Row 44: video minutes are re-checked under the per-account lock.
"""
import io
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zlib
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import piexif
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.utils import get_user_subscription_metrics, process_video_pipeline
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.photos.tasks import process_video_asset
from apps.photos.tests.test_video_pipeline import _make_video_bytes
from apps.photos.views import PhotoListUploadView
from apps.subscriptions.models import UserSubscription
from apps.subscriptions.testing import grant_plan
from apps.users.models import User

GPS = {piexif.GPSIFD.GPSLatitudeRef: b'N', piexif.GPSIFD.GPSLatitude: ((27, 1), (42, 1), (0, 1)),
       piexif.GPSIFD.GPSLongitudeRef: b'E', piexif.GPSIFD.GPSLongitude: ((85, 1), (19, 1), (0, 1))}
XMP_GPS = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           b'<rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" exif:GPSLatitude="27,42.0N" '
           b'exif:GPSLongitude="85,19.0E"/></rdf:RDF></x:xmpmeta>')
HEX32 = re.compile(r'[0-9a-f]{32}')


def jpeg(gps=True, xmp=None):
    buf = io.BytesIO()
    Image.new('RGB', (32, 24), 'teal').save(buf, 'JPEG')
    data = buf.getvalue()
    if gps:
        out = io.BytesIO()
        piexif.insert(piexif.dump({'0th': {piexif.ImageIFD.Make: b'Cam'}, 'GPS': GPS}), data, out)
        data = out.getvalue()
    if xmp:
        payload = b'http://ns.adobe.com/xap/1.0/\x00' + xmp
        segment = b'\xff\xe1' + struct.pack('>H', len(payload) + 2) + payload
        data = data[:2] + segment + data[2:]
    return data


def png_with_exif_gps():
    buf = io.BytesIO()
    Image.new('RGB', (16, 16), 'navy').save(buf, 'PNG')
    data = buf.getvalue()
    tiff = piexif.dump({'GPS': GPS})[6:]          # strip the 'Exif\0\0' header: eXIf holds bare TIFF
    chunk = struct.pack('>I', len(tiff)) + b'eXIf' + tiff + struct.pack('>I', zlib.crc32(b'eXIf' + tiff) & 0xffffffff)
    iend = data.rindex(b'IEND') - 4
    return data[:iend] + chunk + data[iend:]


def has_gps(data):
    if data.startswith(b'\xff\xd8'):
        exif = piexif.load(data)
        if exif.get('GPS'):
            return True
    if b'GPSLatitude' in data or b'GPSLongitude' in data:
        return True
    if b'eXIf' in data:
        start = data.index(b'eXIf') + 4
        length = struct.unpack('>I', data[start - 8:start - 4])[0]
        return bool(piexif.load(data[start:start + length]).get('GPS'))
    return False


def ffprobe_tags(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format_tags:stream_tags', '-of', 'json', path],
                            capture_output=True, text=True, check=True, timeout=60)
    data = json.loads(result.stdout)
    tags = dict(data.get('format', {}).get('tags', {}))
    for stream in data.get('streams', []):
        tags.update(stream.get('tags', {}))
    return {k.lower(): v for k, v in tags.items()}


def video_with_location(suffix='.mov'):
    raw = _make_video_bytes(duration=1)
    src = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
    src.write(raw)
    src.close()
    out = src.name + suffix
    try:
        subprocess.run(['ffmpeg', '-y', '-i', src.name, '-c', 'copy', '-metadata', 'location=+27.7172+085.3240/',
                        '-metadata', 'location-eng=+27.7172+085.3240/', '-metadata', 'title=Keep me', out],
                       capture_output=True, check=True, timeout=60)
        with open(out, 'rb') as handle:
            return handle.read()
    finally:
        for path in (src.name, out):
            if os.path.exists(path):
                os.remove(path)


class TempMediaMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = tempfile.mkdtemp(prefix='kyapture-7b-media-')
        cls.addClassCleanup(shutil.rmtree, root, True)
        cls.enterClassContext(override_settings(MEDIA_ROOT=root))


class UploadBase(TempMediaMixin, APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='up7b@example.com', password='SecurePassword123!', username='up7b')
        self.gallery = Gallery.objects.create(photographer=self.user, title='Up', slug='up-7b')
        self.url = f'/api/v1/photos/{self.gallery.slug}/upload/'
        self.client.force_authenticate(self.user)

    def upload(self, name, data, field='image', content_type='image/jpeg'):
        with self.captureOnCommitCallbacks(execute=False):
            return self.client.post(self.url, {field: [SimpleUploadedFile(name, data, content_type=content_type)]},
                                    format='multipart')

    def stored(self):
        asset = MediaAsset.objects.get(gallery=self.gallery)
        asset.original_file.open('rb')
        try:
            return asset, asset.original_file.read()
        finally:
            asset.original_file.close()


class PrivateKeyTests(UploadBase):
    def test_the_original_key_has_a_random_part_and_is_not_derivable(self):
        self.assertEqual(self.upload('photo.jpg', jpeg(gps=False)).status_code, 202)
        asset = MediaAsset.objects.get(gallery=self.gallery)
        name = asset.original_file.name
        self.assertTrue(HEX32.search(os.path.basename(name)), name)
        guessed = f'photographers/{self.user.id}/galleries/{self.gallery.id}/photos/{asset.id}_original.jpg'
        self.assertNotEqual(name, guessed)

    def test_the_stored_extension_comes_from_the_bytes_not_the_filename(self):
        # Django's ImageField already refuses non-image extensions (.html, .svg); an
        # image extension that does not match the bytes was stored as sent.
        self.assertEqual(self.upload('photo.tiff', jpeg(gps=False)).status_code, 202)
        asset = MediaAsset.objects.get(gallery=self.gallery)
        self.assertTrue(asset.original_file.name.endswith('.jpg'), asset.original_file.name)
        self.assertEqual(asset.original_name, 'photo.tiff')      # the visitor-facing name is kept

    def test_a_non_image_extension_is_refused(self):
        """Holds: Django's ImageField extension check refuses an .html name before anything is stored."""
        self.assertEqual(self.upload('evil.html', jpeg(gps=False)).status_code, 400)
        self.assertFalse(MediaAsset.objects.exists())

    def test_the_download_master_key_has_a_random_part(self):
        from apps.photos.models import get_download_photo_path
        asset = MediaAsset(gallery=self.gallery, media_type=MediaAsset.MediaType.IMAGE)
        self.assertTrue(HEX32.search(get_download_photo_path(asset, 'x_download.jpg')))


class GpsFailClosedTests(UploadBase):
    def test_exif_gps_is_removed_and_the_pixels_are_untouched(self):
        data = jpeg(gps=True)
        self.assertEqual(self.upload('gps.jpg', data).status_code, 202)
        _, stored = self.stored()
        self.assertFalse(has_gps(stored))
        self.assertEqual(Image.open(io.BytesIO(stored)).tobytes(), Image.open(io.BytesIO(data)).tobytes())

    def test_gps_in_xmp_is_removed(self):
        self.assertEqual(self.upload('xmp.jpg', jpeg(gps=False, xmp=XMP_GPS)).status_code, 202)
        _, stored = self.stored()
        self.assertFalse(has_gps(stored))

    def test_gps_in_a_png_exif_chunk_is_removed(self):
        self.assertEqual(self.upload('gps.png', png_with_exif_gps(), content_type='image/png').status_code, 202)
        _, stored = self.stored()
        self.assertFalse(has_gps(stored))
        Image.open(io.BytesIO(stored)).verify()

    def test_when_gps_cannot_be_removed_the_upload_is_refused(self):
        data = jpeg(gps=True)
        with mock.patch('apps.core.utils.piexif.dump', side_effect=ValueError('boom')):
            response = self.upload('gps.jpg', data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'location_strip_failed')
        self.assertFalse(MediaAsset.objects.exists())

    def test_unreadable_exif_with_gps_is_refused(self):
        data = jpeg(gps=True)
        with mock.patch('apps.core.utils.piexif.load', side_effect=ValueError('corrupt')):
            response = self.upload('gps.jpg', data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'location_strip_failed')


class VideoLocationTests(TempMediaMixin, APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='vl7b@example.com', password='SecurePassword123!', username='vl7b')
        self.gallery = Gallery.objects.create(photographer=self.user, title='V', slug='vl-7b')

    def video_asset(self, data, name='clip.mov'):
        return MediaAsset.objects.create(
            gallery=self.gallery, media_type=MediaAsset.MediaType.VIDEO,
            original_file=SimpleUploadedFile(name, data, content_type='video/quicktime'),
            original_name=name, file_size=len(data), duration=1, order=Decimal('1.0'),
            processing_status=MediaAsset.ProcessingStatus.PENDING,
        )

    def tags_of(self, field):
        fd, path = tempfile.mkstemp(suffix=os.path.splitext(field.name)[1])
        os.close(fd)
        try:
            field.open('rb')
            with open(path, 'wb') as handle:
                handle.write(field.read())
            field.close()
            return ffprobe_tags(path)
        finally:
            os.remove(path)

    def test_the_fixture_really_carries_a_location(self):
        fd, path = tempfile.mkstemp(suffix='.mov')
        os.close(fd)
        with open(path, 'wb') as handle:
            handle.write(video_with_location())
        try:
            self.assertTrue(any('location' in key for key in ffprobe_tags(path)))
        finally:
            os.remove(path)

    def test_processing_removes_location_from_the_original_and_the_playback_copy(self):
        asset = self.video_asset(video_with_location())
        process_video_asset.apply(args=[str(asset.id)])
        asset.refresh_from_db()
        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.READY)
        for field in (asset.original_file, asset.playback_file):
            tags = self.tags_of(field)
            self.assertFalse([k for k in tags if 'location' in k or 'xyz' in k], (field.name, tags))
        asset.original_file.open('rb')
        self.assertEqual(asset.file_size, len(asset.original_file.read()))
        asset.original_file.close()

    def test_a_video_whose_location_cannot_be_removed_fails_closed(self):
        asset = self.video_asset(video_with_location())
        real_run = subprocess.run

        def refuse_remux(cmd, *args, **kwargs):
            if '-map_metadata' in cmd and '-c' in cmd and 'copy' in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            return real_run(cmd, *args, **kwargs)

        with mock.patch('apps.core.utils.subprocess.run', side_effect=refuse_remux):
            process_video_asset.apply(args=[str(asset.id)])
        asset.refresh_from_db()
        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.FAILED)
        self.assertFalse(asset.playback_file)

    def test_every_ffmpeg_call_has_a_timeout(self):
        calls = []
        real_run = subprocess.run

        def record(cmd, *args, **kwargs):
            calls.append((cmd[0], kwargs.get('timeout')))
            return real_run(cmd, *args, **kwargs)

        clip = SimpleUploadedFile('clip.mp4', _make_video_bytes(duration=1), content_type='video/mp4')
        with mock.patch('apps.core.utils.subprocess.run', side_effect=record):
            process_video_pipeline(clip)
        self.assertTrue(calls)
        self.assertEqual([c for c in calls if not c[1]], [])


class ExplodingStream(io.RawIOBase):
    """A request body that must never be read."""
    def readable(self):
        return True

    def read(self, *args):
        raise AssertionError('the upload body was read')

    readline = read
    readinto = read


class EarlyBodyRefusalTests(TempMediaMixin, APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='eb7b@example.com', password='SecurePassword123!', username='eb7b')
        self.gallery = Gallery.objects.create(photographer=self.user, title='E', slug='eb-7b')
        self.path = f'/api/v1/photos/{self.gallery.slug}/upload/'

    def raw_post(self, length):
        request = APIRequestFactory().generic('POST', self.path, b'', content_type='multipart/form-data; boundary=xyz')
        request.META['CONTENT_LENGTH'] = str(length)
        request.META['wsgi.input'] = ExplodingStream()
        request._stream = ExplodingStream()
        request.COOKIES['access_token'] = str(RefreshToken.for_user(self.user).access_token)
        return PhotoListUploadView.as_view()(request, gallery_slug=self.gallery.slug)

    def test_a_body_bigger_than_any_allowed_file_is_refused_unread(self):
        response = self.raw_post(50 * 1024 ** 3)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.data['code'], 'request_too_large')

    def test_an_account_with_no_storage_left_is_refused_unread(self):
        MediaAsset.objects.create(
            gallery=self.gallery, media_type=MediaAsset.MediaType.IMAGE, original_name='fill.jpg',
            original_file=SimpleUploadedFile('fill.jpg', b'x'), file_size=500 * 1024 ** 3, order=Decimal('1'),
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        response = self.raw_post(5 * 1024 ** 2)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'storage_limit_reached')


class PlanEdgeTests(TempMediaMixin, APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='pe7b@example.com', password='SecurePassword123!', username='pe7b')
        self.gallery = Gallery.objects.create(photographer=self.user, title='P', slug='pe-7b')

    def test_a_lapsed_subscription_is_not_the_paid_plan(self):
        grant_plan(self.user, name='Pro')
        UserSubscription.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(minutes=1))
        metrics = get_user_subscription_metrics(self.user)
        self.assertEqual(metrics['plan_name'], 'Free')
        self.assertIsNone(metrics['active_subscription'])

    def test_video_minutes_are_checked_again_under_the_lock(self):
        plan = grant_plan(self.user, name='Pro')
        plan.video_minutes = 1
        plan.save(update_fields=['video_minutes'])
        self.client.force_authenticate(self.user)
        clip = SimpleUploadedFile('clip.mp4', _make_video_bytes(duration=2), content_type='video/mp4')
        from apps.core import utils as core_utils
        real_probe = core_utils.probe_video_duration

        def probe_while_a_parallel_upload_lands(uploaded):
            seconds = real_probe(uploaded)
            # A second upload of the same account commits while this one is probing.
            MediaAsset.objects.create(
                gallery=self.gallery, media_type=MediaAsset.MediaType.VIDEO, original_name='parallel.mp4',
                original_file=SimpleUploadedFile('parallel.mp4', b'x'), file_size=1, duration=59,
                order=Decimal('2'), processing_status=MediaAsset.ProcessingStatus.READY,
            )
            return seconds

        with mock.patch('apps.photos.views.probe_video_duration', side_effect=probe_while_a_parallel_upload_lands), \
                self.captureOnCommitCallbacks(execute=False):
            response = self.client.post(f'/api/v1/photos/{self.gallery.slug}/upload/', {'video': [clip]},
                                        format='multipart')
        self.assertEqual(response.status_code, 403, getattr(response, 'data', None))
        self.assertEqual(MediaAsset.objects.filter(original_name='clip.mp4').count(), 0)
