# backend/apps/clients/tests/test_single_photo_download_1r5d.py
"""
Task 1R.5-D — pixieset-style single photo download (tile icon / lightbox).

  - the photo is a DIRECT attachment (no ZIP, no download job), named after the real
    photo -- never a UUID -- whichever size is chosen
  - the same gates as every other download: email / PIN token, gallery password,
    disabled sets, disabled sizes, total limit, contact list
  - High Resolution is the 3600px master unless a Pro photographer chose Original;
    Web Size is the exact px JPEG
  - it counts as ONE photo toward the limit, and the Download Activity row carries
    the real filename + email
  - ?check=1 (what the dialog asks before handing the browser the link) applies every
    one of those gates but serves nothing, logs nothing and counts nothing
"""
import io
import re

from django.core.files.base import ContentFile
from PIL import Image
from rest_framework import status

from apps.clients.models import DownloadJob, DownloadLog
from apps.clients.tests.test_download_access_flow import DownloadFlowBase
from apps.clients.tests.test_download_pages_1r5b import jpeg_bytes, real_asset
from apps.subscriptions.testing import grant_plan

UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)


def body(response):
    return b''.join(response.streaming_content)


class SinglePhotoBase(DownloadFlowBase):
    with_pin = True

    def set_downloads(self, **downloads):
        self.gallery.design_settings = dict(self.gallery.design_settings or {}, downloads=downloads)
        self.gallery.save(update_fields=['design_settings'])

    def get_photo(self, asset, token, **params):
        return self.client.get(self.photo_url(asset), {'download_token': token, **params})


class DirectDownloadTests(SinglePhotoBase):
    def test_high_resolution_is_a_direct_attachment_with_the_real_filename(self):
        response = self.get_photo(self.a1, self.token(), resolution='download')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="a1.jpg"')
        self.assertEqual(body(response), b'MASTER:a1.jpg')
        self.assertFalse(UUID_RE.search(response['Content-Disposition']))

    def test_no_zip_and_no_preparing_job_is_involved(self):
        response = self.get_photo(self.a1, self.token())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('zip', response['Content-Type'])
        self.assertFalse(DownloadJob.objects.exists())

    def test_a_gallery_without_email_or_pin_downloads_with_no_token_at_all(self):
        self.gallery.download_pin_hash = ''
        self.gallery.save(update_fields=['download_pin_hash'])
        self.set_downloads(require_email=False)
        response = self.client.get(self.photo_url(self.a1))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="a1.jpg"')
        self.assertIsNone(DownloadLog.objects.get().email)

    def test_an_awkward_but_real_filename_is_kept_readable(self):
        self.a1.original_name = 'Wedding day 01.JPG'
        self.a1.save(update_fields=['original_name'])
        response = self.get_photo(self.a1, self.token())
        self.assertIn('Wedding day 01.JPG', response['Content-Disposition'])
        self.assertFalse(UUID_RE.search(response['Content-Disposition']))


