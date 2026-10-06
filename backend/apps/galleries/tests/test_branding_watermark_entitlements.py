# backend/apps/galleries/tests/test_branding_watermark_entitlements.py
"""
Branding + Watermark plan entitlements, enforced server-side.

Rule under test: Branding (business logo) and Watermark are included only on
plans whose branding/watermark/original_download flags are on (Pro and above) while the
subscription is ACTIVE and unexpired. Free (no/pending/cancelled/expired
subscription) and Basic are refused with a 403 {'error', 'code'} body by the
API itself — the frontend's locked state is a courtesy, never the control.
"""
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from PIL import Image

from apps.galleries.models import Gallery
from apps.subscriptions.models import UserSubscription
from apps.subscriptions.testing import grant_plan

User = get_user_model()


def _image(fmt='PNG', size=(200, 100), color=(200, 30, 30), exif=False, name=None):
    out = io.BytesIO()
    img = Image.new('RGBA' if fmt == 'PNG' else 'RGB', size, color + ((255,) if fmt == 'PNG' else ()))
    kwargs = {}
    if exif and fmt == 'JPEG':
        exif_data = Image.Exif()
        exif_data[0x010F] = 'SecretCameraMaker'
        kwargs['exif'] = exif_data
    img.save(out, format=fmt, **kwargs)
    ext = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp', 'GIF': 'gif'}[fmt]
    return SimpleUploadedFile(name or f'logo.{ext}', out.getvalue(), content_type=f'image/{ext}')


class EntitlementBase(APITestCase):
    def make_user(self, name):
        return User.objects.create_user(
            email=f'{name}@kyapture.com', password='SecurePassword123!', username=name,
            display_name=name.title(),
        )

    def setUp(self):
        self.free = self.make_user('freeuser')
        self.pro = self.make_user('prouser')
        grant_plan(self.pro)
        self.free_gallery = Gallery.objects.create(
            photographer=self.free, title='Free G', slug='free-g', is_published=True, is_active=True)
        self.pro_gallery = Gallery.objects.create(
            photographer=self.pro, title='Pro G', slug='pro-g', is_published=True, is_active=True)
        self.me_url = '/api/v1/auth/me/'

    def patch_gallery(self, user, gallery, payload):
        self.client.force_authenticate(user=user)
        return self.client.patch(f'/api/v1/galleries/{gallery.slug}/', payload, format='json')


class PlanEntitlementRuleTests(EntitlementBase):
    def entitlements(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get('/api/v1/subscriptions/my-subscription/').data['entitlements']

    def test_free_user_has_no_entitlements(self):
        result = self.entitlements(self.free)
        self.assertFalse(result['branding'])
        self.assertFalse(result['watermark'])

    def test_pro_user_is_entitled(self):
        result = self.entitlements(self.pro)
        self.assertTrue(result['branding'] and result['watermark'])
        self.assertEqual(result['plan_name'], 'Pro')

    def test_basic_plan_without_the_flag_is_not_entitled(self):
        basic = self.make_user('basicuser')
        grant_plan(basic, name='Basic', includes_branding_watermark=False)
        self.assertFalse(self.entitlements(basic)['branding'])

    def test_studio_plan_is_entitled(self):
        studio = self.make_user('studiouser')
        grant_plan(studio, name='Studio')
        self.assertTrue(self.entitlements(studio)['watermark'])

    def test_expired_cancelled_and_pending_subscriptions_are_free(self):
        for name, kwargs in (
            ('expireduser', {'days': -1}),
            ('cancelleduser', {'status': UserSubscription.SubscriptionStatus.CANCELLED}),
            ('pendinguser', {'status': UserSubscription.SubscriptionStatus.PENDING}),
        ):
            user = self.make_user(name)
            grant_plan(user, **kwargs)
            self.assertFalse(self.entitlements(user)['branding'], name)

    def test_staff_are_entitled(self):
        staff = self.make_user('staffer')
        staff.is_staff = True
        staff.save(update_fields=['is_staff'])
        self.assertTrue(self.entitlements(staff)['watermark'])

    def test_plan_list_exposes_the_feature_rows_for_the_pricing_page(self):
        response = self.client.get('/api/v1/subscriptions/plans/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(
            {row['key'] for row in plan['features']} == {'branding', 'watermark', 'original_download'}
            for plan in response.data))


