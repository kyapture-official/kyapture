# backend/apps/clients/tests/test_download_pages_1r5b.py
"""
Task 1R.5-B — prepare + ready pages: what the server has to guarantee.

  - the ready page's key is bound to ONE job (no email / PIN asked again)
  - prepared ZIPs and links live 7 days; an expired / purged download reads as
    "expired" (never a raw error page); the daily purge only touches job files
  - a big download is split into "{slug}-photo-download-{n}of{m}.zip" parts
  - Web Size is delivered at the EXACT chosen px (standard JPEG, sRGB, no upscale)
  - High Resolution is the byte-identical original (Pro) or the 3600px master (Free)
"""
import io
import os
import zipfile
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image, ImageCms
from rest_framework import status

from apps.clients.download_jobs import purge_expired_jobs, run_download_job
from apps.clients.models import ClientSession, DownloadJob, DownloadLog
from apps.clients.tests.test_download_access_flow import DownloadFlowBase, _asset, _zip_entries
from apps.core.storage import PrivateMediaStorage
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet
from apps.subscriptions.testing import grant_plan


def jpeg_bytes(size, color=(200, 80, 40), icc=None):
    image = Image.new('RGB', size, color)
    extra = {'icc_profile': icc} if icc else {}
    out = io.BytesIO()
    image.save(out, format='JPEG', quality=92, **extra)
    return out.getvalue()


def real_asset(gallery, name, photo_set, size, order=0, icc=None):
    """A READY image with REAL pixels: original + Download Master (the master is capped at 3600)."""
    data = jpeg_bytes(size, icc=icc)
    asset = MediaAsset(
        gallery=gallery, media_type=MediaAsset.MediaType.IMAGE, original_name=name, file_size=len(data),
        order=order, photo_set=photo_set, processing_status=MediaAsset.ProcessingStatus.READY,
    )
    asset.original_file.save(name, ContentFile(data), save=False)
    asset.save()
    asset.download_file.save(f'{name}.master.jpg', ContentFile(data), save=False)
    asset.save(update_fields=['download_file'])
    return asset, data


class JobBase(DownloadFlowBase):
    with_pin = True

    def prepare_job(self, **body):
        """Authorize, POST download/ and return (job, prepare response)."""
        cache.clear()
        token = self.token(email=body.pop('email', 'client@example.com'))
        body['download_token'] = token
        response = self.client.post(f'{self.base}download/', body, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, getattr(response, 'data', None))
        return DownloadJob.objects.get(pk=response.data['job_id']), response

    def status_by_key(self, job, key, **extra):
        return self.client.get(f'{self.base}download-jobs/{job.id}/', {'link_token': key, **extra})


class JobLinkTokenTests(JobBase):
    def test_the_prepare_response_carries_a_key_for_that_job(self):
        job, response = self.prepare_job()
        self.assertTrue(response.data['link_token'])
        self.assertEqual(job.state, DownloadJob.State.READY)

    def test_the_key_opens_the_ready_page_without_email_or_pin(self):
        job, response = self.prepare_job()
        cache.clear()
        # No download_token, no PIN, no email anywhere in this request.
        ready = self.status_by_key(job, response.data['link_token'])
        self.assertEqual(ready.status_code, status.HTTP_200_OK, ready.data)
        self.assertEqual(ready.data['state'], 'ready')
        self.assertEqual(ready.data['files'][0]['name'], 'flow-gallery-photo-download-1of1.zip')
        download = self.client.get(ready.data['files'][0]['url'])
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_zip_entries(download)), 3)

    def test_without_the_key_the_pin_gate_still_applies(self):
        job, _ = self.prepare_job()
        response = self.client.get(f'{self.base}download-jobs/{job.id}/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_key_is_bound_to_its_own_job(self):
        job_a, response_a = self.prepare_job(resolution='download')
        job_b, response_b = self.prepare_job(resolution='web', email='other@example.com')
        self.assertNotEqual(job_a.id, job_b.id)
        wrong = self.status_by_key(job_b, response_a.data['link_token'])
        self.assertEqual((wrong.status_code, wrong.data['code']), (404, 'download_not_found'))
        right = self.status_by_key(job_b, response_b.data['link_token'])
        self.assertEqual(right.status_code, status.HTTP_200_OK)

    def test_a_key_never_reaches_another_gallery(self):
        job, response = self.prepare_job()
        other = Gallery.objects.create(
            photographer=self.photographer, title='Other', slug='other-gallery',
            is_published=True, is_active=True, allow_download=True,
        )
        moved = DownloadJob.objects.create(
            gallery=other, resolution=job.resolution, email=job.email, state='ready',
            files=job.files, expires_at=job.expires_at,
        )
        denied = self.client.get(
            f'/api/v1/public/{self.username}/other-gallery/download-jobs/{moved.id}/',
            {'link_token': response.data['link_token']},
        )
        self.assertEqual((denied.status_code, denied.data['code']), (404, 'download_not_found'))

    def test_a_forged_or_empty_key_is_refused(self):
        job, response = self.prepare_job()
        for bad in ('', 'garbage', response.data['link_token'][:-3] + 'abc'):
            denied = self.status_by_key(job, bad)
            self.assertEqual((denied.status_code, denied.data['code']), (404, 'download_not_found'), bad)

    def test_the_gallery_password_gate_is_a_separate_gate_and_stays(self):
        job, response = self.prepare_job()
        Gallery.objects.filter(pk=self.gallery.pk).update(is_password_protected=True)
        key = response.data['link_token']
        denied = self.status_by_key(job, key)
        self.assertEqual((denied.status_code, denied.data['code']), (401, 'session_required'))
        session = ClientSession.objects.create(gallery=self.gallery, email='client@example.com')
        allowed = self.status_by_key(job, key, token=session.access_token)
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)


