# backend/apps/clients/tests/test_downloads_6d.py
"""
Chunk 6-D -- every download path with the REAL Download Master encoder.

Unlike the older download tests (fake master bytes) every photo here goes through the
production pipeline (`process_image_pipeline`: sRGB, 3600 px cap, jpegli q90 / Pillow
fallback), and the bytes that come back are decoded and measured.

  single      High Resolution (Free master / Pro Original), Web Size at 2048/1024/640
  ZIP         High Resolution, Web Size, Pro Original
  ZIP parts   the part limit splits a download; the parts together hold every photo once
  watermark   on/off for Web Size; High Resolution and Original never carry it
  Original    Pro: byte-identical to the upload (SHA-256); Free can never reach it by API
  failures    the encoder / a stored file failing mid-ZIP fails the job cleanly: no partial
              ZIP is stored or served, no activity row, no email; fallbacks that are meant to work do
"""
import glob
import hashlib
import io
import os
import tempfile
import zipfile
from unittest import mock, skipUnless

import piexif
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework import status

from apps.clients import web_size
from apps.clients.models import DownloadJob, DownloadLog
from apps.clients.tests.test_single_photo_download_1r5d import body
from apps.clients.tests.test_web_size_cache_6c import WebSizeBase
from apps.core import utils as core_utils
from apps.core.storage import PrivateMediaStorage
from apps.core.utils import process_image_pipeline
from apps.photos.models import MediaAsset
from apps.subscriptions.testing import grant_plan

JPEGLI = skipUnless(os.path.exists(core_utils.CJPEGLI_BIN), 'cjpegli is not installed on this host')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def photo_like(size):
    """Smooth gradient + noise: encodes like a photograph, unlike a flat colour."""
    gradient = Image.linear_gradient('L').resize(size)
    noise = Image.effect_noise(size, 24)
    channel = Image.blend(gradient, noise, 0.35)
    return Image.merge('RGB', (channel, channel.transpose(Image.Transpose.FLIP_LEFT_RIGHT), noise))


def upload_jpeg(size, orientation=None):
    kwargs = {}
    if orientation:
        kwargs['exif'] = piexif.dump({'0th': {piexif.ImageIFD.Orientation: orientation}})
    out = io.BytesIO()
    photo_like(size).save(out, format='JPEG', quality=92, **kwargs)
    return out.getvalue()


def read_field(field):
    field.open('rb')
    try:
        return field.read()
    finally:
        field.close()


def dims(data):
    with Image.open(io.BytesIO(data)) as image:
        return image.format, image.size


