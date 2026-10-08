# backend/apps/clients/tests/test_gallery_lock_7g.py
"""
7G (reviewer 7R-2, R1): the gallery row lock added in 7F must not wait for
uploads, and must not form a lock cycle with them.

Postgres: every INSERT of a child row (a MediaAsset, a session, a log) takes
FOR KEY SHARE on the gallery row it points to, and keeps it until its
transaction ends. 7F's select_for_update() took FOR UPDATE, which conflicts
with it, so a PIN use or an owner save waited for any upload in progress, and
a publishing PATCH (gallery lock, then a notification row for the
photographer) and an upload (photographer lock, then asset rows) could
deadlock. The lock is now FOR NO KEY UPDATE (writers still queue behind each
other), the "published" notification is written after commit, and bcrypt
runs before the lock is taken.

Real threads and real Postgres row locks, so this is a TransactionTestCase.
No serialized_rollback: setUp re-creates the plan rows (ensure_seed_plans).
"""
import io
import shutil
import tempfile
import threading
import time
from unittest import mock

import bcrypt
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.subscriptions.testing import ensure_seed_plans

from apps.clients import views as client_views
from apps.galleries import serializers as gallery_serializers, views as gallery_views
from apps.galleries.models import Gallery
from apps.photos import views as photo_views
from apps.photos.models import MediaAsset
from apps.users.models import Notification

User = get_user_model()
PIN = '4821'


def fast_hash(value):
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt(4)).decode()