class SevenDayLifetimeTests(JobBase):
    def test_defaults_are_seven_days(self):
        week = 7 * 24 * 3600
        self.assertEqual(settings.DOWNLOAD_JOB_TTL_SECONDS, week)
        self.assertEqual(settings.DOWNLOAD_FILE_URL_TTL_SECONDS, week)

    def test_a_ready_job_expires_in_seven_days(self):
        job, _ = self.prepare_job()
        lifetime = (job.expires_at - timezone.now()).total_seconds()
        self.assertAlmostEqual(lifetime, 7 * 24 * 3600, delta=120)

    def test_the_link_still_works_on_day_six_and_reads_expired_after_day_seven(self):
        job, response = self.prepare_job()
        key = response.data['link_token']
        DownloadJob.objects.filter(pk=job.pk).update(expires_at=timezone.now() + timedelta(days=1))
        self.assertEqual(self.status_by_key(job, key).data['state'], 'ready')

        DownloadJob.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        expired = self.status_by_key(job, key)
        self.assertEqual(expired.status_code, status.HTTP_200_OK)
        self.assertEqual((expired.data['state'], expired.data['code']), ('failed', 'download_expired'))
        self.assertEqual(expired.data['files'], [])

    def test_an_expired_file_link_opened_in_a_browser_redirects_to_the_friendly_page(self):
        job, response = self.prepare_job()
        url = self.status_by_key(job, response.data['link_token']).data['files'][0]['url']
        DownloadJob.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        browser = self.client.get(url, HTTP_ACCEPT='text/html,application/xhtml+xml')
        self.assertEqual(browser.status_code, 302)
        self.assertTrue(browser['Location'].endswith(f'/g/{self.username}/{self.slug}/download?link=expired'))

    def test_a_purged_download_reads_as_not_found_for_the_page_to_explain(self):
        job, response = self.prepare_job()
        key = response.data['link_token']
        DownloadJob.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(purge_expired_jobs(), 1)
        gone = self.client.get(f'{self.base}download-jobs/{job.id}/', {'link_token': key})
        self.assertEqual((gone.status_code, gone.data['code']), (404, 'download_not_found'))


class DailyPurgeTests(JobBase):
    def test_purge_removes_expired_job_files_only(self):
        expired, _ = self.prepare_job(email='old@example.com')
        live, _ = self.prepare_job(resolution='web', email='new@example.com')
        storage = PrivateMediaStorage()
        expired_path = storage.path(expired.files[0]['storage_path'])
        live_path = storage.path(live.files[0]['storage_path'])
        original_paths = [asset.original_file.path for asset in MediaAsset.objects.filter(gallery=self.gallery)]
        DownloadJob.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(days=1))

        self.assertEqual(purge_expired_jobs(), 1)
        self.assertFalse(os.path.exists(expired_path))
        self.assertTrue(os.path.exists(live_path))
        self.assertTrue(DownloadJob.objects.filter(pk=live.pk).exists())
        # Originals are never part of a purge, and the activity history stays.
        self.assertTrue(all(os.path.exists(path) for path in original_paths))

    def test_the_beat_schedule_runs_the_purge_once_a_day(self):
        from config.celery import app
        entry = app.conf.beat_schedule['purge-expired-download-jobs']
        self.assertEqual(entry['task'], 'apps.clients.tasks.purge_expired_download_jobs')
        self.assertEqual(
            (entry['schedule']._orig_hour, entry['schedule']._orig_day_of_week), (3, '*'),
        )


