# backend/apps/clients/tests/test_download_advanced_1r6c.py
"""
Task 1R.6-C — Download > Advanced: the four server-enforced controls.

  - Limit Photo Downloads: counted in PHOTOS, null (Off) = unlimited, only a
    whole number >= 1 is ever stored
  - Restrict Downloads to Specific Contacts: On with an empty list lets no
    one download; the list is never revealed; removing a contact revokes a
    token they already hold
  - Photo Sets Available for Download: at least one set must stay on
  - Limit PIN Usage: counts correct entries only, Off = null, inactive while
    the Download PIN is off, and a stray stored limit of 1 is cleared
"""
import importlib

from django.apps import apps as django_apps
from django.core.cache import cache
from rest_framework import status

from types import SimpleNamespace

from apps.clients.download_access import (
    download_limit_reached, file_token_state, issue_file_token, pin_limit_reached,
)
from apps.clients.models import DownloadLog
from apps.clients.tests.test_download_access_flow import PIN, DownloadFlowBase


class AdvancedBase(DownloadFlowBase):
    def setUp(self):
        super().setUp()
        self.detail_url = f'/api/v1/galleries/{self.gallery.slug}/'

    def patch_settings(self, **blocks):
        """PATCH design_settings as the photographer; returns the response."""
        self.client.force_authenticate(user=self.photographer)
        try:
            return self.client.patch(self.detail_url, {'design_settings': blocks}, format='json')
        finally:
            self.client.force_authenticate(user=None)

    def patch_downloads(self, **downloads):
        return self.patch_settings(downloads=downloads)

    def stored(self, *path):
        self.gallery.refresh_from_db()
        value = self.gallery.design_settings
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        return value

    def reached(self):
        self.gallery.refresh_from_db()  # settings were saved through the API
        return download_limit_reached(self.gallery)

    def pin_reached(self):
        self.gallery.refresh_from_db()
        return pin_limit_reached(self.gallery)

    def log(self, photo_count=None, **kwargs):
        return DownloadLog.objects.create(gallery=self.gallery, photo_count=photo_count, **kwargs)


