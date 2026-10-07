# backend/apps/galleries/tests/test_partial_save_7f.py
"""
7F (reviewer 7R, F2 / row 152): a gallery PATCH changes only the keys it names.

Before 7F a `design_settings.downloads` block that left keys out reset them to
defaults (a size that was Off came back On, restrict_contacts went Off, the set
choice and the download limit were cleared) and a `privacy` block without
`pin_limit` removed the PIN usage limit. One test per key: the stored value is
set first, then a PATCH that does not name the key must leave it as it was.
An explicit value (including null where null means Off) still changes it.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.photos.models import PhotoSet
from apps.subscriptions.testing import grant_plan

User = get_user_model()

STORED_DOWNLOADS = {
    'require_email': False,
    'high_res': {'enabled': False, 'mode': '3600'},
    'web': {'enabled': True, 'px': 640},
    'limit_total': 40,
    'restrict_contacts': True,
    'allowed_emails': ['listed@example.com'],
    'pin_enabled': False,
}


class PartialSaveBase(APITestCase):
    def setUp(self):
        self.photographer = User.objects.create_user(
            email='partial7f@kyapture.com', password='SecurePassword123!', username='partial7f',
        )
        self.gallery = Gallery.objects.create(photographer=self.photographer, title='Partial', slug='partial-7f')
        self.ceremony = PhotoSet.objects.create(gallery=self.gallery, name='Ceremony', order=1)
        self.party = PhotoSet.objects.create(gallery=self.gallery, name='Party', order=2)
        self.client.force_authenticate(user=self.photographer)
        self.url = f'/api/v1/galleries/{self.gallery.slug}/'
        saved = self.patch(downloads=dict(STORED_DOWNLOADS, sets_enabled=[str(self.ceremony.id)]),
                           privacy={'pin_limit': 7})
        self.assertEqual(saved.status_code, 200, saved.data)

    def patch(self, **blocks):
        return self.client.patch(self.url, {'design_settings': blocks}, format='json')

    def stored(self, *path):
        value = Gallery.objects.get(pk=self.gallery.pk).design_settings
        for key in path:
            value = value[key]
        return value

    def unrelated_save(self):
        """The reviewer's example: only the Web Size switch is named."""
        response = self.patch(downloads={'web': {'enabled': True}})
        self.assertEqual(response.status_code, 200, response.data)


class OmittedDownloadKeysKeepTheirStoredValueTests(PartialSaveBase):
    def test_high_res_enabled(self):
        self.unrelated_save()
        self.assertFalse(self.stored('downloads', 'high_res', 'enabled'))
        self.assertEqual(self.stored('downloads', 'allowed_sizes'), ['web'])

    def test_high_res_mode(self):
        grant_plan(self.photographer)
        self.patch(downloads={'high_res': {'enabled': True, 'mode': 'original'}})
        self.patch(downloads={'high_res': {'enabled': True}})
        self.assertEqual(self.stored('downloads', 'high_res', 'mode'), 'original')

    def test_web_enabled(self):
        self.patch(downloads={'high_res': {'enabled': True}, 'web': {'enabled': False}})
        response = self.patch(downloads={'high_res': {'mode': '3600'}})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(self.stored('downloads', 'web', 'enabled'))
        self.assertEqual(self.stored('downloads', 'allowed_sizes'), ['download'])

    def test_web_px(self):
        self.unrelated_save()
        self.assertEqual(self.stored('downloads', 'web', 'px'), 640)

    def test_require_email(self):
        self.unrelated_save()
        self.assertFalse(self.stored('downloads', 'require_email'))

    def test_restrict_contacts(self):
        self.unrelated_save()
        self.assertTrue(self.stored('downloads', 'restrict_contacts'))

    def test_allowed_emails(self):
        self.unrelated_save()
        self.assertEqual(self.stored('downloads', 'allowed_emails'), ['listed@example.com'])

    def test_sets_enabled(self):
        self.unrelated_save()
        self.assertEqual(self.stored('downloads', 'sets_enabled'), [str(self.ceremony.id)])

    def test_limit_total(self):
        self.unrelated_save()
        self.assertEqual(self.stored('downloads', 'limit_total'), 40)

    def test_pin_enabled(self):
        self.unrelated_save()
        self.assertFalse(self.stored('downloads', 'pin_enabled'))

    def test_only_the_named_key_changed(self):
        before = self.stored('downloads')
        response = self.patch(downloads={'web': {'px': 2048}})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.stored('downloads'), dict(before, web={'enabled': True, 'px': 2048}))

    def test_an_empty_block_changes_nothing(self):
        before = self.stored('downloads')
        self.assertEqual(self.patch(downloads={}).status_code, 200)
        self.assertEqual(self.stored('downloads'), before)


class ExplicitValuesStillChangeTests(PartialSaveBase):
    def test_null_still_turns_a_limit_or_set_choice_off(self):
        response = self.patch(downloads={'limit_total': None, 'sets_enabled': None}, privacy={'pin_limit': None})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(self.stored('downloads', 'limit_total'))
        self.assertIsNone(self.stored('downloads', 'sets_enabled'))
        self.assertIsNone(self.stored('privacy', 'pin_limit'))

    def test_named_values_are_validated_and_saved(self):
        response = self.patch(downloads={'restrict_contacts': False, 'allowed_emails': [], 'require_email': True})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(self.stored('downloads', 'restrict_contacts'))
        self.assertEqual(self.stored('downloads', 'allowed_emails'), [])
        self.assertTrue(self.stored('downloads', 'require_email'))
        self.assertEqual(self.patch(downloads={'limit_total': 0}).status_code, 400)
        self.assertEqual(self.stored('downloads', 'limit_total'), 40)

    def test_turning_the_only_on_size_off_is_still_refused(self):
        self.assertEqual(self.patch(downloads={'web': {'enabled': False}}).status_code, 400)

    def test_the_legacy_allowed_sizes_shape_still_decides_the_sizes(self):
        response = self.patch(downloads={'allowed_sizes': ['download']})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.stored('downloads', 'allowed_sizes'), ['download'])
        self.assertEqual(self.stored('downloads', 'limit_total'), 40)

    def test_a_kept_original_mode_is_not_a_new_pro_choice(self):
        """A lapsed Pro can still save other download keys; the download path falls back to 3600 by itself."""
        grant_plan(self.photographer)
        self.patch(downloads={'high_res': {'enabled': True, 'mode': 'original'}})
        grant_plan(self.photographer, days=-1)          # the plan has lapsed
        response = self.patch(downloads={'limit_total': 12})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.stored('downloads', 'high_res', 'mode'), 'original')
        refused = self.patch(downloads={'high_res': {'enabled': True, 'mode': 'original'}, 'limit_total': 13})
        self.assertEqual(refused.status_code, 200, refused.data)   # same as stored: not a change


class OmittedPrivacyAndWatermarkKeysTests(PartialSaveBase):
    def test_privacy_block_without_pin_limit_keeps_the_limit(self):
        response = self.patch(privacy={})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.stored('privacy', 'pin_limit'), 7)

    def test_watermark_block_naming_one_key_keeps_the_others(self):
        grant_plan(self.photographer)
        first = self.patch(watermark={'type': 'text', 'text': 'STUDIO 7F', 'position': 'top-left', 'opacity': 40})
        self.assertEqual(first.status_code, 200, first.data)
        response = self.patch(watermark={'opacity': 70})
        self.assertEqual(response.status_code, 200, response.data)
        stored = self.stored('watermark')
        self.assertEqual((stored['text'], stored['position'], stored['opacity']), ('STUDIO 7F', 'top-left', 70))