class ZipPartTests(JobBase):
    """Fixture files are a few bytes each, so a tiny limit forces a split."""
    with_pin = False

    @override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=20)
    def test_each_photo_that_does_not_fit_starts_a_new_part_named_n_of_m(self):
        job, response = self.prepare_job()
        names = [part['name'] for part in job.files]
        self.assertEqual(names, [f'flow-gallery-photo-download-{n}of3.zip' for n in (1, 2, 3)])
        self.assertEqual([part['photo_count'] for part in job.files], [1, 1, 1])

        ready = self.status_by_key(job, response.data['link_token']).data
        self.assertEqual([entry['name'] for entry in ready['files']], names)
        seen = set()
        for entry in ready['files']:
            self.assertGreater(entry['size_bytes'], 0)
            download = self.client.get(entry['url'])
            self.assertEqual(download.status_code, status.HTTP_200_OK)
            self.assertIn(f'filename="{entry["name"]}"', download['Content-Disposition'])
            seen.update(_zip_entries(download))
        self.assertEqual(seen, {'a1.jpg', 'a2.jpg', 'b1.jpg'})   # every photo exactly once across the parts

    @override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=30)
    def test_parts_are_packed_up_to_the_limit(self):
        job, _ = self.prepare_job()
        self.assertEqual([part['photo_count'] for part in job.files], [2, 1])
        self.assertEqual(
            [part['name'] for part in job.files],
            ['flow-gallery-photo-download-1of2.zip', 'flow-gallery-photo-download-2of2.zip'],
        )

    def test_under_the_default_two_gigabyte_limit_it_is_one_part(self):
        self.assertEqual(settings.DOWNLOAD_ZIP_PART_MAX_BYTES, 2 * 1024 ** 3)
        job, _ = self.prepare_job()
        self.assertEqual([part['name'] for part in job.files], ['flow-gallery-photo-download-1of1.zip'])

    @override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=20)
    def test_every_part_gets_its_own_activity_row_and_repeats_collapse(self):
        job, response = self.prepare_job()
        ready = self.status_by_key(job, response.data['link_token']).data
        first, second = ready['files'][0]['url'], ready['files'][1]['url']
        for _ in range(2):                                   # a retry of part 1 is one row
            self.assertEqual(self.client.get(first).status_code, 200)
        self.assertEqual(DownloadLog.objects.count(), 1)
        self.assertEqual(self.client.get(second).status_code, 200)
        rows = list(DownloadLog.objects.order_by('created_at'))
        self.assertEqual([row.photo_count for row in rows], [1, 1])
        self.assertEqual(
            [row.filename for row in rows],
            ['flow-gallery-photo-download-1of3.zip', 'flow-gallery-photo-download-2of3.zip'],
        )
        self.assertTrue(all(row.email == 'client@example.com' and row.resolution == 'download' for row in rows))