class WatermarkWriteGateTests(EntitlementBase):
    def test_free_user_cannot_enable_watermark(self):
        response = self.patch_gallery(self.free, self.free_gallery, {'watermark_enabled': True})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'watermark_requires_upgrade')
        self.assertIn('error', response.data)
        self.free_gallery.refresh_from_db()
        self.assertFalse(self.free_gallery.watermark_enabled)          # nothing saved

    def test_free_user_cannot_save_watermark_settings_directly_via_design_settings(self):
        response = self.patch_gallery(self.free, self.free_gallery,
                                      {'design_settings': {'watermark': {'type': 'text', 'text': 'Hi'}}})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'watermark_requires_upgrade')
        self.free_gallery.refresh_from_db()
        self.assertNotIn('watermark', self.free_gallery.design_settings)

    def test_free_user_can_still_turn_watermark_off_and_save_other_design_settings(self):
        response = self.patch_gallery(self.free, self.free_gallery,
                                      {'watermark_enabled': False, 'design_settings': {'colorPalette': 'gold'}})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_free_user_cannot_enable_it_on_create(self):
        self.client.force_authenticate(user=self.free)
        response = self.client.post('/api/v1/galleries/', {'title': 'New', 'watermark_enabled': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Gallery.objects.filter(photographer=self.free, title='New').exists())

    def test_pro_user_can_enable_and_configure_watermark(self):
        payload = {'watermark_enabled': True, 'design_settings': {
            'colorPalette': 'gold',
            'watermark': {'type': 'text', 'text': 'Pro Studio', 'position': 'top-left',
                          'opacity': 40, 'size': 25, 'margin': 5}}}
        with self.captureOnCommitCallbacks(execute=False):
            response = self.patch_gallery(self.pro, self.pro_gallery, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.pro_gallery.refresh_from_db()
        self.assertTrue(self.pro_gallery.watermark_enabled)
        block = self.pro_gallery.design_settings['watermark']
        self.assertEqual((block['text'], block['position'], block['opacity'], block['size'], block['margin']),
                         ('Pro Studio', 'top-left', 40, 25, 5))
        self.assertEqual(self.pro_gallery.design_settings['colorPalette'], 'gold')

    def test_pro_user_can_create_a_gallery_with_watermark(self):
        self.client.force_authenticate(user=self.pro)
        response = self.client.post('/api/v1/galleries/', {'title': 'New Pro', 'watermark_enabled': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_lapsed_pro_cannot_enable_but_can_disable(self):
        grant_plan(self.pro, days=-1)
        self.assertEqual(self.patch_gallery(self.pro, self.pro_gallery, {'watermark_enabled': True}).status_code, 403)
        self.assertEqual(self.patch_gallery(self.pro, self.pro_gallery, {'watermark_enabled': False}).status_code, 200)

    def test_invalid_watermark_settings_are_rejected_with_field_errors(self):
        for bad in ({'type': 'banner'}, {'position': 'nowhere'}, {'opacity': 500}, {'size': 1},
                    {'margin': 99}, {'text': 'x' * 100}, {'text': '<script>'}):
            response = self.patch_gallery(self.pro, self.pro_gallery, {'design_settings': {'watermark': bad}})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)
        self.pro_gallery.refresh_from_db()
        self.assertNotIn('watermark', self.pro_gallery.design_settings)

    def test_non_object_design_settings_is_rejected(self):
        response = self.patch_gallery(self.pro, self.pro_gallery, {'design_settings': 'nope'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_design_page_save_without_the_block_preserves_the_stored_watermark(self):
        self.patch_gallery(self.pro, self.pro_gallery,
                           {'design_settings': {'watermark': {'type': 'text', 'text': 'Keep Me'}}})
        response = self.patch_gallery(self.pro, self.pro_gallery, {'design_settings': {'colorPalette': 'dark'}})
        self.assertEqual(response.status_code, 200)
        self.pro_gallery.refresh_from_db()
        self.assertEqual(self.pro_gallery.design_settings['watermark']['text'], 'Keep Me')
        self.assertEqual(self.pro_gallery.design_settings['colorPalette'], 'dark')

    def test_lapsed_user_can_save_design_settings_that_echo_the_unchanged_block(self):
        self.patch_gallery(self.pro, self.pro_gallery,
                           {'design_settings': {'watermark': {'type': 'text', 'text': 'Echo'}}})
        stored = Gallery.objects.get(pk=self.pro_gallery.pk).design_settings['watermark']
        grant_plan(self.pro, days=-1)
        response = self.patch_gallery(self.pro, self.pro_gallery,
                                      {'design_settings': {'colorPalette': 'sand', 'watermark': stored}})
        self.assertEqual(response.status_code, 200, response.data)
        changed = dict(stored, text='Changed')
        response = self.patch_gallery(self.pro, self.pro_gallery, {'design_settings': {'watermark': changed}})
        self.assertEqual(response.status_code, 403)

    def test_explicit_null_clears_the_block(self):
        self.patch_gallery(self.pro, self.pro_gallery,
                           {'design_settings': {'watermark': {'type': 'text', 'text': 'Gone'}}})
        self.patch_gallery(self.pro, self.pro_gallery, {'design_settings': {'watermark': None}})
        self.pro_gallery.refresh_from_db()
        self.assertNotIn('watermark', self.pro_gallery.design_settings)

    def test_logo_watermark_requires_an_uploaded_logo(self):
        response = self.patch_gallery(self.pro, self.pro_gallery,
                                      {'design_settings': {'watermark': {'type': 'logo'}}})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(user=self.pro)
        self.assertEqual(self.client.put(self.me_url, {'logo': _image()}, format='multipart').status_code, 200)
        response = self.patch_gallery(self.pro, self.pro_gallery,
                                      {'design_settings': {'watermark': {'type': 'logo'}}})
        self.assertEqual(response.status_code, 200, response.data)

    def test_cannot_modify_another_photographers_gallery_or_settings(self):
        response = self.patch_gallery(self.pro, self.free_gallery,
                                      {'watermark_enabled': True,
                                       'design_settings': {'watermark': {'type': 'text'}}})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.free_gallery.refresh_from_db()
        self.assertFalse(self.free_gallery.watermark_enabled)

    def test_unauthenticated_cannot_write(self):
        self.client.force_authenticate(user=None)
        response = self.client.patch(f'/api/v1/galleries/{self.pro_gallery.slug}/',
                                     {'watermark_enabled': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_put_as_well_as_patch_is_gated(self):
        self.client.force_authenticate(user=self.free)
        response = self.client.put(f'/api/v1/galleries/{self.free_gallery.slug}/',
                                   {'watermark_enabled': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class WatermarkRegenerationTriggerTests(EntitlementBase):
    def test_changing_the_watermark_queues_background_regeneration_after_commit(self):
        with mock.patch('apps.photos.tasks.regenerate_gallery_watermarks.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.patch_gallery(self.pro, self.pro_gallery, {'watermark_enabled': True})
        self.assertEqual(response.status_code, 200)
        delay.assert_called_once_with(str(self.pro_gallery.id))

    def test_unrelated_changes_do_not_queue_regeneration(self):
        with mock.patch('apps.photos.tasks.regenerate_gallery_watermarks.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                self.patch_gallery(self.pro, self.pro_gallery, {'title': 'Renamed'})
                self.patch_gallery(self.pro, self.pro_gallery, {'design_settings': {'colorPalette': 'gold'}})
        delay.assert_not_called()

    def test_resaving_identical_watermark_settings_does_not_requeue(self):
        payload = {'watermark_enabled': True, 'design_settings': {'watermark': {'type': 'text', 'text': 'Same'}}}
        self.patch_gallery(self.pro, self.pro_gallery, payload)
        with mock.patch('apps.photos.tasks.regenerate_gallery_watermarks.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                self.patch_gallery(self.pro, self.pro_gallery, payload)
        delay.assert_not_called()

    def test_request_does_not_run_regeneration_inline(self):
        with mock.patch('apps.photos.tasks.regenerate_asset_watermark') as per_asset:
            self.patch_gallery(self.pro, self.pro_gallery, {'watermark_enabled': True})
        per_asset.assert_not_called()                  # nothing executes until on_commit/worker


class BrandingLogoTests(EntitlementBase):
    def put_logo(self, user, upload):
        self.client.force_authenticate(user=user)
        return self.client.put(self.me_url, {'logo': upload}, format='multipart')

    def test_free_user_cannot_upload_a_logo(self):
        response = self.put_logo(self.free, _image())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'branding_requires_upgrade')
        self.free.refresh_from_db()
        self.assertFalse(self.free.logo)

    def test_free_users_bad_file_gets_the_entitlement_error_without_being_decoded(self):
        junk = SimpleUploadedFile('logo.png', b'<html><script>alert(1)</script></html>', 'image/png')
        with mock.patch('apps.core.branding.Image.open') as decode:
            response = self.put_logo(self.free, junk)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'branding_requires_upgrade')
        decode.assert_not_called()

    def test_basic_plan_cannot_upload_a_logo(self):
        basic = self.make_user('basicbrand')
        grant_plan(basic, name='Basic', includes_branding_watermark=False)
        self.assertEqual(self.put_logo(basic, _image()).status_code, 403)

    def test_pro_user_can_upload_and_the_owner_gets_a_usable_url(self):
        response = self.put_logo(self.pro, _image())
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['logo'].startswith('http'))
        self.pro.refresh_from_db()
        self.assertRegex(self.pro.logo.name, rf'^photographers/{self.pro.id}/branding/logo_[0-9a-f]{{12}}\.png$')
        self.assertTrue(self.pro.logo.storage.exists(self.pro.logo.name))
        self.assertEqual(self.client.get(self.me_url).data['logo'], response.data['logo'])

    def test_logo_is_stored_in_public_media_storage_not_the_default_private_one(self):
        from apps.core.storage import PublicMediaStorage
        self.assertIsInstance(User._meta.get_field('logo').storage, PublicMediaStorage)

    def test_upload_is_reencoded_and_metadata_is_stripped(self):
        photo = _image('JPEG', size=(300, 200), exif=True)
        self.assertIn(b'SecretCameraMaker', photo.read())
        photo.seek(0)
        self.put_logo(self.pro, photo)
        self.pro.refresh_from_db()
        self.pro.logo.open('rb')
        stored = self.pro.logo.read()
        self.pro.logo.close()
        self.assertNotIn(b'SecretCameraMaker', stored)
        self.assertEqual(Image.open(io.BytesIO(stored)).format, 'JPEG')

    def test_accepted_formats(self):
        for fmt in ('PNG', 'JPEG', 'WEBP'):
            self.assertEqual(self.put_logo(self.pro, _image(fmt)).status_code, 200, fmt)

    def test_validation_rejects_bad_uploads(self):
        oversized = SimpleUploadedFile('big.png', b'\x89PNG\r\n\x1a\n' + b'0' * (2 * 1024 * 1024 + 10), 'image/png')
        svg = SimpleUploadedFile('logo.svg', b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                                 'image/svg+xml')
        html_as_png = SimpleUploadedFile('logo.png', b'<html><script>alert(1)</script></html>', 'image/png')
        text = SimpleUploadedFile('logo.txt', b'hello', 'text/plain')
        gif_out = io.BytesIO()
        frames = [Image.new('P', (40, 40), i) for i in (0, 1)]
        frames[0].save(gif_out, format='GIF', save_all=True, append_images=frames[1:])
        gif = SimpleUploadedFile('logo.gif', gif_out.getvalue(), 'image/gif')
        tiny = _image(size=(4, 4))
        huge = _image(size=(5000, 40))
        truncated = _image()
        truncated = SimpleUploadedFile('t.png', truncated.read()[:60], 'image/png')
        for label, upload in (('oversized', oversized), ('svg', svg), ('html-as-png', html_as_png),
                              ('text', text), ('animated gif', gif), ('tiny', tiny), ('huge', huge),
                              ('truncated', truncated)):
            response = self.put_logo(self.pro, upload)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, label)
            self.assertIn('logo', response.data.get('details', response.data), label)
        self.pro.refresh_from_db()
        self.assertFalse(self.pro.logo)

    def test_remove_clears_the_logo_and_deletes_the_stored_file(self):
        self.put_logo(self.pro, _image())
        self.pro.refresh_from_db()
        stored_name = self.pro.logo.name
        storage = self.pro.logo.storage
        self.client.force_authenticate(user=self.pro)
        response = self.client.put(self.me_url, {'logo': None}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data['logo'])
        self.pro.refresh_from_db()
        self.assertFalse(self.pro.logo)
        self.assertFalse(storage.exists(stored_name))

    def test_replace_uses_a_new_key_and_deletes_the_old_file(self):
        self.put_logo(self.pro, _image())
        self.pro.refresh_from_db()
        old_name, storage = self.pro.logo.name, self.pro.logo.storage
        self.put_logo(self.pro, _image(color=(0, 200, 0)))
        self.pro.refresh_from_db()
        self.assertNotEqual(self.pro.logo.name, old_name)          # fresh key => caches show the new logo
        self.assertFalse(storage.exists(old_name))
        self.assertTrue(storage.exists(self.pro.logo.name))

    def test_lapsed_user_can_remove_but_not_set_a_logo(self):
        self.put_logo(self.pro, _image())
        grant_plan(self.pro, days=-1)
        self.assertEqual(self.put_logo(self.pro, _image()).status_code, 403)
        self.client.force_authenticate(user=self.pro)
        self.assertEqual(self.client.put(self.me_url, {'logo': None}, format='json').status_code, 200)

    def test_other_profile_fields_still_save_for_free_users(self):
        self.client.force_authenticate(user=self.free)
        response = self.client.put(self.me_url, {'display_name': 'Free Person', 'bio': 'hi'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def test_one_user_cannot_touch_anothers_logo(self):
        self.put_logo(self.pro, _image())
        self.client.force_authenticate(user=self.free)
        self.client.put(self.me_url, {'logo': None}, format='json')
        self.pro.refresh_from_db()
        self.assertTrue(self.pro.logo)                              # /auth/me/ only ever edits the caller

    def test_unauthenticated_cannot_upload(self):
        self.client.force_authenticate(user=None)
        response = self.client.put(self.me_url, {'logo': _image()}, format='multipart')
        self.assertEqual(response.status_code, 401)


class ClientPayloadExposureTests(EntitlementBase):
    def public(self, user, gallery):
        self.client.force_authenticate(user=None)
        return self.client.get(f'/api/v1/public/{user.username}/{gallery.slug}/')

    def give_logo(self, user):
        self.client.force_authenticate(user=user)
        self.assertEqual(self.client.put(self.me_url, {'logo': _image()}, format='multipart').status_code, 200)

    def test_entitled_photographers_logo_is_in_the_client_payload(self):
        self.give_logo(self.pro)
        response = self.public(self.pro, self.pro_gallery)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['photographer_logo'].startswith('http'))
        self.assertIn('/branding/logo_', response.data['photographer_logo'])

    def test_logo_disappears_from_client_payload_when_the_plan_lapses_without_deleting_it(self):
        self.give_logo(self.pro)
        grant_plan(self.pro, days=-1)
        self.assertIsNone(self.public(self.pro, self.pro_gallery).data['photographer_logo'])
        self.pro.refresh_from_db()
        self.assertTrue(self.pro.logo)                              # stored, just not shown

    def test_a_free_user_with_a_legacy_logo_row_is_never_exposed(self):
        # e.g. a logo saved before the gate existed
        User.objects.filter(pk=self.free.pk).update(logo='photographers/legacy/branding/logo_legacy.png')
        self.assertIsNone(self.public(self.free, self.free_gallery).data['photographer_logo'])

    def test_no_logo_means_null(self):
        self.assertIsNone(self.public(self.pro, self.pro_gallery).data['photographer_logo'])

    def test_public_payload_does_not_leak_watermark_config_or_private_paths(self):
        self.patch_gallery(self.pro, self.pro_gallery, {
            'watermark_enabled': True,
            'design_settings': {'colorPalette': 'gold',
                                'watermark': {'type': 'text', 'text': 'SECRET-WM-TEXT', 'position': 'top-left'}}})
        self.give_logo(self.pro)
        response = self.public(self.pro, self.pro_gallery)
        body = str(response.data)
        self.assertNotIn('SECRET-WM-TEXT', body)
        self.assertNotIn('watermark', response.data['design_settings'])
        self.assertEqual(response.data['design_settings']['colorPalette'], 'gold')
        for forbidden in ('password_hash', 'download_pin_hash', 'original_file', '_original', 'download_file'):
            self.assertNotIn(forbidden, body)
        self.assertNotIn('password', {k for k in response.data if k != 'is_password_protected'})

    def test_derivative_urls_carry_the_watermark_version(self):
        from apps.photos.models import MediaAsset
        from django.core.files.base import ContentFile
        asset = MediaAsset(gallery=self.pro_gallery, media_type='image', original_name='a.jpg', file_size=10,
                           processing_status='ready', watermark_signature='abc123def456')
        asset.original_file.save('a.jpg', ContentFile(b'x'), save=False)
        asset.display_file.save('a.d.webp', ContentFile(b'x'), save=False)
        asset.thumbnail_file.save('a.t.webp', ContentFile(b'x'), save=False)
        asset.save()
        photo = self.public(self.pro, self.pro_gallery).data['photos'][0]
        self.assertTrue(photo['display_url'].endswith('?v=abc123def456'))
        self.assertTrue(photo['thumbnail_url'].endswith('?v=abc123def456'))
        self.assertNotIn('original', photo['display_url'])
