# backend/apps/clients/tests/test_web_size_cache_6c.py
"""
Chunk 6-C -- exact-px Web Size, cached per (photo, px, watermark state), encoded by Celery.

  - a 1024 request serves a 1024px file, never the stored 1280 tier, and it is
    derived from the Download Master (not the original)
  - the second request for the same (photo, px, watermark state) is a storage
    read: nothing is decoded or encoded again (single photo AND ZIP)
  - the watermark state is part of the cache key: switching it on/off selects a
    different object and never serves the wrong one
  - the request thread never encodes: a cold size goes through the
    `generate_web_size` task (own queue); a worker that does not answer in time is a 503, not a
    wrong-size file
  - purge (5.1-D) removes the cached sizes with the photo / set / collection
  - the Original and the Download Master are never touched by any of it
"""
import io
import shutil
import tempfile
from unittest import mock

from celery.exceptions import TimeoutError as CeleryTimeoutError
from django.conf import settings
from django.core.files.base import ContentFile
from django.test import override_settings
from PIL import Image
from rest_framework import status

from apps.clients import web_size
from apps.clients.models import DownloadLog
from apps.clients.tests.test_download_access_flow import _zip_entries
from apps.clients.tests.test_download_pages_1r5b import jpeg_bytes, real_asset
from apps.clients.tests.test_single_photo_download_1r5d import SinglePhotoBase, body
from apps.core.storage import PrivateMediaStorage
from apps.core.watermark import build_watermark_spec
from apps.photos.models import MediaAsset
from apps.photos.purge import purge_assets, purge_gallery, purge_photo_set, run_purge, web_size_prefix
from apps.subscriptions.testing import grant_plan


def webp_bytes(size):
    out = io.BytesIO()
    Image.new('RGB', size, (30, 30, 30)).save(out, format='WEBP')
    return out.getvalue()


class WebSizeBase(SinglePhotoBase):
    with_pin = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp(prefix='kyapture-test-media-')
        cls.addClassCleanup(shutil.rmtree, cls.media_root, True)
        cls.enterClassContext(override_settings(MEDIA_ROOT=cls.media_root))
        patcher = mock.patch(
            'apps.photos.tasks.purge_storage_objects.delay',
            side_effect=lambda refs, prefixes=None: run_purge(refs, prefixes or []),
        )
        patcher.start()
        cls.addClassCleanup(patcher.stop)

    def setUp(self):
        super().setUp()
        MediaAsset.objects.filter(gallery=self.gallery).delete()     # the base's placeholder (non-image) files
        self.set_downloads(web={'enabled': True, 'px': 1024})
        self.photo, self.original = real_asset(self.gallery, 'big.jpg', self.ceremony, (3000, 2000), 4)
        self.access_token = self.token()

    def web(self, asset=None, **params):
        return self.get_photo(asset or self.photo, self.access_token, **{'resolution': 'web', **params})

    def cached_files(self, asset=None):
        prefix = web_size_prefix(asset or self.photo)
        try:
            return sorted(PrivateMediaStorage().listdir(prefix)[1])
        except FileNotFoundError:
            return []

    def counting_render(self):
        return mock.patch.object(web_size, 'render_web_jpeg', wraps=web_size.render_web_jpeg)


