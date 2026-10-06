# C:/Users/LENOVO/Desktop/kyapture/backend/apps/galleries/tests/test_typography_settings.py
"""
CHUNK 6.2-A: typography settings (backend). One key, `design_settings.typography`,
one of six named style ids; the family/weight/spacing/case are server constants.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.typography import (
    DEFAULT_TYPOGRAPHY, TYPOGRAPHY_IDS, TYPOGRAPHY_STYLES, resolve_typography,
)
from apps.galleries.models import Gallery

User = get_user_model()

SIX = ('sans', 'serif', 'modern', 'timeless', 'bold', 'subtle')
SETTINGS = '/api/v1/auth/settings/'


class TypographyBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='typo-owner@kyapture.com', password='SecurePassword123!', username='typoowner')
        self.other = User.objects.create_user(
            email='typo-other@kyapture.com', password='SecurePassword123!', username='typoother')
        self.gallery = Gallery.objects.create(
            photographer=self.owner, title='Typo', slug='typo', is_published=True, is_active=True)
        self.url = f'/api/v1/galleries/{self.gallery.slug}/'
        self.public_url = f'/api/v1/public/{self.owner.username}/{self.gallery.slug}/'
        self.client.force_authenticate(user=self.owner)

    def patch(self, design, user=None):
        if user is not None:
            self.client.force_authenticate(user=user)
        return self.client.patch(self.url, {'design_settings': design}, format='json')

    def stored(self):
        self.gallery.refresh_from_db()
        return self.gallery.design_settings


class TypographyTableTests(APITestCase):
    def test_exactly_the_six_pixieset_ids(self):
        self.assertEqual(TYPOGRAPHY_IDS, SIX)
        self.assertIn(DEFAULT_TYPOGRAPHY, SIX)

    def test_every_style_is_complete_and_has_a_system_fallback(self):
        for style_id, style in TYPOGRAPHY_STYLES.items():
            self.assertEqual(
                set(style) - {'label', 'description', 'family', 'family_key'},
                {'font_family', 'weight', 'font_style', 'letter_spacing', 'text_transform'}, style_id)
            self.assertTrue(style['font_family'].startswith(f'"{style["family"]}", '), style_id)
            self.assertRegex(style['font_family'], r'(sans-serif|serif)$', style_id)
            self.assertIn(style['weight'], (300, 400, 500, 600, 700))
            self.assertIn(style['font_style'], ('normal', 'italic'))
            self.assertIn(style['text_transform'], ('none', 'uppercase'))
            # Nothing that could break out of a declaration if it ever reached a stylesheet.
            for value in (style['font_family'], style['letter_spacing']):
                self.assertNotRegex(value, r'[;{}<>\\]|url\(|@import')

    def test_resolve_never_raises_and_falls_back_to_the_default(self):
        for bad in (None, '', 'comic-sans', 'SERIF', 5, ['bold'], {'a': 1}, 'bold; color:red'):
            self.assertEqual(resolve_typography(bad)['id'], DEFAULT_TYPOGRAPHY, bad)
        self.assertEqual(resolve_typography('bold')['id'], 'bold')


class TypographyCatalogEndpointTests(TypographyBase):
    """CHUNK 6.2-B: the Design page / Collection Defaults / Preview read the six styles from the server."""
    CATALOG = '/api/v1/galleries/typography-styles/'

    def test_returns_all_six_in_order_with_label_description_and_mapping(self):
        response = self.client.get(self.CATALOG)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['default'], DEFAULT_TYPOGRAPHY)
        styles = response.data['styles']
        self.assertEqual([s['id'] for s in styles], list(SIX))
        for style in styles:
            table = TYPOGRAPHY_STYLES[style['id']]
            self.assertEqual(style['label'], table['label'])
            self.assertTrue(style['description'].startswith('A ') and style['description'].endswith(' font'))
            for key in ('family_key', 'font_family', 'weight', 'font_style', 'letter_spacing', 'text_transform'):
                self.assertEqual(style[key], table[key])
            self.assertNotIn('family', style)

    def test_is_static_and_ignores_any_stored_value(self):
        Gallery.objects.filter(pk=self.gallery.pk).update(design_settings={'typography': 'x; color:red'})
        self.assertEqual(self.client.get(self.CATALOG).data['styles'], self.client.get(self.CATALOG).data['styles'])
        self.assertNotIn('color:red', str(self.client.get(self.CATALOG).data))

    def test_requires_sign_in(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.CATALOG).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_public_gallery_payload_does_not_carry_the_blurb(self):
        style = self.client.get(self.public_url).data['typography_style']
        self.assertNotIn('description', style)
        self.assertNotIn('label', style)


class TypographySaveTests(TypographyBase):
    def test_each_of_the_six_ids_saves_and_comes_back(self):
        for style_id in SIX:
            response = self.patch({'typography': style_id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, (style_id, response.data))
            self.assertEqual(response.data['design_settings']['typography'], style_id)
            self.assertEqual(self.stored()['typography'], style_id)

    def test_unknown_or_free_text_style_is_rejected_and_nothing_changes(self):
        self.patch({'typography': 'bold'})
        for bad in ('comic-sans', 'Inter', 'SERIF', '', 'bold; color:red', 'url(http://evil.test/x.woff)',
                    '"><script>', 12, True, ['bold'], {'family': 'Inter'}):
            response = self.patch({'typography': bad})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)
            self.assertIn('typography', response.data['design_settings'], bad)
        self.assertEqual(self.stored(), {'typography': 'bold'})

    def test_other_presentation_keys_use_the_same_allowlists(self):
        self.patch({'typography': 'sans'})
        for bad in ({'colorPalette': 'hotpink'}, {'gridStyle': 'diagonal'}, {'thumbSize': '20px'},
                    {'layout': 'url(x)'}, {'gridSpacing': 999}, {'gridSpacing': '16px'}, {'gridSpacing': True}):
            self.assertEqual(self.patch(bad).status_code, status.HTTP_400_BAD_REQUEST, bad)
        self.assertEqual(self.patch({'colorPalette': 'gold', 'gridSpacing': 12}).status_code, 200)
        self.assertEqual(self.stored(), {'typography': 'sans', 'colorPalette': 'gold', 'gridSpacing': 12})

    def test_null_resets_typography_to_the_app_default(self):
        self.patch({'typography': 'bold', 'colorPalette': 'sea'})
        self.assertEqual(self.patch({'typography': None}).status_code, 200)
        self.assertEqual(self.stored(), {'colorPalette': 'sea'})
        self.assertEqual(self.client.get(self.public_url).data['typography_style']['id'], DEFAULT_TYPOGRAPHY)

    def test_partial_patch_keeps_watermark_branding_slideshow_downloads_and_privacy(self):
        keep = {
            'watermark': {'type': 'text', 'text': 'Mine', 'position': 'center', 'opacity': 40, 'size': 20, 'margin': 4},
            'branding': {'logo': 'kept'},
            'slideshow': {'enabled': True, 'seconds': 5},
            'downloads': {'require_email': False, 'limit_total': 9},
            'privacy': {'pin_limit': 3, 'pin_use_count': 2},
            'colorPalette': 'gold',
        }
        Gallery.objects.filter(pk=self.gallery.pk).update(design_settings=dict(keep))
        response = self.patch({'typography': 'timeless'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        saved = self.stored()
        self.assertEqual(saved['typography'], 'timeless')
        for key, value in keep.items():
            self.assertEqual(saved[key], value, key)
        # A second, unrelated presentation save still keeps typography and the rest.
        self.assertEqual(self.patch({'gridSpacing': 8}).status_code, 200)
        saved = self.stored()
        self.assertEqual((saved['typography'], saved['gridSpacing']), ('timeless', 8))
        self.assertEqual(saved['slideshow'], keep['slideshow'])
        self.assertEqual(saved['watermark'], keep['watermark'])

    def test_explicit_watermark_null_still_clears_only_the_watermark(self):
        Gallery.objects.filter(pk=self.gallery.pk).update(design_settings={
            'watermark': {'type': 'text', 'text': 'Mine', 'position': 'center', 'opacity': 40, 'size': 20, 'margin': 4},
            'typography': 'bold', 'slideshow': {'enabled': True}})
        self.assertEqual(self.patch({'watermark': None}).status_code, 200)
        self.assertEqual(self.stored(), {'typography': 'bold', 'slideshow': {'enabled': True}})

    def test_foreign_gallery_is_404_and_untouched(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.patch(self.url, {'design_settings': {'typography': 'bold'}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.stored(), {})

    def test_anonymous_cannot_write(self):
        self.client.force_authenticate(user=None)
        response = self.client.patch(self.url, {'design_settings': {'typography': 'bold'}}, format='json')
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(self.stored(), {})


class TypographyPublicPayloadTests(TypographyBase):
    def test_old_gallery_with_no_settings_renders_the_app_default(self):
        self.assertEqual(self.stored(), {})
        response = self.client.get(self.public_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['design_settings'], {})
        self.assertEqual(response.data['typography_style'], resolve_typography(DEFAULT_TYPOGRAPHY))

    def test_saved_style_is_returned_as_the_mapped_presentation_only(self):
        self.patch({'typography': 'modern'})
        style = self.client.get(self.public_url).data['typography_style']
        self.assertEqual(style, resolve_typography('modern'))
        self.assertEqual(set(style), {'id', 'family_key', 'font_family', 'weight', 'font_style',
                                      'letter_spacing', 'text_transform'})

    def test_legacy_or_tampered_stored_values_never_reach_the_client(self):
        Gallery.objects.filter(pk=self.gallery.pk).update(design_settings={
            'typography': 'Comic Sans; background:url(//evil.test)', 'colorPalette': 'gold',
            'gridSpacing': '99px', 'layout': {'x': 1}})
        data = self.client.get(self.public_url).data
        self.assertEqual(data['typography_style']['id'], DEFAULT_TYPOGRAPHY)
        self.assertEqual(data['design_settings'], {'colorPalette': 'gold'})
        self.assertNotIn('evil', str(data))

    def test_private_blocks_and_unknown_keys_are_not_public(self):
        Gallery.objects.filter(pk=self.gallery.pk).update(design_settings={
            'typography': 'bold',
            'watermark': {'type': 'text', 'text': 'SECRET-MARK'},
            'downloads': {'allowed_emails': ['client@example.com'], 'limit_total': 4},
            'privacy': {'pin_limit': 3, 'pin_use_count': 1},
            'slideshow': {'enabled': True}, 'branding': {'x': 1}, 'notes': 'private note'})
        data = self.client.get(self.public_url).data
        self.assertEqual(data['design_settings'], {'typography': 'bold'})
        text = str(data)
        for secret in ('SECRET-MARK', 'client@example.com', 'pin_use_count', 'private note', 'slideshow'):
            self.assertNotIn(secret, text)


class CollectionDefaultsTypographyTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='typo-defaults@kyapture.com', password='SecurePassword123!', username='typodefaults')
        self.client.force_authenticate(user=self.user)

    def put(self, design):
        return self.client.patch(SETTINGS, {'collection_defaults': {'design': design}}, format='json')

    def test_defaults_accept_the_same_six_ids(self):
        for style_id in SIX:
            self.assertEqual(self.put({'typography': style_id}).status_code, 200, style_id)
            self.user.refresh_from_db()
            self.assertEqual(self.user.collection_defaults, {'design': {'typography': style_id}})

    def test_defaults_reject_an_unknown_id_and_keep_the_previous_value(self):
        self.put({'typography': 'bold'})
        for bad in ('comic-sans', 'Inter', '', None, 3, ['bold']):
            self.assertEqual(self.put({'typography': bad}).status_code, 400, bad)
        self.user.refresh_from_db()
        self.assertEqual(self.user.collection_defaults, {'design': {'typography': 'bold'}})

    def test_new_collection_starts_with_the_default_style_and_a_missing_one_is_fine(self):
        self.put({'typography': 'subtle'})
        created = self.client.post('/api/v1/galleries/', {'title': 'From defaults'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(Gallery.objects.get(slug=created.data['slug']).design_settings['typography'], 'subtle')
        # A user with no defaults: the gallery has no typography key and renders the app default.
        self.user.collection_defaults = {}
        self.user.save(update_fields=['collection_defaults'])
        plain = self.client.post('/api/v1/galleries/', {'title': 'No defaults'}, format='json')
        gallery = Gallery.objects.get(slug=plain.data['slug'])
        self.assertNotIn('typography', gallery.design_settings)
        gallery.is_published = True
        gallery.save(update_fields=['is_published'])
        public = self.client.get(f'/api/v1/public/{self.user.username}/{gallery.slug}/')
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.data['typography_style']['id'], DEFAULT_TYPOGRAPHY)