class ExactWebSizeTests(JobBase):
    with_pin = False

    def setUp(self):
        super().setUp()
        MediaAsset.objects.filter(gallery=self.gallery).delete()
        self.wide, self.wide_bytes = real_asset(self.gallery, 'wide.jpg', self.ceremony, (3000, 2000), 1)
        self.tall, _ = real_asset(self.gallery, 'tall.jpg', self.ceremony, (2000, 3000), 2)
        self.small, _ = real_asset(self.gallery, 'small.jpg', self.party, (1000, 700), 3)

    def store_px(self, px):
        self.gallery.design_settings = {'downloads': {'web': {'enabled': True, 'px': px}}}
        self.gallery.save(update_fields=['design_settings'])

    def delivered(self, px):
        self.store_px(px)
        cache.clear()
        response = self.zip(self.token(email=f'px{px}@example.com'), resolution='web')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {name: Image.open(io.BytesIO(data)) for name, data in _zip_entries(response).items()}

    def test_the_delivered_long_edge_equals_the_chosen_px(self):
        for px in (2048, 1024, 640):
            images = self.delivered(px)
            self.assertEqual(set(images), {'wide.jpg', 'tall.jpg', 'small.jpg'}, px)
            self.assertEqual(max(images['wide.jpg'].size), px, px)
            self.assertEqual(images['wide.jpg'].size[0], px, px)       # landscape: width is the long edge
            self.assertEqual(images['tall.jpg'].size[1], px, px)       # portrait: height is the long edge
            self.assertEqual(round(images['wide.jpg'].size[1] / px, 2), round(2000 / 3000, 2), px)

    def test_1024_is_really_1024_not_the_1280_tier(self):
        images = self.delivered(1024)
        self.assertEqual(max(images['wide.jpg'].size), 1024)
        self.assertNotEqual(max(images['wide.jpg'].size), 1280)

    def test_a_smaller_photo_is_never_upscaled(self):
        self.assertEqual(max(self.delivered(2048)['small.jpg'].size), 1000)
        self.assertEqual(max(self.delivered(1024)['small.jpg'].size), 1000)
        self.assertEqual(max(self.delivered(640)['small.jpg'].size), 640)

    def test_it_is_a_standard_srgb_jpeg_without_metadata(self):
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        real_asset(self.gallery, 'tagged.jpg', self.ceremony, (2400, 1600), 4, icc=icc)
        images = self.delivered(1024)
        for name, image in images.items():
            self.assertEqual(image.format, 'JPEG', name)
            self.assertEqual(image.mode, 'RGB', name)
            self.assertNotIn('icc_profile', image.info, name)
            self.assertEqual(len(image.getexif()), 0, name)
            self.assertFalse(image.info.get('progressive'), name)
        self.assertEqual(max(images['tagged.jpg'].size), 1024)

    def test_the_original_file_is_only_read_never_changed(self):
        self.delivered(640)
        self.wide.original_file.open('rb')
        try:
            self.assertEqual(self.wide.original_file.read(), self.wide_bytes)
        finally:
            self.wide.original_file.close()

    def test_a_single_photo_web_download_is_exact_too(self):
        self.store_px(1024)
        token = self.token()
        response = self.client.get(self.photo_url(self.wide), {'download_token': token, 'resolution': 'web'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('wide.jpg', response['Content-Disposition'])
        image = Image.open(io.BytesIO(b''.join(response.streaming_content)))
        self.assertEqual((image.format, max(image.size)), ('JPEG', 1024))
        self.assertEqual(DownloadLog.objects.latest('created_at').resolution, DownloadLog.Resolution.WEB)

    def test_the_gallery_watermark_is_applied_to_web_size_like_the_web_tiers(self):
        from apps.clients.web_size import derive_web_jpeg
        grant_plan(self.photographer)
        self.gallery.watermark_enabled = True
        self.gallery.design_settings = {'watermark': {'type': 'text', 'text': 'KYAPTURE TEST'}}
        self.gallery.save(update_fields=['watermark_enabled', 'design_settings'])
        self.gallery.refresh_from_db()
        plain = derive_web_jpeg(self.wide, 1024, None)
        marked = derive_web_jpeg(self.wide, 1024, self.gallery)
        self.assertNotEqual(plain, marked)
        self.assertEqual(max(Image.open(io.BytesIO(marked)).size), 1024)


class HighResolutionTruthTests(JobBase):
    with_pin = False

    def setUp(self):
        super().setUp()
        MediaAsset.objects.filter(gallery=self.gallery).delete()
        self.a, self.a_bytes = real_asset(self.gallery, 'a.jpg', self.ceremony, (3000, 2000), 1)
        # A Download Master that is plainly NOT the original, so the two can be told apart.
        master = jpeg_bytes((1800, 1200), color=(10, 120, 200))
        self.a.download_file.delete(save=False)
        self.a.download_file.save('a.master.jpg', ContentFile(master), save=True)
        self.master_bytes = master

    def choose_original(self):
        self.gallery.design_settings = {'downloads': {'high_res': {'enabled': True, 'mode': 'original'}}}
        self.gallery.save(update_fields=['design_settings'])

    def test_pro_original_is_byte_identical_in_the_zip(self):
        grant_plan(self.photographer)
        self.choose_original()
        entries = _zip_entries(self.zip(self.token()))
        self.assertEqual(entries, {'a.jpg': self.a_bytes})

    def test_free_falls_back_to_the_3600_master_even_if_original_is_stored(self):
        self.choose_original()          # stored choice, but this photographer is on Free
        entries = _zip_entries(self.zip(self.token()))
        self.assertEqual(entries, {'a.jpg': self.master_bytes})
        self.assertNotEqual(entries['a.jpg'], self.a_bytes)

    def test_default_high_resolution_is_the_download_master(self):
        entries = _zip_entries(self.zip(self.token()))
        self.assertEqual(entries, {'a.jpg': self.master_bytes})