class SizeTruthTests(SinglePhotoBase):
    with_pin = False

    def setUp(self):
        super().setUp()
        self.wide, self.wide_bytes = real_asset(self.gallery, 'wide.jpg', self.ceremony, (3000, 2000), 4)
        # Same photo again, but with a Download Master that is plainly NOT the original.
        self.mastered, self.mastered_bytes = real_asset(self.gallery, 'mastered.jpg', self.ceremony, (3000, 2000), 5)
        master = jpeg_bytes((1800, 1200), color=(10, 120, 200))
        self.mastered.download_file.delete(save=False)
        self.mastered.download_file.save('mastered.master.jpg', ContentFile(master), save=True)
        self.master_bytes = master

    def test_web_size_is_the_exact_chosen_px_named_after_the_photo(self):
        for px in (2048, 1024, 640):
            self.set_downloads(web={'enabled': True, 'px': px})
            response = self.get_photo(self.wide, self.token(email=f'w{px}@example.com'), resolution='web')
            self.assertEqual(response.status_code, status.HTTP_200_OK, px)
            self.assertEqual(response['Content-Disposition'], 'attachment; filename="wide.jpg"')
            image = Image.open(io.BytesIO(body(response)))
            self.assertEqual((image.format, max(image.size)), ('JPEG', px))

    def test_web_size_never_upscales_a_smaller_photo(self):
        small, _ = real_asset(self.gallery, 'small.jpg', self.ceremony, (500, 300), 5)
        self.set_downloads(web={'enabled': True, 'px': 2048})
        response = self.get_photo(small, self.token(), resolution='web')
        self.assertEqual(Image.open(io.BytesIO(body(response))).size, (500, 300))

    def test_free_photographer_gets_the_master_even_if_original_is_stored(self):
        self.set_downloads(high_res={'enabled': True, 'mode': 'original'})
        response = self.get_photo(self.mastered, self.token(), resolution='download')
        payload = body(response)
        self.assertEqual(payload, self.master_bytes)
        self.assertNotEqual(payload, self.mastered_bytes)
        self.assertEqual(DownloadLog.objects.get().resolution, DownloadLog.Resolution.DOWNLOAD)

    def test_pro_photographer_original_is_byte_identical(self):
        grant_plan(self.photographer)
        self.set_downloads(high_res={'enabled': True, 'mode': 'original'})
        response = self.get_photo(self.mastered, self.token(), resolution='download')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="mastered.jpg"')
        self.assertEqual(body(response), self.mastered_bytes)
        self.assertEqual(DownloadLog.objects.get().resolution, DownloadLog.Resolution.ORIGINAL)

    def test_a_raw_original_request_is_refused(self):
        response = self.get_photo(self.wide, self.token(), resolution='original')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RulesEnforcedTests(SinglePhotoBase):
    def test_no_token_is_refused_when_email_or_pin_is_required(self):
        response = self.client.get(self.photo_url(self.a1))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'download_access_required')
        self.assertFalse(DownloadLog.objects.exists())

    def test_a_forged_token_is_refused(self):
        response = self.get_photo(self.a1, 'forged')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'download_access_expired')

    def test_a_disabled_size_is_refused(self):
        self.set_downloads(high_res={'enabled': False}, web={'enabled': True, 'px': 1024})
        token = self.token()
        refused = self.get_photo(self.a1, token, resolution='download')
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(refused.data['code'], 'resolution_not_allowed')

    def test_a_photo_in_a_disabled_set_is_refused(self):
        self.set_downloads(sets_enabled=[str(self.party.id)])
        token = self.token()
        refused = self.get_photo(self.a1, token)
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(refused.data['code'], 'set_not_enabled')
        self.assertEqual(self.get_photo(self.b1, token).status_code, status.HTTP_200_OK)

    def test_a_contact_not_on_the_list_never_gets_a_token(self):
        self.set_downloads(restrict_contacts=True, allowed_emails=['vip@example.com'])
        response = self.authorize(email='stranger@example.com')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'email_not_authorized')

    def test_a_contact_removed_after_the_token_was_issued_loses_access(self):
        self.set_downloads(restrict_contacts=True, allowed_emails=['client@example.com'])
        token = self.token()
        self.assertEqual(self.get_photo(self.a1, token).status_code, status.HTTP_200_OK)
        self.set_downloads(restrict_contacts=True, allowed_emails=['vip@example.com'])
        self.assertEqual(self.get_photo(self.a1, token).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_wrong_pin_never_issues_a_token(self):
        response = self.authorize(pin='0000')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_limit_counts_each_single_photo_as_one(self):
        self.set_downloads(limit_total=2)
        token = self.token()
        self.assertEqual(self.get_photo(self.a1, token).status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_photo(self.a2, token).status_code, status.HTTP_200_OK)
        blocked = self.get_photo(self.b1, token)
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(blocked.data['code'], 'download_limit_reached')
        self.assertEqual(DownloadLog.objects.count(), 2)
        self.assertEqual(set(DownloadLog.objects.values_list('photo_count', flat=True)), {None})

    def test_downloads_off_refuses_the_photo(self):
        self.gallery.allow_download = False
        self.gallery.save(update_fields=['allow_download'])
        self.assertEqual(self.get_photo(self.a1, 'x').status_code, status.HTTP_403_FORBIDDEN)


class ActivityTests(SinglePhotoBase):
    def test_a_web_size_that_falls_back_to_a_stored_tier_is_still_named_after_the_photo(self):
        # a1's bytes are not a decodable image, so Web Size falls back to the stored tier
        response = self.get_photo(self.a1, self.token(), resolution='web')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="a1.webp"')
        self.assertEqual(DownloadLog.objects.get().filename, 'a1.webp')

    def test_the_activity_row_shows_the_real_filename_and_the_email(self):
        token = self.token(email='buyer@example.com')
        self.get_photo(self.a1, token, resolution='download')
        self.client.force_authenticate(user=self.photographer)
        response = self.client.get(f'/api/v1/galleries/{self.slug}/download-logs/', {'type': 'photo'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        row = response.data['results'][0]
        self.assertEqual(row['filename'], 'a1.jpg')
        self.assertEqual(row['email'], 'buyer@example.com')
        self.assertEqual(row['download_type'], 'photo')
        self.assertEqual(row['resolution'], 'download')
        self.assertFalse(UUID_RE.search(row['filename']))

    def test_a_pro_original_row_is_logged_with_the_real_filename_too(self):
        grant_plan(self.photographer)
        self.set_downloads(high_res={'enabled': True, 'mode': 'original'})
        self.get_photo(self.a2, self.token(), resolution='download')
        log = DownloadLog.objects.get()
        self.assertEqual((log.filename, log.resolution), ('a2.jpg', DownloadLog.Resolution.ORIGINAL))


class PreflightCheckTests(SinglePhotoBase):
    def check(self, asset, token, **params):
        return self.get_photo(asset, token, check='1', **params)

    def test_a_passing_check_serves_nothing_logs_nothing_and_counts_nothing(self):
        self.set_downloads(limit_total=1)
        token = self.token()
        response = self.check(self.a1, token, resolution='download')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'ok': True})
        self.assertNotIn('Content-Disposition', response)
        self.assertFalse(DownloadLog.objects.exists())
        # the limit of 1 is still unspent: the real download that follows works
        self.assertEqual(self.get_photo(self.a1, token).status_code, status.HTTP_200_OK)

    def test_the_check_applies_every_gate(self):
        token = self.token()
        self.assertEqual(self.client.get(self.photo_url(self.a1), {'check': '1'}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.check(self.a1, 'forged').status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.check(self.a1, token, resolution='original').status_code, status.HTTP_400_BAD_REQUEST)

        self.set_downloads(high_res={'enabled': False}, web={'enabled': True, 'px': 1024})
        self.assertEqual(self.check(self.a1, token, resolution='download').data['code'], 'resolution_not_allowed')

        self.set_downloads(sets_enabled=[str(self.party.id)])
        self.assertEqual(self.check(self.a1, token).data['code'], 'set_not_enabled')
        self.assertEqual(self.check(self.b1, token).status_code, status.HTTP_200_OK)

        self.set_downloads(limit_total=1)
        self.get_photo(self.a1, token)
        self.assertEqual(self.check(self.a2, token).data['code'], 'download_limit_reached')

    def test_the_check_cannot_probe_another_gallerys_photo(self):
        token = self.token()
        response = self.check(self.a1, token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        wrong = f'/api/v1/public/otherphotog/{self.slug}/photo/{self.a1.id}/download/'
        self.assertEqual(self.client.get(wrong, {'download_token': token, 'check': '1'}).status_code, status.HTTP_404_NOT_FOUND)