class GalleryLockBase(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.assertEqual(ensure_seed_plans(), 4)
        patcher = mock.patch.object(client_views.PasswordUnlockRateThrottle, 'allow_request', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.photographer = User.objects.create_user(
            email='lock7g@kyapture.com', password='SecurePassword123!', username='lock7g',
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer, title='Lock 7G', slug='lock-7g',
            is_published=True, is_active=True, allow_download=True,
            download_pin_hash=fast_hash(PIN),
            design_settings={'privacy': {'pin_limit': 10, 'pin_use_count': 0}},
        )
        self.owner = APIClient()
        self.owner.force_authenticate(user=self.photographer)

    def insert_asset(self, name):
        return MediaAsset.objects.create(
            gallery_id=self.gallery.pk, media_type=MediaAsset.MediaType.IMAGE, original_name=name,
            file_size=1024, original_file=f'photographers/x/galleries/x/originals/{name}',
            processing_status=MediaAsset.ProcessingStatus.READY,
        )

    def run_in_thread(self, fn, result, key):
        def target():
            try:
                result[key] = fn()
            except Exception as exc:          # recorded, asserted by the test
                result[key] = exc
            finally:
                connection.close()
        thread = threading.Thread(target=target)
        thread.start()
        return thread


class UploadInProgressTests(GalleryLockBase):
    """Thread A is an upload: it inserted a MediaAsset and has not committed yet."""

    def timed_while_an_upload_is_open(self, request):
        inserted, release = threading.Event(), threading.Event()
        result = {}

        def upload():
            with transaction.atomic():
                self.insert_asset('open-upload.jpg')
                inserted.set()
                release.wait(10)
            return 'committed'

        holder = self.run_in_thread(upload, result, 'upload')
        try:
            self.assertTrue(inserted.wait(5))
            started = time.monotonic()
            worker = self.run_in_thread(request, result, 'request')
            worker.join(3)                     # 7F's FOR UPDATE waited here until the upload ended
            elapsed = time.monotonic() - started
        finally:
            release.set()
            holder.join()
            worker.join()
            connection.close()
        self.assertEqual(result['upload'], 'committed')
        return elapsed, result['request']

    def test_a_pin_use_answers_while_an_upload_is_open(self):
        elapsed, response = self.timed_while_an_upload_is_open(
            lambda: APIClient(REMOTE_ADDR='192.0.2.70').post(
                '/api/v1/public/lock7g/lock-7g/download-access/', {'email': 'g@example.com', 'pin': PIN},
                format='json'),
        )
        print(f'\n  7G PIN use while an upload is open: {elapsed:.3f}s -> {response.status_code}')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', response))
        self.assertLess(elapsed, 1.0)
        self.assertEqual(Gallery.objects.get(pk=self.gallery.pk).design_settings['privacy']['pin_use_count'], 1)

    def test_an_owner_settings_save_answers_while_an_upload_is_open(self):
        elapsed, response = self.timed_while_an_upload_is_open(
            lambda: self.owner.patch('/api/v1/galleries/lock-7g/', {'title': 'Renamed'}, format='json'),
        )
        print(f'\n  7G owner save while an upload is open: {elapsed:.3f}s -> {response.status_code}')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', response))
        self.assertLess(elapsed, 1.0)
        self.assertEqual(Gallery.objects.get(pk=self.gallery.pk).title, 'Renamed')

    def test_setting_a_new_pin_answers_while_an_upload_is_open(self):
        elapsed, response = self.timed_while_an_upload_is_open(
            lambda: self.owner.post('/api/v1/galleries/lock-7g/set-download-pin/', {'pin': '9999'}, format='json'),
        )
        print(f'\n  7G set-download-pin while an upload is open: {elapsed:.3f}s -> {response.status_code}')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', response))
        self.assertLess(elapsed, 1.0)


class PublishDuringUploadTests(GalleryLockBase):
    def test_publishing_while_an_upload_holds_the_photographer_lock_does_not_deadlock(self):
        """
        A = an upload: locks the photographer row (photos/views.py), then inserts
        an asset. B = the owner publishes. 7F: B held the gallery lock and waited
        for the photographer row (notification insert) while A waited for the
        gallery row (asset insert), and Postgres aborted one of them.
        """
        Gallery.objects.filter(pk=self.gallery.pk).update(is_published=False)
        locked, release = threading.Event(), threading.Event()
        result = {}

        def upload():
            with transaction.atomic():
                User.objects.select_for_update().only('pk').get(pk=self.photographer.pk)
                locked.set()
                release.wait(10)                     # B publishes meanwhile
                self.insert_asset('during-publish.jpg')
            return 'committed'

        holder = self.run_in_thread(upload, result, 'upload')
        self.assertTrue(locked.wait(5))
        publisher = self.run_in_thread(
            lambda: self.owner.patch('/api/v1/galleries/lock-7g/', {'is_published': True}, format='json'),
            result, 'publish',
        )
        time.sleep(0.5)                              # B is inside its PATCH now
        release.set()
        holder.join(15)
        publisher.join(15)
        connection.close()
        print(f"\n  7G publish during an upload: upload={result.get('upload')!r}, "
              f"publish={getattr(result.get('publish'), 'status_code', result.get('publish'))!r}")
        self.assertEqual(result['upload'], 'committed')
        self.assertEqual(result['publish'].status_code, 200, getattr(result['publish'], 'data', None))
        self.assertTrue(Gallery.objects.get(pk=self.gallery.pk).is_published)
        self.assertTrue(MediaAsset.objects.filter(gallery_id=self.gallery.pk, original_name='during-publish.jpg')
                        .exists())
        self.assertEqual(Notification.objects.filter(
            user=self.photographer, kind=Notification.Kind.PUBLISHED, gallery_id=self.gallery.pk).count(), 1)

    def test_a_publish_that_fails_sends_no_notification(self):
        """on_commit: a PATCH that fails after the publish step (and rolls back) tells the photographer nothing."""
        Gallery.objects.filter(pk=self.gallery.pk).update(is_published=False)
        # The first call (before save) works; the second (after the publish step) fails.
        with mock.patch.object(gallery_views, '_watermark_state', side_effect=['same', RuntimeError('boom')]):
            client = APIClient(raise_request_exception=False)
            client.force_authenticate(user=self.photographer)
            response = client.patch('/api/v1/galleries/lock-7g/', {'is_published': True}, format='json')
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Gallery.objects.get(pk=self.gallery.pk).is_published)
        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.PUBLISHED).exists())


