# backend/apps/clients/tests/test_download_policy_1r6.py
"""
Task 1R.6 -- Pixieset-style Download/Privacy settings, server-enforced.

Covers the policy knobs that did not exist before this task, all stored in
Gallery.design_settings (no new DB columns):

  - download.high_res.mode='original' is Pro+ only to SAVE (403 for Free)
    and the EFFECTIVE mode served auto-falls-back to the 3600px Download
    Master the moment the plan lapses, without touching the stored choice
  - the served "original" bytes are the real upload, byte-identical and
    never watermarked
  - "Limit Photo Downloads" (download.limit_total) and "Limit PIN Usage"
    (privacy.pin_limit) both count real rows (DownloadLog / a JSON use
    counter) and reject once the cap is hit, with a friendly message that
    never reveals internals
  - "Restrict Downloads to Specific Contacts" (restrict_contacts +
    allowed_emails) never reveals the allow-list itself, win or lose
  - "Photo Sets Available for Download" (sets_enabled) blocks a disabled
    set and any whole-gallery download once restricted
  - a brand new gallery has no auto-generated PIN and asks for nothing on
    open when it has neither a password nor a PIN

Reuses DownloadFlowBase (gallery + PhotoSets + assets + token/zip/photo_url
helpers) from test_download_access_flow.py and grant_plan() from
apps.subscriptions.testing, exactly like the existing branding/watermark
entitlement tests -- no new fixtures duplicated.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.clients.models import DownloadLog
from apps.clients.tests.test_download_access_flow import DownloadFlowBase, PIN, _asset, _zip_entries
from apps.galleries.models import Gallery
from apps.subscriptions.testing import grant_plan

User = get_user_model()


class OriginalDownloadEntitlementTests(DownloadFlowBase):
    """Save-time Pro-gate (apps/galleries/serializers.py) and serve-time
    fallback (apps/clients/download_access.py::effective_high_res_mode)."""

    def _save_high_res_mode(self, mode):
        self.client.force_authenticate(user=self.photographer)
        return self.client.patch(
            f'/api/v1/galleries/{self.gallery.slug}/',
            {'design_settings': {'downloads': {'high_res': {'enabled': True, 'mode': mode}}}},
            format='json',
        )

    def test_free_user_cannot_save_original_mode(self):
        response = self._save_high_res_mode('original')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(response.data['code'], 'original_download_requires_upgrade')
        self.gallery.refresh_from_db()
        self.assertNotEqual(
            (self.gallery.design_settings or {}).get('downloads', {}).get('high_res', {}).get('mode'),
            'original',
        )

    def test_free_user_can_still_save_3600_mode(self):
        response = self._save_high_res_mode('3600')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_pro_user_can_save_original_mode(self):
        grant_plan(self.photographer)
        response = self._save_high_res_mode('original')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.design_settings['downloads']['high_res']['mode'], 'original')

    def test_downgrade_falls_back_to_3600_master_without_mutating_the_stored_choice(self):
        grant_plan(self.photographer)
        saved = self._save_high_res_mode('original')
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)

        # Plan lapses -- the stored choice is left exactly as it was.
        grant_plan(self.photographer, days=-1)

        token = self.token()
        response = self.client.get(self.photo_url(self.a1), {'download_token': token, 'resolution': 'download'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b''.join(response.streaming_content), b'MASTER:a1.jpg')
        self.assertEqual(DownloadLog.objects.latest('created_at').resolution, DownloadLog.Resolution.DOWNLOAD)

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.design_settings['downloads']['high_res']['mode'], 'original')

    def test_pro_photographer_download_serves_the_true_original_byte_identical(self):
        grant_plan(self.photographer)
        self.assertEqual(self._save_high_res_mode('original').status_code, status.HTTP_200_OK)

        token = self.token()
        response = self.client.get(self.photo_url(self.a1), {'download_token': token, 'resolution': 'download'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # The real upload bytes, never re-encoded -- not the 2048px display
        # derivative and not the 3600px Download Master.
        self.assertEqual(b''.join(response.streaming_content), b'ORIGINAL:a1.jpg')
        self.assertEqual(DownloadLog.objects.latest('created_at').resolution, DownloadLog.Resolution.ORIGINAL)

    def test_pro_photographer_zip_serves_the_true_original_for_every_asset(self):
        grant_plan(self.photographer)
        self.assertEqual(self._save_high_res_mode('original').status_code, status.HTTP_200_OK)

        token = self.token()
        response = self.zip(token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entries = _zip_entries(response)
        self.assertEqual(
            entries,
            {'a1.jpg': b'ORIGINAL:a1.jpg', 'a2.jpg': b'ORIGINAL:a2.jpg', 'b1.jpg': b'ORIGINAL:b1.jpg'},
        )

    def test_client_facing_resolution_values_never_include_the_word_original(self):
        """The public API's own vocabulary never exposes 'original' as a
        choice -- only 'web'/'download' are accepted; see
        apps.clients.views.DOWNLOAD_RESOLUTIONS."""
        from apps.clients.views import DOWNLOAD_RESOLUTIONS
        self.assertEqual(set(DOWNLOAD_RESOLUTIONS), {'web', 'download'})


class TotalDownloadLimitTests(DownloadFlowBase):
    def _set_limit(self, limit_total):
        self.gallery.design_settings = dict(self.gallery.design_settings or {}, downloads={'limit_total': limit_total})
        self.gallery.save(update_fields=['design_settings'])

    def test_limit_blocks_further_single_photo_downloads_once_reached(self):
        self._set_limit(1)
        token = self.token()
        first = self.client.get(self.photo_url(self.a1), {'download_token': token})
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        second = self.client.get(self.photo_url(self.a2), {'download_token': token})
        self.assertEqual(second.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(second.data['code'], 'download_limit_reached')
        self.assertEqual(DownloadLog.objects.count(), 1)

    def test_limit_blocks_a_new_gallery_zip_once_reached(self):
        self._set_limit(1)
        token = self.token()
        self.client.get(self.photo_url(self.a1), {'download_token': token})
        response = self.zip(token)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'download_limit_reached')

    def test_unlimited_by_default(self):
        token = self.token()
        for asset in (self.a1, self.a2, self.b1):
            self.assertEqual(
                self.client.get(self.photo_url(asset), {'download_token': token}).status_code, 200,
            )


class PinUsageLimitTests(DownloadFlowBase):
    def _set_pin_limit(self, limit):
        self.gallery.design_settings = dict(self.gallery.design_settings or {}, privacy={'pin_limit': limit})
        self.gallery.save(update_fields=['design_settings'])

    def test_pin_limit_blocks_further_verification_once_reached(self):
        self._set_pin_limit(1)
        first = self.authorize()
        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)
        second = self.authorize()
        self.assertEqual(second.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(second.data['code'], 'pin_limit_reached')

    def test_wrong_pin_attempts_never_count_against_the_limit(self):
        self._set_pin_limit(1)
        for _ in range(3):
            wrong = self.authorize(pin='0000')
            self.assertEqual(wrong.status_code, status.HTTP_401_UNAUTHORIZED)
        ok = self.authorize()
        self.assertEqual(ok.status_code, status.HTTP_200_OK, ok.data)

    def test_setting_a_new_pin_resets_the_count(self):
        self._set_pin_limit(1)
        self.authorize()
        self.client.force_authenticate(user=self.photographer)
        self.client.post(f'/api/v1/galleries/{self.gallery.slug}/set-download-pin/', {'pin': '7777'}, format='json')
        self.client.force_authenticate(user=None)
        response = self.client.post(self.access_url, {'email': 'c@example.com', 'pin': '7777'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class ContactRestrictionTests(DownloadFlowBase):
    def _restrict_to(self, *emails):
        self.gallery.design_settings = dict(
            self.gallery.design_settings or {},
            downloads={'restrict_contacts': True, 'allowed_emails': list(emails)},
        )
        self.gallery.save(update_fields=['design_settings'])

    def test_email_not_on_the_allowlist_is_refused_without_revealing_it(self):
        self._restrict_to('vip@example.com')
        response = self.authorize(email='stranger@example.com')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'email_not_authorized')
        self.assertNotIn('vip@example.com', str(response.data))

    def test_email_on_the_allowlist_is_authorized(self):
        self._restrict_to('vip@example.com')
        response = self.authorize(email='VIP@example.com')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_restriction_forces_the_email_prompt_even_without_require_email(self):
        self.gallery.design_settings = dict(
            self.gallery.design_settings or {},
            downloads={'require_email': False, 'restrict_contacts': True, 'allowed_emails': ['vip@example.com']},
        )
        self.gallery.save(update_fields=['design_settings'])
        response = self.client.get(self.base).data['download_policy']
        self.assertTrue(response['require_email'])


class SetsAvailableForDownloadTests(DownloadFlowBase):
    def _restrict_to_ceremony_only(self):
        self.gallery.design_settings = dict(
            self.gallery.design_settings or {}, downloads={'sets_enabled': [str(self.ceremony.id)]},
        )
        self.gallery.save(update_fields=['design_settings'])

    def test_disabled_set_cannot_be_downloaded(self):
        self._restrict_to_ceremony_only()
        token = self.token()
        response = self.zip(token, set_id=str(self.party.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'set_not_enabled')

    def test_enabled_set_still_downloads(self):
        self._restrict_to_ceremony_only()
        token = self.token()
        response = self.zip(token, set_id=str(self.ceremony.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_whole_gallery_download_refused_once_restricted_to_a_subset(self):
        self._restrict_to_ceremony_only()
        token = self.token()
        response = self.zip(token)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'set_not_enabled')

    def test_single_photo_in_a_disabled_set_cannot_be_downloaded(self):
        self._restrict_to_ceremony_only()
        token = self.token()
        response = self.client.get(self.photo_url(self.b1), {'download_token': token})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'set_not_enabled')

    def test_browsing_tabs_are_never_filtered_by_the_download_restriction(self):
        """sets_enabled only narrows the download picker, never what a
        visitor can browse/view in the gallery."""
        self._restrict_to_ceremony_only()
        response = self.client.get(self.base, {'set': str(self.party.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['photos']) >= 1)


class NewGalleryDefaultsTests(APITestCase):
    def test_new_gallery_has_no_auto_generated_pin_or_password(self):
        photographer = User.objects.create_user(
            email='freshowner@kyapture.com', password='SecurePassword123!', username='freshowner',
        )
        gallery = Gallery.objects.create(
            photographer=photographer, title='Fresh', slug='fresh-gallery',
            is_published=True, is_active=True, allow_download=True,
        )
        self.assertIsNone(gallery.download_pin_hash)
        self.assertFalse(gallery.is_password_protected)

        response = self.client.get(f'/api/v1/public/{photographer.username}/{gallery.slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['has_download_pin'])
        self.assertNotIn('requires_password', response.data)