class LimitPhotoDownloadsTests(AdvancedBase):
    with_pin = False

    def test_off_is_null_and_nothing_is_limited(self):
        self.assertTrue(self.patch_downloads(limit_total=5).status_code == 200)
        self.assertEqual(self.stored('downloads', 'limit_total'), 5)
        response = self.patch_downloads(limit_total=None)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNone(self.stored('downloads', 'limit_total'))
        for _ in range(8):
            self.log(photo_count=50)
        self.assertFalse(self.reached())

    def test_default_gallery_has_no_limit(self):
        self.assertFalse(self.reached())

    def test_only_a_whole_number_of_one_or_more_is_accepted(self):
        for bad in (0, -3, 1.5, '5', True, [5]):
            response = self.patch_downloads(limit_total=bad)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)
        self.assertIsNone(self.stored('downloads', 'limit_total'))

    def test_the_limit_counts_photos_not_download_rows(self):
        self.patch_downloads(limit_total=10)
        self.log(photo_count=6)            # a 6-photo ZIP
        self.assertFalse(self.reached())
        self.log()                          # a single photo = 1
        self.log(photo_count=2)
        self.assertFalse(self.reached())  # 6 + 1 + 2 = 9
        self.log()                          # 10
        self.assertTrue(self.reached())

    def test_a_single_zip_of_many_photos_reaches_a_small_limit(self):
        self.patch_downloads(limit_total=3)
        self.log(photo_count=3)
        self.assertTrue(self.reached())

    def test_reaching_the_limit_is_rejected_on_every_download_path_with_a_friendly_message(self):
        self.patch_downloads(limit_total=2)
        token = self.token()
        self.log(photo_count=2)
        single = self.client.get(self.photo_url(self.a1), {'download_token': token})
        self.assertEqual(single.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(single.data['code'], 'download_limit_reached')
        self.assertIn('Contact', single.data['error'])
        zipped = self.zip(token)
        self.assertEqual(zipped.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(zipped.data['code'], 'download_limit_reached')

    def test_a_real_single_download_counts_one_photo(self):
        self.patch_downloads(limit_total=2)
        token = self.token()
        self.assertEqual(self.client.get(self.photo_url(self.a1), {'download_token': token}).status_code, 200)
        self.assertFalse(self.reached())
        self.assertEqual(self.client.get(self.photo_url(self.a2), {'download_token': token}).status_code, 200)
        self.assertTrue(self.reached())
        blocked = self.client.get(self.photo_url(self.b1), {'download_token': token})
        self.assertEqual(blocked.data['code'], 'download_limit_reached')


class RestrictContactsTests(AdvancedBase):
    with_pin = False

    def test_on_with_an_empty_list_is_saved_and_lets_no_one_download(self):
        response = self.patch_downloads(restrict_contacts=True, allowed_emails=[])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIs(self.stored('downloads', 'restrict_contacts'), True)
        self.assertEqual(self.stored('downloads', 'allowed_emails'), [])
        for email in ('client@example.com', 'owner@example.com'):
            cache.clear()
            refused = self.client.post(self.access_url, {'email': email}, format='json')
            self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN, email)
            self.assertEqual(refused.data['code'], 'email_not_authorized')

    def test_refusal_never_reveals_the_list_or_its_size(self):
        self.patch_downloads(restrict_contacts=True, allowed_emails=['vip@example.com', 'other@example.com'])
        refused = self.client.post(self.access_url, {'email': 'stranger@example.com'}, format='json')
        body = refused.content.decode()
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)
        for secret in ('vip@example.com', 'other@example.com', 'allowed_emails'):
            self.assertNotIn(secret, body)
        self.assertNotRegex(body, r'\b2\b')
        public = self.client.get(self.base).content.decode()
        self.assertNotIn('vip@example.com', public)
        self.assertNotIn('allowed_emails', public)

    def test_an_email_on_the_list_downloads_and_one_off_it_does_not(self):
        self.patch_downloads(restrict_contacts=True, allowed_emails=['vip@example.com'])
        ok = self.authorize(email='VIP@Example.com')
        self.assertEqual(ok.status_code, status.HTTP_200_OK, ok.data)
        cache.clear()
        self.assertEqual(self.authorize(email='stranger@example.com').status_code, status.HTTP_403_FORBIDDEN)

    def test_removing_a_contact_revokes_the_token_they_already_hold(self):
        self.patch_downloads(restrict_contacts=True, allowed_emails=['vip@example.com', 'keep@example.com'])
        token = self.token(email='vip@example.com')
        self.assertEqual(self.client.get(self.photo_url(self.a1), {'download_token': token}).status_code, 200)
        self.patch_downloads(restrict_contacts=True, allowed_emails=['keep@example.com'])
        revoked = self.client.get(self.photo_url(self.a2), {'download_token': token})
        self.assertEqual(revoked.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(revoked.data['code'], 'download_access_expired')

    def test_removing_a_contact_also_kills_their_prepared_download_link(self):
        self.patch_downloads(restrict_contacts=True, allowed_emails=['vip@example.com'])
        self.gallery.refresh_from_db()
        job = SimpleNamespace(id='11111111-1111-1111-1111-111111111111', email='vip@example.com')
        file_token = issue_file_token(job, self.gallery, 0)
        self.assertEqual(file_token_state(file_token, job, self.gallery, 0), 'ok')
        self.patch_downloads(restrict_contacts=True, allowed_emails=['someone@example.com'])
        self.gallery.refresh_from_db()
        self.assertEqual(file_token_state(file_token, job, self.gallery, 0), 'invalid')

    def test_turning_it_off_lets_everyone_download_again(self):
        self.patch_downloads(restrict_contacts=True, allowed_emails=[])
        self.patch_downloads(restrict_contacts=False, allowed_emails=[])
        self.assertIsNone(self.client.get(self.base).data.get('allowed_emails'))
        self.assertEqual(self.authorize(email='anyone@example.com').status_code, status.HTTP_200_OK)

    def test_emails_are_lowercased_deduplicated_and_validated_on_save(self):
        response = self.patch_downloads(
            restrict_contacts=True, allowed_emails=['A@Example.com', 'a@example.com', ' b@example.com ', ''],
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.stored('downloads', 'allowed_emails'), ['a@example.com', 'b@example.com'])
        bad = self.patch_downloads(restrict_contacts=True, allowed_emails=['not-an-email'])
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.stored('downloads', 'allowed_emails'), ['a@example.com', 'b@example.com'])