class PipelineBase(WebSizeBase):
    """Free photographer, a gallery whose photos come out of the real image pipeline."""

    def setUp(self):
        super().setUp()
        MediaAsset.objects.filter(gallery=self.gallery).delete()
        self.uploads = {}              # asset id -> the exact bytes that were uploaded
        self.big = self.pipeline_asset('big.jpg', (4200, 2800), 1)      # above the 3600 px cap
        self.mid = self.pipeline_asset('mid.jpg', (3000, 2000), 2)      # between the web tiers and the cap
        self.small = self.pipeline_asset('small.jpg', (1600, 1067), 3)  # below every choice but 640
        self.assets = [self.big, self.mid, self.small]

    def pipeline_asset(self, name, size, order, orientation=None, build_master=True):
        raw = upload_jpeg(size, orientation)
        display, medium, thumbnail, master, blurhash = process_image_pipeline(SimpleUploadedFile(name, raw, 'image/jpeg'))
        asset = MediaAsset(
            gallery=self.gallery, media_type=MediaAsset.MediaType.IMAGE, original_name=name, file_size=len(raw),
            order=order, photo_set=self.ceremony, processing_status=MediaAsset.ProcessingStatus.READY, blurhash=blurhash,
        )
        asset.original_file.save(name, ContentFile(raw), save=False)
        asset.display_file.save(display.name, display, save=False)
        asset.medium_file.save(medium.name, medium, save=False)
        asset.thumbnail_file.save(thumbnail.name, thumbnail, save=False)
        if build_master and master is not None:
            asset.download_file.save(master.name, master, save=False)
        asset.save()
        self.uploads[asset.id] = raw
        return asset

    # ── requests ──────────────────────────────────────────────────────────
    def single(self, asset, resolution, **params):
        return self.get_photo(asset, self.access_token, resolution=resolution, **params)

    def prepare(self, **payload):
        """POST download/ -> (job, [bytes of every part])."""
        response = self.client.post(
            f'{self.base}download/', {'download_token': self.access_token, **payload}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, getattr(response, 'data', None))
        job = DownloadJob.objects.get(pk=response.data['job_id'])
        listing = self.client.get(
            f'{self.base}download-jobs/{job.id}/', {'download_token': self.access_token},
        )
        parts = []
        if listing.data['state'] == 'ready':
            for entry in listing.data['files']:
                parts.append(b''.join(self.client.get(entry['url']).streaming_content))
        return job, parts

    @staticmethod
    def entries(zip_bytes):
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            assert archive.testzip() is None
            return {name: archive.read(name) for name in archive.namelist()}

    def zip_entries(self, **payload):
        job, parts = self.prepare(**payload)
        self.assertEqual(job.state, DownloadJob.State.READY, job.error_code)
        self.assertEqual(len(parts), 1)
        return self.entries(parts[0])

    def enable_watermark(self):
        grant_plan(self.photographer)
        self.gallery.watermark_enabled = True
        self.gallery.design_settings = dict(
            self.gallery.design_settings, watermark={'type': 'text', 'text': 'KYAPTURE 6D'},
        )
        self.gallery.save(update_fields=['watermark_enabled', 'design_settings'])
        self.gallery.refresh_from_db()

    def use_original_mode(self):
        self.set_downloads(
            web={'enabled': True, 'px': 1024}, high_res={'enabled': True, 'mode': 'original'},
        )

    # ── assertions ────────────────────────────────────────────────────────
    def assert_originals_intact(self):
        for asset in self.assets:
            asset.refresh_from_db()
            self.assertEqual(sha(read_field(asset.original_file)), sha(self.uploads[asset.id]), asset.original_name)

    def stored_job_files(self, job):
        try:
            return PrivateMediaStorage().listdir(f'download_jobs/{job.id}')[1]
        except FileNotFoundError:
            return []


class HighResolutionTests(PipelineBase):
    def test_single_free_download_is_the_3600_master_not_the_original(self):
        response = self.single(self.big, 'download')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = body(response)
        self.assertEqual(dims(payload), ('JPEG', (3600, 2400)))
        self.assertEqual(payload, read_field(self.big.download_file))
        self.assertNotEqual(sha(payload), sha(self.uploads[self.big.id]))
        self.assertEqual(DownloadLog.objects.get().resolution, DownloadLog.Resolution.DOWNLOAD)
        self.assert_originals_intact()

    def test_no_photo_is_ever_upscaled_or_larger_than_3600(self):
        for asset, expected in ((self.big, (3600, 2400)), (self.mid, (3000, 2000)), (self.small, (1600, 1067))):
            with self.subTest(asset.original_name):
                payload = body(self.single(asset, 'download'))
                self.assertEqual(dims(payload)[1], expected)

    def test_a_small_photo_whose_reencode_is_not_smaller_may_be_served_as_itself(self):
        # 6-A rule: no master is made when it would be larger than the original and the source is within the cap.
        bare = self.pipeline_asset('bare.jpg', (1200, 800), 9, build_master=False)
        payload = body(self.single(bare, 'download'))
        self.assertEqual(dims(payload)[1], (1200, 800))

    def test_portrait_orientation_is_applied_in_the_master(self):
        rotated = self.pipeline_asset('rot.jpg', (3000, 2000), 8, orientation=6)    # camera held upright
        width, height = dims(body(self.single(rotated, 'download')))[1]
        self.assertEqual((width, height), (2000, 3000))
        self.assertEqual(self.uploads[rotated.id], read_field(rotated.original_file))   # the original keeps its raw layout

    def test_the_zip_holds_exactly_the_stored_masters(self):
        entries = self.zip_entries(resolution='download')
        self.assertEqual(sorted(entries), ['big.jpg', 'mid.jpg', 'small.jpg'])
        for asset in self.assets:
            self.assertEqual(entries[asset.original_name], read_field(asset.download_file))
        self.assertEqual(dims(entries['big.jpg'])[1], (3600, 2400))
        self.assert_originals_intact()

    @JPEGLI
    def test_the_master_is_far_smaller_than_the_original_and_decodes_cleanly(self):
        master = read_field(self.big.download_file)
        self.assertLess(len(master), len(self.uploads[self.big.id]))
        with Image.open(io.BytesIO(master)) as image:
            image.load()
            self.assertEqual(image.mode, 'RGB')
            self.assertTrue(image.info.get('progressive') or image.info.get('progression'))

    def test_the_encoder_falling_back_to_pillow_still_downloads_at_3600(self):
        with mock.patch.object(core_utils, 'CJPEGLI_BIN', '/nonexistent/cjpegli'):
            fallback = self.pipeline_asset('fallback.jpg', (4200, 2800), 7)
        payload = body(self.single(fallback, 'download'))
        self.assertEqual(dims(payload), ('JPEG', (3600, 2400)))
        entries = self.zip_entries(resolution='download', asset_ids=[str(fallback.id)])
        self.assertEqual(entries['fallback.jpg'], payload)