class ExactPixelTests(WebSizeBase):
    def test_a_1024_request_serves_1024px_not_the_stored_1280_tier(self):
        medium = webp_bytes((1280, 853))
        self.photo.medium_file.save('big_medium.webp', ContentFile(medium), save=True)
        response = self.web()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        served = body(response)
        image = Image.open(io.BytesIO(served))
        self.assertEqual((image.format, max(image.size)), ('JPEG', 1024))
        self.assertNotEqual(served, medium)
        self.assertNotEqual(max(Image.open(io.BytesIO(medium)).size), max(image.size))

    def test_each_choice_is_its_own_exact_size(self):
        for px in (2048, 1024, 640):
            self.set_downloads(web={'enabled': True, 'px': px})
            image = Image.open(io.BytesIO(body(self.web())))
            self.assertEqual(max(image.size), px)
        self.assertEqual(len(self.cached_files()), 3)

    def test_it_is_derived_from_the_download_master_not_the_original(self):
        master = jpeg_bytes((1800, 1200), color=(10, 120, 200))     # blue; the original is orange
        self.photo.download_file.delete(save=False)
        self.photo.download_file.save('big.master.jpg', ContentFile(master), save=True)
        image = Image.open(io.BytesIO(body(self.web()))).convert('RGB')
        red, _, blue = image.getpixel((image.width // 2, image.height // 2))
        self.assertGreater(blue, red)
        self.assertEqual(max(image.size), 1024)

    def test_original_and_master_are_untouched(self):
        self.photo.download_file.open('rb')
        master_before = self.photo.download_file.read()
        self.photo.download_file.close()
        body(self.web())
        self.photo.refresh_from_db()
        self.photo.original_file.open('rb')
        self.photo.download_file.open('rb')
        try:
            self.assertEqual(self.photo.original_file.read(), self.original)
            self.assertEqual(self.photo.download_file.read(), master_before)
        finally:
            self.photo.original_file.close()
            self.photo.download_file.close()


class CacheTests(WebSizeBase):
    def test_second_request_does_not_encode_again(self):
        with self.counting_render() as render:
            first = body(self.web())
            second = body(self.web())
            third = body(self.web())
        self.assertEqual(render.call_count, 1)
        self.assertEqual(first, second)
        self.assertEqual(second, third)
        self.assertEqual(len(self.cached_files()), 1)

    def test_the_preflight_prepares_it_and_the_download_is_then_free(self):
        with self.counting_render() as render:
            check = self.web(check='1')
            self.assertEqual(check.status_code, status.HTTP_200_OK)
            self.assertEqual(render.call_count, 1)
            self.assertEqual(DownloadLog.objects.count(), 0)
            response = self.web()
            body(response)
        self.assertEqual(render.call_count, 1)
        self.assertEqual(DownloadLog.objects.count(), 1)

    def test_a_zip_after_the_single_download_reuses_the_cache(self):
        single = body(self.web())
        with self.counting_render() as render:
            archive = self.zip(token=self.access_token, resolution='web')
        self.assertEqual(render.call_count, 0)
        entries = _zip_entries(archive)
        self.assertEqual(list(entries), ['big.jpg'])
        self.assertEqual(entries['big.jpg'], single)

    def test_a_second_zip_encodes_nothing(self):
        self.zip(token=self.access_token, resolution='web')
        with self.counting_render() as render:
            self.zip(token=self.token(email='second@example.com'), resolution='web')
        self.assertEqual(render.call_count, 0)

    def test_a_changed_source_is_not_served_from_the_old_cache(self):
        body(self.web())
        master = jpeg_bytes((1800, 1200), color=(10, 120, 200))
        self.photo.download_file.delete(save=False)
        self.photo.download_file.save('big.master2.jpg', ContentFile(master), save=True)
        with self.counting_render() as render:
            body(self.web())
        self.assertEqual(render.call_count, 1)
        self.assertEqual(len(self.cached_files()), 1)         # the superseded entry was removed


class WatermarkStateTests(WebSizeBase):
    def enable_watermark(self):
        grant_plan(self.photographer)
        self.gallery.watermark_enabled = True
        self.gallery.design_settings = dict(
            self.gallery.design_settings, watermark={'type': 'text', 'text': 'KYAPTURE TEST'},
        )
        self.gallery.save(update_fields=['watermark_enabled', 'design_settings'])
        self.gallery.refresh_from_db()

    def test_the_watermark_state_changes_the_cache_key(self):
        clean_key = web_size.cache_key(self.photo, 1024, None)
        self.enable_watermark()
        spec = build_watermark_spec(self.gallery)
        marked_key = web_size.cache_key(self.photo, 1024, spec)
        self.assertNotEqual(clean_key, marked_key)
        self.assertIn('-clean-', clean_key)
        self.assertIn(f'-{spec.signature}-', marked_key)
        self.assertNotEqual(
            marked_key,
            web_size.cache_key(self.photo, 1024, build_watermark_spec(self._edited_text('OTHER MARK'))),
        )

    def _edited_text(self, text):
        self.gallery.design_settings = dict(self.gallery.design_settings, watermark={'type': 'text', 'text': text})
        self.gallery.save(update_fields=['design_settings'])
        self.gallery.refresh_from_db()
        return self.gallery

    def test_turning_the_watermark_on_never_serves_the_clean_file(self):
        clean = body(self.web())
        self.enable_watermark()
        with self.counting_render() as render:
            marked = body(self.web())
        self.assertEqual(render.call_count, 1)
        self.assertNotEqual(clean, marked)
        self.assertEqual(len(self.cached_files()), 1)         # the clean size was superseded

    def test_turning_it_off_again_never_serves_the_watermarked_file(self):
        self.enable_watermark()
        marked = body(self.web())
        self.gallery.watermark_enabled = False
        self.gallery.save(update_fields=['watermark_enabled'])
        clean = body(self.web())
        self.assertNotEqual(clean, marked)
        self.assertEqual(max(Image.open(io.BytesIO(clean)).size), 1024)

    def test_high_resolution_and_original_are_never_watermarked(self):
        self.enable_watermark()
        master = body(self.get_photo(self.photo, self.access_token, resolution='download'))
        self.photo.download_file.open('rb')
        try:
            self.assertEqual(master, self.photo.download_file.read())
        finally:
            self.photo.download_file.close()
        grant_plan(self.photographer)
        self.set_downloads(web={'enabled': True, 'px': 1024}, high_res={'enabled': True, 'mode': 'original'})
        original = body(self.get_photo(self.photo, self.access_token, resolution='download'))
        self.assertEqual(original, self.original)


class CeleryBoundaryTests(WebSizeBase):
    def test_a_cold_size_is_requested_from_the_task_not_encoded_in_the_view(self):
        calls = []

        def fake_apply_async(args=None, **kwargs):
            calls.append(args)
            result = mock.Mock()
            result.get.return_value = None
            return result

        # A processed photo has its stored tiers; with none, nothing is served (7-B: never the original).
        self.photo.display_file.save('big.webp', ContentFile(b'DISPLAY-TIER'), save=True)
        with mock.patch('apps.clients.tasks.generate_web_size.apply_async', side_effect=fake_apply_async), \
                self.counting_render() as render:
            response = self.web()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1:], [1024, web_size.CLEAN])
        self.assertEqual(render.call_count, 0)                # the view itself never encoded
        self.assertEqual(response.status_code, status.HTTP_200_OK)   # None = undecodable -> legacy tier fallback
        self.assertEqual(b''.join(response.streaming_content), b'DISPLAY-TIER')

    def test_a_worker_that_does_not_answer_is_a_503_not_a_wrong_size_file(self):
        result = mock.Mock()
        result.get.side_effect = CeleryTimeoutError('too slow')
        with mock.patch('apps.clients.tasks.generate_web_size.apply_async', return_value=result):
            response = self.web()
            check = self.web(check='1')
        for refused in (response, check):
            self.assertEqual(refused.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertEqual(refused.data['code'], 'web_size_preparing')
            self.assertEqual(refused['Retry-After'], '3')
        self.assertEqual(DownloadLog.objects.count(), 0)

    def test_an_unreachable_broker_is_a_503_too(self):
        with mock.patch('apps.clients.tasks.generate_web_size.apply_async', side_effect=OSError('broker down')):
            self.assertEqual(self.web().status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_a_warm_request_never_touches_celery(self):
        body(self.web())
        with mock.patch('apps.clients.tasks.generate_web_size.apply_async') as apply_async:
            body(self.web())
        apply_async.assert_not_called()

    def test_the_task_has_its_own_bounded_queue(self):
        self.assertEqual(
            settings.CELERY_TASK_ROUTES['apps.clients.tasks.generate_web_size'], {'queue': settings.WEB_SIZE_QUEUE},
        )
        from config.celery import app
        route = app.amqp.router.route({}, 'apps.clients.tasks.generate_web_size')
        self.assertEqual(route['queue'].name, 'websize')

    def test_the_task_refuses_a_size_that_is_not_offered(self):
        from apps.clients.tasks import generate_web_size
        self.assertIsNone(generate_web_size(str(self.photo.id), 5000, web_size.CLEAN))
        self.assertEqual(self.cached_files(), [])


class PurgeTests(WebSizeBase):
    def listing(self, prefix):
        try:
            return PrivateMediaStorage().listdir(prefix)[1]
        except FileNotFoundError:
            return []

    def test_deleting_the_photo_removes_its_cached_sizes(self):
        for px in (2048, 1024, 640):
            self.set_downloads(web={'enabled': True, 'px': px})
            body(self.web())
        other, _ = real_asset(self.gallery, 'keep.jpg', self.ceremony, (3000, 2000), 5)
        body(self.web(other))
        self.assertEqual(len(self.cached_files()), 3)
        with self.captureOnCommitCallbacks(execute=True):
            purge_assets(self.gallery, MediaAsset.objects.filter(pk=self.photo.pk))
        self.assertEqual(self.listing(web_size_prefix(self.photo)), [])
        self.assertEqual(len(self.listing(web_size_prefix(other))), 1)     # another photo's cache is left alone

    def test_deleting_a_set_removes_its_cached_sizes(self):
        body(self.web())
        prefix = web_size_prefix(self.photo)
        self.assertEqual(len(self.listing(prefix)), 1)
        with self.captureOnCommitCallbacks(execute=True):
            purge_photo_set(self.gallery, self.ceremony)
        self.assertEqual(self.listing(prefix), [])

    def test_deleting_the_collection_removes_every_cached_size(self):
        second, _ = real_asset(self.gallery, 'second.jpg', self.ceremony, (3000, 2000), 5)
        body(self.web())
        body(self.web(second))
        prefixes = [web_size_prefix(self.photo), web_size_prefix(second)]
        self.assertTrue(all(len(self.listing(prefix)) == 1 for prefix in prefixes))
        with self.captureOnCommitCallbacks(execute=True):
            purge_gallery(self.gallery)
        for prefix in prefixes:
            self.assertEqual(self.listing(prefix), [])
