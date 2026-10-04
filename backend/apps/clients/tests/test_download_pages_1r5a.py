# backend/apps/clients/tests/test_download_pages_1r5a.py
"""
Task 1R.5-A — the standalone download pages (Page 1 email/PIN, Page 2 Choose
Photos) lean on three server facts, all pinned here:

  - the public policy tells the page whether the total download limit has
    been reached (a yes/no only) and never leaks the contacts list
  - several photo sets can be requested at once (`set_ids`); each must be one
    of THIS gallery's sets and enabled for download
  - email and PIN are still enforced by the server on a direct call, with the
    friendly blocked-case messages
"""
from django.core.cache import cache
from rest_framework import status

from apps.clients.models import DownloadLog
from apps.clients.tests.test_download_access_flow import PIN, DownloadFlowBase, _asset, _zip_entries
from apps.clients.tests.test_download_advanced_1r6c import AdvancedBase
from apps.photos.models import PhotoSet


class PolicyForThePagesTests(AdvancedBase):
    with_pin = False

    def policy(self):
        return self.client.get(self.base).data['download_policy']

    def test_limit_reached_is_a_plain_boolean_and_hides_the_limit(self):
        self.assertIs(self.policy()['limit_reached'], False)
        self.patch_downloads(limit_total=2)
        self.log(photo_count=1)
        policy = self.policy()
        self.assertIs(policy['limit_reached'], False)
        self.log(photo_count=1)
        policy = self.policy()
        self.assertIs(policy['limit_reached'], True)
        self.assertNotIn('limit_total', policy)

    def test_the_contacts_list_is_never_in_the_public_payload(self):
        self.patch_downloads(restrict_contacts=True, allowed_emails=['secret@example.com'])
        response = self.client.get(self.base)
        self.assertNotIn('secret@example.com', str(response.data))
        policy = response.data['download_policy']
        self.assertNotIn('allowed_emails', policy)
        self.assertTrue(policy['require_email'])     # the page must ask for an email

    def test_only_enabled_sets_are_listed_in_the_policy(self):
        self.patch_downloads(sets_enabled=[str(self.ceremony.id)])
        self.assertEqual(self.policy()['sets_enabled'], [str(self.ceremony.id)])


class MultiSetSelectionTests(DownloadFlowBase):
    with_pin = False

    def setUp(self):
        super().setUp()
        self.extras = PhotoSet.objects.create(gallery=self.gallery, name="Extras", order=3)
        self.c1 = _asset(self.gallery, "c1.jpg", self.extras, order=4)

    def names(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK, getattr(response, 'data', None))
        return sorted(_zip_entries(response))

    def test_two_sets_package_exactly_their_photos(self):
        response = self.zip(email="a@example.com", set_ids=[str(self.ceremony.id), str(self.party.id)])
        names = self.names(response)
        self.assertEqual(len(names), 3)
        self.assertFalse(any('c1' in name for name in names))

    def test_a_single_id_behaves_like_set_id(self):
        names = self.names(self.zip(email="a@example.com", set_ids=[str(self.extras.id)]))
        self.assertEqual(len(names), 1)
        self.assertIn('c1', names[0])

    def test_a_foreign_or_malformed_set_is_refused_not_widened(self):
        other = PhotoSet.objects.create(
            gallery=type(self.gallery).objects.create(
                photographer=self.photographer, title="Other", slug="other-gallery",
                is_published=True, is_active=True, allow_download=True,
            ),
            name="Foreign", order=1,
        )
        for bad in (str(other.id), 'not-a-uuid'):
            cache.clear()
            response = self.zip(email="a@example.com", set_ids=[str(self.ceremony.id), bad])
            self.assertEqual((response.status_code, response.data['code']), (404, 'set_not_found'), bad)

    def test_set_id_and_set_ids_together_are_refused(self):
        response = self.zip(
            email="a@example.com", set_id=str(self.ceremony.id), set_ids=[str(self.party.id)],
        )
        self.assertEqual((response.status_code, response.data['code']), (400, 'set_conflict'))

    def test_a_disabled_set_cannot_ride_along_in_set_ids(self):
        self.gallery.design_settings = {'downloads': {'sets_enabled': [str(self.ceremony.id)]}}
        self.gallery.save(update_fields=['design_settings'])
        response = self.zip(email="a@example.com", set_ids=[str(self.ceremony.id), str(self.party.id)])
        self.assertEqual((response.status_code, response.data['code']), (403, 'set_not_enabled'))

    def test_every_enabled_set_may_be_requested_when_the_gallery_is_restricted(self):
        self.gallery.design_settings = {
            'downloads': {'sets_enabled': [str(self.ceremony.id), str(self.party.id)]},
        }
        self.gallery.save(update_fields=['design_settings'])
        names = self.names(self.zip(email="a@example.com", set_ids=[str(self.ceremony.id), str(self.party.id)]))
        self.assertEqual(len(names), 3)

    def test_set_ids_must_be_a_list(self):
        response = self.zip(email="a@example.com", set_ids=str(self.ceremony.id))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ServerEnforcesTheGateTests(DownloadFlowBase):
    """Page 1 is presentation only: skipping it by URL/API gets nowhere."""

    def test_prepare_without_a_token_is_refused_when_a_pin_is_set(self):
        response = self.client.post(f"{self.base}download/", {'resolution': 'web'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'download_access_required')

    def test_a_wrong_pin_is_incorrect_and_a_missing_one_is_required(self):
        wrong = self.client.post(self.access_url, {'email': 'a@example.com', 'pin': '0000'}, format='json')
        self.assertEqual((wrong.status_code, wrong.data['code']), (401, 'invalid_pin'))
        cache.clear()
        missing = self.client.post(self.access_url, {'email': 'a@example.com'}, format='json')
        self.assertEqual((missing.status_code, missing.data['code']), (401, 'pin_required'))

    def test_a_pin_alone_is_not_enough_when_an_email_is_required(self):
        response = self.client.post(self.access_url, {'pin': PIN}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (400, 'email_required'))

    def test_an_unlisted_email_gets_the_friendly_message_without_the_list(self):
        self.gallery.design_settings = {
            'downloads': {'restrict_contacts': True, 'allowed_emails': ['vip@example.com']},
        }
        self.gallery.save(update_fields=['design_settings'])
        response = self.client.post(self.access_url, {'email': 'x@example.com', 'pin': PIN}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (403, 'email_not_authorized'))
        self.assertIn('This email is not authorized to download. Contact', response.data['error'])
        self.assertNotIn('vip@example.com', response.data['error'])

    def test_the_limit_message_names_the_studio(self):
        self.gallery.design_settings = {'downloads': {'limit_total': 1}}
        self.gallery.save(update_fields=['design_settings'])
        DownloadLog.objects.create(gallery=self.gallery, photo_count=1)
        token = self.token()
        response = self.zip(token=token, set_ids=[str(self.ceremony.id), str(self.party.id)])
        self.assertEqual((response.status_code, response.data['code']), (403, 'download_limit_reached'))
        self.assertIn('Download limit reached. Contact', response.data['error'])