class WebSizeTests(PipelineBase):
    def test_every_choice_is_exact_for_single_and_zip_and_never_upscales(self):
        for px in (2048, 1024, 640):
            self.set_downloads(web={'enabled': True, 'px': px})
            entries = self.zip_entries(resolution='web')
            for asset in self.assets:
                with self.subTest(px=px, photo=asset.original_name):
                    single = body(self.single(asset, 'web'))
                    fmt, size = dims(single)
                    self.assertEqual(fmt, 'JPEG')
                    self.assertEqual(max(size), min(px, max(Image.open(asset.original_file).size)))
                    self.assertEqual(entries[asset.original_name], single)       # ZIP == single, byte for byte
        self.assert_originals_intact()

    def test_web_size_is_made_from_the_master_and_smaller_than_it(self):
        web = body(self.single(self.big, 'web'))
        self.assertLess(len(web), len(read_field(self.big.download_file)))

    def test_portrait_orientation_is_applied_in_web_size(self):
        rotated = self.pipeline_asset('rot.jpg', (3000, 2000), 8, orientation=6)
        width, height = dims(body(self.single(rotated, 'web')))[1]
        self.assertEqual((width, height), (683, 1024))

    def test_watermark_on_and_off(self):
        clean = body(self.single(self.mid, 'web'))
        clean_zip = self.zip_entries(resolution='web')['mid.jpg']
        self.enable_watermark()
        marked = body(self.single(self.mid, 'web'))
        marked_zip = self.zip_entries(resolution='web')['mid.jpg']
        self.assertNotEqual(clean, marked)
        self.assertEqual(marked_zip, marked)
        self.assertEqual(dims(marked)[1], dims(clean)[1])
        # High Resolution never carries it, before or after.
        self.assertEqual(body(self.single(self.mid, 'download')), read_field(self.mid.download_file))
        self.assertEqual(self.zip_entries(resolution='download')['mid.jpg'], read_field(self.mid.download_file))
        # Off again: the clean file is served, not the cached watermarked one.
        self.gallery.watermark_enabled = False
        self.gallery.save(update_fields=['watermark_enabled'])
        self.assertEqual(body(self.single(self.mid, 'web')), clean)
        self.assertEqual(self.zip_entries(resolution='web')['mid.jpg'], clean)
        self.assert_originals_intact()