class PhotoSetsAvailableTests(AdvancedBase):
    with_pin = False

    def test_at_least_one_set_must_stay_available(self):
        response = self.patch_downloads(sets_enabled=[])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('at least one set', str(response.data).lower())
        self.assertIsNone(self.stored('downloads', 'sets_enabled'))

    def test_null_means_every_set_and_a_subset_saves(self):
        self.assertEqual(self.patch_downloads(sets_enabled=None).status_code, status.HTTP_200_OK)
        ok = self.patch_downloads(sets_enabled=[str(self.ceremony.id)])
        self.assertEqual(ok.status_code, status.HTTP_200_OK, ok.data)
        self.assertEqual(self.stored('downloads', 'sets_enabled'), [str(self.ceremony.id)])

    def test_a_foreign_set_id_is_rejected(self):
        response = self.patch_downloads(sets_enabled=['00000000-0000-0000-0000-000000000000'])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_disabled_sets_are_refused_for_set_gallery_and_single_photo_downloads(self):
        self.patch_downloads(sets_enabled=[str(self.ceremony.id)])
        token = self.token()
        party_zip = self.zip(token, set_id=str(self.party.id))
        self.assertEqual((party_zip.status_code, party_zip.data['code']), (403, 'set_not_enabled'))
        cache.clear()
        whole = self.zip(token)
        self.assertEqual((whole.status_code, whole.data['code']), (403, 'set_not_enabled'))
        single = self.client.get(self.photo_url(self.b1), {'download_token': token})
        self.assertEqual((single.status_code, single.data['code']), (403, 'set_not_enabled'))
        self.assertEqual(self.client.get(self.photo_url(self.a1), {'download_token': token}).status_code, 200)


class LimitPinUsageTests(AdvancedBase):
    def used(self):
        self.client.force_authenticate(user=self.photographer)
        try:
            return self.client.get(self.detail_url).data['design_settings'].get('privacy', {}).get('pin_use_count', 0)
        finally:
            self.client.force_authenticate(user=None)

    def test_each_correct_entry_counts_once_and_wrong_ones_never(self):
        self.patch_settings(privacy={'pin_limit': 3})
        self.assertEqual(self.used(), 0)
        self.authorize(pin='0000')
        self.assertEqual(self.used(), 0)
        cache.clear()
        self.assertEqual(self.authorize().status_code, 200)
        self.assertEqual(self.used(), 1)
        cache.clear()
        self.authorize()
        self.assertEqual(self.used(), 2)

    def test_the_count_is_exposed_to_the_photographer_as_used_x_of_n(self):
        response = self.patch_settings(privacy={'pin_limit': 5})
        self.assertEqual(response.data['design_settings']['privacy']['pin_limit'], 5)
        self.assertEqual(response.data['design_settings']['privacy']['pin_use_count'], 0)
        self.authorize()
        self.assertEqual(self.used(), 1)

    def test_downloads_after_one_entry_do_not_use_the_pin_again(self):
        """What the screen says: a correct entry counts once, whatever is downloaded next."""
        self.patch_settings(privacy={'pin_limit': 2})
        token = self.token()
        self.assertEqual(self.used(), 1)
        for asset in (self.a1, self.a2, self.b1):
            self.assertEqual(self.client.get(self.photo_url(asset), {'download_token': token}).status_code, 200)
        self.assertEqual(self.zip(token).status_code, 200)
        self.assertEqual(self.used(), 1)

    def test_reaching_the_limit_is_rejected_with_a_friendly_message(self):
        self.patch_settings(privacy={'pin_limit': 1})
        self.assertEqual(self.authorize().status_code, 200)
        cache.clear()
        blocked = self.authorize()
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(blocked.data['code'], 'pin_limit_reached')
        self.assertIn('Contact', blocked.data['error'])
        self.assertNotIn(PIN, blocked.content.decode())

    def test_off_is_null_and_nothing_is_limited(self):
        self.patch_settings(privacy={'pin_limit': 1})
        off = self.patch_settings(privacy={'pin_limit': None})
        self.assertEqual(off.status_code, status.HTTP_200_OK, off.data)
        self.assertIsNone(self.stored('privacy', 'pin_limit'))
        for _ in range(3):
            cache.clear()
            self.assertEqual(self.authorize().status_code, 200)
        self.assertFalse(self.pin_reached())

    def test_only_a_whole_number_of_one_or_more_is_accepted(self):
        for bad in (0, -1, 2.5, '3', True):
            self.assertEqual(self.patch_settings(privacy={'pin_limit': bad}).status_code, 400, bad)

    def test_it_is_inactive_while_the_download_pin_is_off(self):
        self.patch_settings(privacy={'pin_limit': 1})
        self.authorize()                                  # uses the one allowed entry
        self.patch_downloads(pin_enabled=False)
        for _ in range(2):
            cache.clear()
            response = self.authorize()
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertFalse(response.data['pin_verified'])
        self.patch_downloads(pin_enabled=True)
        cache.clear()
        self.assertEqual(self.authorize().data['code'], 'pin_limit_reached')

    def test_a_new_pin_starts_its_own_count(self):
        self.patch_settings(privacy={'pin_limit': 1})
        self.authorize()
        self.assertEqual(self.used(), 1)
        self.client.force_authenticate(user=self.photographer)
        self.client.post(f'{self.detail_url}set-download-pin/', {'pin': '7777'}, format='json')
        self.client.force_authenticate(user=None)
        self.assertEqual(self.used(), 0)


