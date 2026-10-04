# backend/apps/clients/tests/test_download_pin_toggle_1r6a.py
"""
Task 1R.6-A — the Download PIN moved to the Download tab behind an On/Off
toggle (design_settings.downloads.pin_enabled), and the Privacy tab is the
Collection Password only.

  - the PIN is enforced only when a hash exists AND the toggle is not Off
  - turning it On without a saved PIN enforces nothing
  - turning it Off stops enforcement but keeps the stored hash
  - the PIN (or its hash) is never in any API response
  - the collection password can be set, rejected when too short, and removed
"""
import bcrypt
from django.core.cache import cache
from rest_framework import status

from apps.clients.download_access import download_pin_enforced
from apps.clients.models import ClientSession
from apps.clients.tests.test_download_access_flow import PIN, DownloadFlowBase


class DownloadPinToggleTests(DownloadFlowBase):
    def _set_pin_enabled(self, value):
        design = dict(self.gallery.design_settings or {})
        downloads = dict(design.get('downloads') or {})
        downloads['pin_enabled'] = value
        design['downloads'] = downloads
        self.gallery.design_settings = design
        self.gallery.save(update_fields=['design_settings'])

    def _public_policy_has_pin(self):
        return self.client.get(self.base).data['has_download_pin']

    # ── no hash -> nothing enforced ──────────────────────────────────────
    def test_toggle_on_without_a_saved_pin_enforces_nothing(self):
        self.gallery.download_pin_hash = None
        self.gallery.save(update_fields=['download_pin_hash'])
        self._set_pin_enabled(True)
        self.assertFalse(download_pin_enforced(self.gallery))
        self.assertFalse(self._public_policy_has_pin())
        # No PIN asked for: email alone authorizes, and pin_verified is False.
        response = self.client.post(self.access_url, {'email': 'c@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data['pin_verified'])
        token = response.data['download_token']
        self.assertEqual(self.zip(token).status_code, status.HTTP_200_OK)

    # ── hash + toggle ────────────────────────────────────────────────────
    def test_existing_pin_with_no_toggle_value_keeps_enforcing(self):
        """A gallery saved before the toggle existed must not lose its PIN."""
        self.assertNotIn('pin_enabled', (self.gallery.design_settings or {}).get('downloads', {}))
        self.assertTrue(download_pin_enforced(self.gallery))
        self.assertTrue(self._public_policy_has_pin())
        missing = self.client.post(self.access_url, {'email': 'c@example.com'}, format='json')
        self.assertEqual(missing.data['code'], 'pin_required')

    def test_toggle_off_stops_enforcement_but_keeps_the_stored_hash(self):
        stored = self.gallery.download_pin_hash
        self._set_pin_enabled(False)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.download_pin_hash, stored)
        self.assertFalse(download_pin_enforced(self.gallery))
        self.assertFalse(self._public_policy_has_pin())

        response = self.client.post(self.access_url, {'email': 'c@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data['pin_verified'])
        token = response.data['download_token']
        self.assertEqual(self.zip(token).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get(self.photo_url(self.a1), {'download_token': token}).status_code,
            status.HTTP_200_OK,
        )

    def test_toggle_off_invalidates_tokens_issued_while_the_pin_was_on(self):
        token = self.token()
        self.assertEqual(self.zip(token).status_code, status.HTTP_200_OK)
        self._set_pin_enabled(False)
        stale = self.client.get(self.photo_url(self.a1), {'download_token': token})
        self.assertEqual(stale.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(stale.data['code'], 'download_access_expired')

    def test_toggle_back_on_enforces_the_same_pin_again(self):
        self._set_pin_enabled(False)
        self._set_pin_enabled(True)
        self.assertTrue(download_pin_enforced(self.gallery))
        cache.clear()
        wrong = self.authorize(pin='0000')
        self.assertEqual(wrong.data['code'], 'invalid_pin')
        cache.clear()
        right = self.authorize()
        self.assertEqual(right.status_code, status.HTTP_200_OK, right.data)
        self.assertTrue(right.data['pin_verified'])

    def test_a_wrong_pin_is_not_checked_while_the_toggle_is_off(self):
        self._set_pin_enabled(False)
        response = self.authorize(pin='0000')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data['pin_verified'])


class DownloadPinToggleApiTests(DownloadFlowBase):
    """The photographer endpoints that back the new Download-tab controls."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.photographer)
        self.detail_url = f'/api/v1/galleries/{self.gallery.slug}/'
        self.pin_url = f'{self.detail_url}set-download-pin/'

    def _patch_downloads(self, **downloads):
        return self.client.patch(
            self.detail_url, {'design_settings': {'downloads': downloads}}, format='json',
        )

    def test_toggle_is_saved_through_the_gallery_update_and_keeps_the_hash(self):
        stored = self.gallery.download_pin_hash
        response = self._patch_downloads(require_email=True, pin_enabled=False)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIs(response.data['design_settings']['downloads']['pin_enabled'], False)
        self.assertTrue(response.data['has_download_pin'])  # a PIN is still stored
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.download_pin_hash, stored)
        self.assertFalse(download_pin_enforced(self.gallery))

    def test_a_downloads_block_that_omits_the_toggle_keeps_the_stored_value(self):
        self._patch_downloads(pin_enabled=False)
        response = self._patch_downloads(require_email=False)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIs(response.data['design_settings']['downloads']['pin_enabled'], False)

    def test_toggle_must_be_a_boolean(self):
        response = self._patch_downloads(pin_enabled='yes')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pin_is_never_returned_in_any_response(self):
        new_pin = '73920145'
        responses = [
            self.client.post(self.pin_url, {'pin': new_pin}, format='json'),
            self.client.get(self.detail_url),
            self._patch_downloads(pin_enabled=True),
            self.client.get(f'{self.detail_url}download-logs/'),
            self.client.get('/api/v1/galleries/'),
        ]
        self.gallery.refresh_from_db()
        self.assertTrue(bcrypt.checkpw(new_pin.encode(), self.gallery.download_pin_hash.encode()))
        self.client.force_authenticate(user=None)
        responses.append(self.client.get(self.base))
        responses.append(self.client.post(self.access_url, {'email': 'c@example.com', 'pin': new_pin}, format='json'))
        for response in responses:
            body = response.content.decode()
            self.assertNotIn(new_pin, body)
            self.assertNotIn(self.gallery.download_pin_hash, body)
            self.assertNotIn('download_pin_hash', body)
        # Only the boolean is ever exposed.
        self.assertIs(responses[1].data['has_download_pin'], True)

    def test_pin_validation_is_unchanged(self):
        for bad in ('123', '123456789', 'abcd', '12 34'):
            response = self.client.post(self.pin_url, {'pin': bad}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)


class CollectionPasswordTests(DownloadFlowBase):
    with_pin = False

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.photographer)
        self.url = f'/api/v1/galleries/{self.gallery.slug}/set-password/'

    def test_password_can_be_set_then_removed(self):
        on = self.client.post(self.url, {'password': 'secret-pass'}, format='json')
        self.assertEqual(on.status_code, status.HTTP_200_OK, on.data)
        self.assertTrue(on.data['has_password'])
        self.gallery.refresh_from_db()
        self.assertTrue(self.gallery.is_password_protected)
        self.assertTrue(bcrypt.checkpw(b'secret-pass', self.gallery.password_hash.encode()))
        self.assertNotIn('secret-pass', on.content.decode())

        off = self.client.post(self.url, {'password': None}, format='json')
        self.assertEqual(off.status_code, status.HTTP_200_OK, off.data)
        self.assertFalse(off.data['has_password'])
        self.gallery.refresh_from_db()
        self.assertFalse(self.gallery.is_password_protected)
        self.assertIsNone(self.gallery.password_hash)

    def test_removing_the_password_revokes_unlocked_sessions(self):
        self.client.post(self.url, {'password': 'secret-pass'}, format='json')
        self.client.force_authenticate(user=None)
        unlocked = self.client.post(f'{self.base}unlock/', {'password': 'secret-pass'}, format='json')
        self.assertEqual(unlocked.status_code, status.HTTP_200_OK, unlocked.data)
        self.assertEqual(ClientSession.objects.filter(gallery=self.gallery).count(), 1)
        self.client.force_authenticate(user=self.photographer)
        self.client.post(self.url, {'password': ''}, format='json')
        self.assertEqual(ClientSession.objects.filter(gallery=self.gallery).count(), 0)

    def test_too_short_password_is_rejected_and_changes_nothing(self):
        response = self.client.post(self.url, {'password': 'abc'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'password_too_short')
        self.gallery.refresh_from_db()
        self.assertFalse(self.gallery.is_password_protected)
        self.assertIsNone(self.gallery.password_hash)