class ProOriginalTests(PipelineBase):
    def setUp(self):
        super().setUp()
        grant_plan(self.photographer)
        self.use_original_mode()

    def test_single_original_is_byte_identical_to_the_upload(self):
        for asset in self.assets:
            with self.subTest(asset.original_name):
                payload = body(self.single(asset, 'download'))
                self.assertEqual(sha(payload), sha(self.uploads[asset.id]))
        self.assertEqual({log.resolution for log in DownloadLog.objects.all()}, {DownloadLog.Resolution.ORIGINAL})
        self.assert_originals_intact()

    def test_zip_original_is_byte_identical_to_the_upload(self):
        entries = self.zip_entries(resolution='download')
        for asset in self.assets:
            self.assertEqual(sha(entries[asset.original_name]), sha(self.uploads[asset.id]))
        self.assertEqual(dims(entries['big.jpg'])[1], (4200, 2800))             # the real, uncapped file

    def test_original_is_never_watermarked_or_recompressed(self):
        self.enable_watermark()
        self.use_original_mode()
        payload = body(self.single(self.big, 'download'))
        self.assertEqual(sha(payload), sha(self.uploads[self.big.id]))

    def test_web_size_stays_a_derivative_for_a_pro_photographer(self):
        web = body(self.single(self.big, 'web'))
        self.assertEqual(max(dims(web)[1]), 1024)
        self.assertNotEqual(sha(web), sha(self.uploads[self.big.id]))

    def test_original_parts_hold_every_original_exactly_once(self):
        limit = max(len(raw) for raw in self.uploads.values()) + 1024        # one photo per part at most
        with override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=limit):
            job, parts = self.prepare(resolution='download')
        self.assertGreater(len(parts), 1)
        seen = {}
        for part in parts:
            seen.update(self.entries(part))
        for asset in self.assets:
            self.assertEqual(sha(seen[asset.original_name]), sha(self.uploads[asset.id]))