class StrayPinLimitMigrationTests(AdvancedBase):
    """0009 clears the stray limit of 1 left by the old autosave-while-typing field."""

    def run_migration(self):
        module = importlib.import_module('apps.galleries.migrations.0009_clear_stray_pin_limit')
        module.clear_stray_pin_limit(django_apps, None)

    def set_design(self, design):
        type(self.gallery).objects.filter(pk=self.gallery.pk).update(design_settings=design)
        self.gallery.refresh_from_db()

    def test_a_stored_limit_of_one_is_cleared_and_the_gallery_downloads_again(self):
        self.set_design({'privacy': {'pin_limit': 1, 'pin_use_count': 3}, 'downloads': {'limit_total': 9}})
        self.assertTrue(self.pin_reached())          # silently blocking
        before = type(self.gallery).objects.get(pk=self.gallery.pk).updated_at
        self.run_migration()
        self.gallery.refresh_from_db()
        self.assertIsNone(self.gallery.design_settings['privacy']['pin_limit'])
        self.assertEqual(self.gallery.design_settings['privacy']['pin_use_count'], 3)   # kept
        self.assertEqual(self.gallery.design_settings['downloads'], {'limit_total': 9})  # untouched
        self.assertEqual(self.gallery.updated_at, before)
        self.assertFalse(self.pin_reached())
        cache.clear()
        self.assertEqual(self.authorize().status_code, status.HTTP_200_OK)

    def test_any_other_limit_and_galleries_without_one_are_left_alone(self):
        self.set_design({'privacy': {'pin_limit': 5, 'pin_use_count': 2}})
        self.run_migration()
        self.assertEqual(self.stored('privacy'), {'pin_limit': 5, 'pin_use_count': 2})
        self.set_design({})
        self.run_migration()
        self.assertEqual(self.stored(), {})
        self.set_design({'privacy': {'pin_limit': True}})
        self.run_migration()
        self.assertIs(self.stored('privacy', 'pin_limit'), True)

    def test_a_malformed_stored_value_never_crashes_the_migration(self):
        for bad in ({'privacy': 'x'}, {'privacy': None}, {'privacy': {'pin_limit': 'one'}}):
            self.set_design(bad)
            self.run_migration()