class RealUploadTests(GalleryLockBase):
    """
    The real upload endpoint, paused inside its transaction after it locked the
    photographer row (while it stores the first file). A PIN use and a publish
    must not wait for the rest of the batch.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = tempfile.mkdtemp(prefix='kyapture-7g-media-')
        cls.addClassCleanup(shutil.rmtree, root, True)
        cls.enterClassContext(override_settings(MEDIA_ROOT=root))

    def timed_during_a_real_upload(self, request):
        paused, release = threading.Event(), threading.Event()
        real_strip = photo_views.strip_exif_gps
        result = {}

        def slow_strip(file_data):
            paused.set()
            release.wait(10)
            return real_strip(file_data)

        def upload():
            buf = io.BytesIO()
            Image.new('RGB', (32, 24), 'teal').save(buf, 'JPEG')
            return self.owner.post('/api/v1/photos/lock-7g/upload/',
                                   {'image': [SimpleUploadedFile('a.jpg', buf.getvalue(), content_type='image/jpeg')]},
                                   format='multipart')

        with mock.patch.object(photo_views, 'strip_exif_gps', side_effect=slow_strip), \
                mock.patch.object(photo_views.process_photo_asset, 'delay'):
            holder = self.run_in_thread(upload, result, 'upload')
            try:
                self.assertTrue(paused.wait(10))
                started = time.monotonic()
                worker = self.run_in_thread(request, result, 'request')
                worker.join(3)
                elapsed = time.monotonic() - started
            finally:
                release.set()
                holder.join()
                worker.join()
                connection.close()
        self.assertEqual(result['upload'].status_code, 202, getattr(result['upload'], 'data', result['upload']))
        return elapsed, result['request']

    def test_a_publish_answers_during_a_real_upload(self):
        Gallery.objects.filter(pk=self.gallery.pk).update(is_published=False)
        elapsed, response = self.timed_during_a_real_upload(
            lambda: self.owner.patch('/api/v1/galleries/lock-7g/', {'is_published': True}, format='json'),
        )
        print(f'\n  7G publish during a real upload: {elapsed:.3f}s -> {response.status_code}')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', response))
        self.assertLess(elapsed, 1.0)
        self.assertEqual(Notification.objects.filter(
            user=self.photographer, kind=Notification.Kind.PUBLISHED, gallery_id=self.gallery.pk).count(), 1)

    def test_a_second_upload_still_waits_for_the_first(self):
        """NO KEY UPDATE on the photographer row still serialises uploads (the storage decision)."""
        paused, release = threading.Event(), threading.Event()
        real_strip = photo_views.strip_exif_gps
        first = []
        result = {}

        def slow_first_strip(file_data):
            if not first:
                first.append(1)
                paused.set()
                release.wait(10)
            return real_strip(file_data)

        def upload(name):
            buf = io.BytesIO()
            Image.new('RGB', (32, 24), 'teal').save(buf, 'JPEG')
            return lambda: self.owner.post(
                '/api/v1/photos/lock-7g/upload/',
                {'image': [SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')]}, format='multipart')

        with mock.patch.object(photo_views, 'strip_exif_gps', side_effect=slow_first_strip), \
                mock.patch.object(photo_views.process_photo_asset, 'delay'):
            a = self.run_in_thread(upload('a.jpg'), result, 'a')
            try:
                self.assertTrue(paused.wait(10))
                b = self.run_in_thread(upload('b.jpg'), result, 'b')
                b.join(1.0)
                second_waited = b.is_alive()
            finally:
                release.set()
                a.join()
                b.join()
                connection.close()
        self.assertTrue(second_waited, result)
        self.assertEqual((result['a'].status_code, result['b'].status_code), (202, 202))
        self.assertEqual(MediaAsset.objects.filter(gallery_id=self.gallery.pk).count(), 2)

    def test_a_pin_use_answers_during_a_real_upload(self):
        elapsed, response = self.timed_during_a_real_upload(
            lambda: APIClient(REMOTE_ADDR='192.0.2.71').post(
                '/api/v1/public/lock7g/lock-7g/download-access/', {'email': 'g@example.com', 'pin': PIN},
                format='json'),
        )
        print(f'\n  7G PIN use during a real upload: {elapsed:.3f}s -> {response.status_code}')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', response))
        self.assertLess(elapsed, 1.0)


class PasswordHashOutsideLockTests(GalleryLockBase):
    def test_the_gallery_password_is_hashed_before_the_row_lock(self):
        real = bcrypt.hashpw
        calls = []

        def spying(*args, **kwargs):
            calls.append(connection.in_atomic_block)
            return real(*args, **kwargs)

        with mock.patch.object(gallery_serializers.bcrypt, 'hashpw', side_effect=spying):
            response = self.owner.patch(
                '/api/v1/galleries/lock-7g/', {'is_password_protected': True, 'password': 'venue-2026'},
                format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(calls, [False], calls)        # one hash, and no transaction (or lock) open
        stored = Gallery.objects.get(pk=self.gallery.pk).password_hash
        self.assertTrue(bcrypt.checkpw(b'venue-2026', stored.encode()))