class FreeCannotReachTheOriginalTests(PipelineBase):
    def test_a_raw_original_request_is_refused_for_free_and_pro_alike(self):
        for pro in (False, True):
            if pro:
                grant_plan(self.photographer)
            single = self.single(self.big, 'original')
            self.assertEqual((single.status_code, single.data['code']), (400, 'invalid_resolution'))
            zipped = self.client.post(
                f'{self.base}download/', {'download_token': self.access_token, 'resolution': 'original'}, format='json',
            )
            self.assertEqual((zipped.status_code, zipped.data['code']), (400, 'invalid_resolution'))
        self.assertFalse(DownloadJob.objects.exists())
        self.assertFalse(DownloadLog.objects.exists())

    def test_a_stored_original_setting_does_nothing_without_a_plan_that_includes_it(self):
        self.use_original_mode()                       # forced in the DB, as after a downgrade
        single = body(self.single(self.big, 'download'))
        self.assertEqual(single, read_field(self.big.download_file))
        self.assertNotEqual(sha(single), sha(self.uploads[self.big.id]))
        entries = self.zip_entries(resolution='download')
        self.assertEqual(entries['big.jpg'], single)
        self.assertEqual({log.resolution for log in DownloadLog.objects.all()}, {DownloadLog.Resolution.DOWNLOAD})

    def test_a_lapsed_pro_plan_falls_back_to_the_master(self):
        grant_plan(self.photographer)
        self.use_original_mode()
        self.assertEqual(sha(body(self.single(self.big, 'download'))), sha(self.uploads[self.big.id]))
        self.photographer.subscription.delete()
        self.assertEqual(body(self.single(self.big, 'download')), read_field(self.big.download_file))

    def test_the_public_gallery_payload_never_carries_an_original_link(self):
        payload = self.client.get(self.base).data
        flat = str(payload).lower()
        self.assertNotIn('original_url', flat)
        self.assertNotIn('original_file', flat)
        self.assertNotIn('/original', flat)

    def test_free_never_gets_more_than_3600_even_when_the_master_is_missing_and_cannot_be_made(self):
        bare = self.pipeline_asset('bare-big.jpg', (4200, 2800), 9, build_master=False)
        with mock.patch('apps.clients.views.process_download_master', side_effect=RuntimeError('encoder down')):
            single = self.single(bare, 'download')
            check = self.single(bare, 'download', check='1')
        for refused in (single, check):
            self.assertEqual(refused.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertEqual(refused.data['code'], 'download_master_unavailable')
        self.assertFalse(DownloadLog.objects.exists())

    def test_a_small_original_may_stand_in_for_a_master_that_cannot_be_made(self):
        bare = self.pipeline_asset('bare-small.jpg', (1200, 800), 9, build_master=False)
        with mock.patch('apps.clients.views.process_download_master', side_effect=RuntimeError('encoder down')):
            payload = body(self.single(bare, 'download'))
        self.assertEqual(sha(payload), sha(self.uploads[bare.id]))


class ZipPartsTests(PipelineBase):
    def part_limit_for(self, sizes, per_part=2):
        ordered = sorted(sizes, reverse=True)
        return sum(ordered[:per_part]) + 1024

    def test_a_download_over_the_limit_splits_into_named_parts_holding_every_photo_once(self):
        extra = [self.pipeline_asset(f'extra{i}.jpg', (3000, 2000), 10 + i) for i in range(3)]
        self.assets.extend(extra)
        masters = {a.original_name: read_field(a.download_file) for a in self.assets}
        limit = self.part_limit_for([len(m) for m in masters.values()])
        with override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=limit):
            job, parts = self.prepare(resolution='download')
        self.assertEqual(job.state, DownloadJob.State.READY)
        self.assertGreaterEqual(len(parts), 2)
        self.assertEqual(
            [f['name'] for f in job.files],
            [f'flow-gallery-photo-download-{n}of{len(parts)}.zip' for n in range(1, len(parts) + 1)],
        )
        seen = {}
        for part, meta in zip(parts, job.files):
            entries = self.entries(part)
            self.assertEqual(meta['photo_count'], len(entries))
            self.assertTrue(set(seen).isdisjoint(entries))                  # no photo twice
            self.assertLessEqual(sum(len(v) for v in entries.values()), limit)
            seen.update(entries)
        self.assertEqual(seen, masters)                                      # nothing lost, nothing altered
        self.assert_originals_intact()

    def test_web_size_parts_hold_exact_px_files(self):
        sizes = []
        for asset in self.assets:
            sizes.append(len(body(self.single(asset, 'web'))))
        limit = max(sizes) + 1024
        with override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=limit):
            job, parts = self.prepare(resolution='web')
        self.assertGreater(len(parts), 1)
        seen = {}
        for part in parts:
            seen.update(self.entries(part))
        self.assertEqual(sorted(seen), ['big.jpg', 'mid.jpg', 'small.jpg'])
        for name, data in seen.items():
            self.assertLessEqual(max(dims(data)[1]), 1024)

    def test_a_single_photo_larger_than_the_limit_still_gets_its_own_part(self):
        with override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=1):
            job, parts = self.prepare(resolution='download')
        self.assertEqual(len(parts), len(self.assets))
        self.assertEqual(sum(len(self.entries(part)) for part in parts), len(self.assets))

    def test_the_default_limit_is_two_gigabytes_and_a_normal_download_is_one_part(self):
        self.assertEqual(core_utils_part_limit(), 2 * 1024 ** 3)
        job, parts = self.prepare(resolution='download')
        self.assertEqual(len(parts), 1)
        self.assertEqual(job.files[0]['name'], 'flow-gallery-photo-download-1of1.zip')


def core_utils_part_limit():
    from django.conf import settings
    return int(settings.DOWNLOAD_ZIP_PART_MAX_BYTES)


class JobReuseTests(PipelineBase):
    """An identical request reuses a ready ZIP, but never one built under a different setting."""

    def job_id(self, **payload):
        response = self.client.post(
            f'{self.base}download/', {'download_token': self.access_token, **payload}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        return response.data['job_id']

    def test_an_identical_request_is_one_job(self):
        self.assertEqual(self.job_id(resolution='web'), self.job_id(resolution='web'))
        self.assertEqual(DownloadJob.objects.count(), 1)

    def test_switching_the_watermark_builds_a_new_zip_each_time(self):
        clean = self.job_id(resolution='web')
        self.enable_watermark()
        marked = self.job_id(resolution='web')
        self.assertNotEqual(clean, marked)
        self.assertEqual(marked, self.job_id(resolution='web'))
        self.gallery.watermark_enabled = False
        self.gallery.save(update_fields=['watermark_enabled'])
        self.assertEqual(self.job_id(resolution='web'), clean)         # the clean one is still valid and is reused

    def test_changing_the_web_size_px_builds_a_new_zip(self):
        first = self.job_id(resolution='web')
        self.set_downloads(web={'enabled': True, 'px': 640})
        second = self.job_id(resolution='web')
        self.assertNotEqual(first, second)
        entries = self.entries(b''.join(self.client.get(self.client.get(
            f'{self.base}download-jobs/{second}/', {'download_token': self.access_token},
        ).data['files'][0]['url']).streaming_content))
        self.assertTrue(all(max(dims(data)[1]) <= 640 for data in entries.values()))

    def test_a_zip_made_for_a_pro_original_is_not_handed_out_after_the_plan_lapses(self):
        grant_plan(self.photographer)
        self.use_original_mode()
        original_job = self.job_id(resolution='download')
        self.photographer.subscription.delete()
        master_job = self.job_id(resolution='download')
        self.assertNotEqual(original_job, master_job)
        entries = self.entries(b''.join(self.client.get(self.client.get(
            f'{self.base}download-jobs/{master_job}/', {'download_token': self.access_token},
        ).data['files'][0]['url']).streaming_content))
        self.assertEqual(dims(entries['big.jpg'])[1], (3600, 2400))


class FailureInjectionTests(PipelineBase):
    """The encoder (or a stored file) failing part-way through a ZIP: fail cleanly, serve nothing."""

    def temp_zips(self):
        return set(glob.glob(os.path.join(tempfile.gettempdir(), '*.zip')))

    def assert_failed_cleanly(self, job, temp_before):
        job.refresh_from_db()
        self.assertEqual(job.state, DownloadJob.State.FAILED)
        self.assertEqual(job.error_code, 'prepare_failed')
        self.assertEqual(job.files, [])
        self.assertEqual(self.stored_job_files(job), [])                     # no part left in private storage
        self.assertEqual(self.temp_zips(), temp_before)                       # no temp part left on disk
        self.assertFalse(DownloadLog.objects.exists())                        # nothing was delivered
        status_response = self.client.get(f'{self.base}download-jobs/{job.id}/', {'download_token': self.access_token})
        self.assertEqual(status_response.data['state'], 'failed')
        self.assertEqual(status_response.data['files'], [])
        self.assertNotIn('Traceback', str(status_response.data))
        file_url = f'{self.base}download-jobs/{job.id}/files/0/'
        self.assertNotEqual(self.client.get(file_url, {'download_token': self.access_token}).status_code, 200)

    def test_the_web_size_encoder_failing_on_the_third_photo_fails_the_job(self):
        self.enable_watermark()
        extra = [self.pipeline_asset(f'extra{i}.jpg', (3000, 2000), 10 + i) for i in range(2)]
        calls = {'n': 0}
        real = web_size.apply_watermark

        def flaky(img, spec):
            calls['n'] += 1
            if calls['n'] == 3:
                raise MemoryError('encoder died')
            return real(img, spec)

        before = self.temp_zips()
        with mock.patch.object(web_size, 'apply_watermark', side_effect=flaky):
            response = self.client.post(
                f'{self.base}download/', {'download_token': self.access_token, 'resolution': 'web'}, format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertGreaterEqual(calls['n'], 3)
        self.assertEqual(len(extra), 2)
        self.assert_failed_cleanly(DownloadJob.objects.get(pk=response.data['job_id']), before)
        self.assert_originals_intact()

    def test_the_jpeg_encode_failing_after_a_good_decode_is_a_failure_not_a_stored_tier(self):
        # Decode problems may fall back to a stored tier (below); an encode problem must not.
        before = self.temp_zips()
        with mock.patch.object(web_size, 'WEB_JPEG_QUALITY', 'not-a-quality'):
            response = self.client.post(
                f'{self.base}download/', {'download_token': self.access_token, 'resolution': 'web'}, format='json',
            )
        self.assert_failed_cleanly(DownloadJob.objects.get(pk=response.data['job_id']), before)

    def test_a_stored_master_vanishing_mid_job_fails_the_job_it_is_not_skipped(self):
        PrivateMediaStorage().delete(self.mid.download_file.name)
        before = self.temp_zips()
        response = self.client.post(
            f'{self.base}download/', {'download_token': self.access_token, 'resolution': 'download'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assert_failed_cleanly(DownloadJob.objects.get(pk=response.data['job_id']), before)
        self.assert_originals_intact()

    def test_a_master_that_cannot_be_made_for_an_oversized_original_fails_the_zip(self):
        bare = self.pipeline_asset('bare-big.jpg', (4200, 2800), 9, build_master=False)
        before = self.temp_zips()
        with mock.patch('apps.clients.views.process_download_master', side_effect=RuntimeError('encoder down')):
            response = self.client.post(
                f'{self.base}download/', {'download_token': self.access_token, 'resolution': 'download'}, format='json',
            )
        self.assert_failed_cleanly(DownloadJob.objects.get(pk=response.data['job_id']), before)
        self.assertEqual(len(self.uploads), 4)
        self.assertIsNotNone(bare)

    def test_a_failed_job_sends_no_ready_email_and_a_retry_builds_a_good_zip(self):
        from django.core import mail
        sent_before = len(mail.outbox)
        PrivateMediaStorage().delete(self.mid.download_file.name)
        failed = self.client.post(
            f'{self.base}download/',
            {'download_token': self.access_token, 'resolution': 'download'}, format='json',
        )
        self.assertEqual(DownloadJob.objects.get(pk=failed.data['job_id']).state, DownloadJob.State.FAILED)
        self.assertEqual(len(mail.outbox), sent_before)
        # The photographer's data is intact; once the master is rebuilt the same request works.
        from apps.core.utils import process_download_master
        self.mid.original_file.open('rb')
        rebuilt = process_download_master(self.mid.original_file)
        self.mid.original_file.close()
        self.mid.download_file.save('mid.rebuilt.jpg', rebuilt, save=True)
        entries = self.zip_entries(resolution='download')
        self.assertEqual(sorted(entries), ['big.jpg', 'mid.jpg', 'small.jpg'])

    def test_an_undecodable_source_falls_back_to_the_stored_tier_it_does_not_fail(self):
        broken = self.pipeline_asset('broken.jpg', (3000, 2000), 9)
        broken.download_file.save('broken.master.jpg', ContentFile(b'not an image'), save=False)
        broken.original_file.save('broken.jpg', ContentFile(b'not an image either'), save=False)
        broken.save()
        job, parts = self.prepare(resolution='web')
        self.assertEqual(job.state, DownloadJob.State.READY)
        entries = self.entries(parts[0])
        self.assertTrue(entries['broken.webp'].startswith(b'RIFF'))         # its stored display tier, honestly named
        self.assertEqual(dims(entries['big.jpg'])[0], 'JPEG')

    def test_a_single_web_size_whose_encode_fails_is_a_503_never_a_wrong_file(self):
        with mock.patch.object(web_size, 'WEB_JPEG_QUALITY', 'not-a-quality'):
            response = self.single(self.big, 'web')
            check = self.single(self.big, 'web', check='1')
        for refused in (response, check):
            self.assertEqual(refused.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertEqual(refused.data['code'], 'web_size_preparing')
            self.assertEqual(refused['Retry-After'], '3')
        self.assertFalse(DownloadLog.objects.exists())
        self.assertEqual(self.cached_files(self.big), [])


class RetryAfterReachesTheBrowserTests(PipelineBase):
    def test_the_503_exposes_retry_after_to_the_cross_origin_app(self):
        from django.conf import settings
        self.assertIn('Retry-After', settings.CORS_EXPOSE_HEADERS)
        with mock.patch.object(web_size, 'WEB_JPEG_QUALITY', 'not-a-quality'):
            response = self.client.get(
                self.photo_url(self.big),
                {'download_token': self.access_token, 'resolution': 'web', 'check': '1'},
                HTTP_ORIGIN=settings.CORS_ALLOWED_ORIGINS[0],
            )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response['Retry-After'], str(settings.WEB_SIZE_RETRY_AFTER_SECONDS))
        self.assertIn('Retry-After', response['Access-Control-Expose-Headers'])
