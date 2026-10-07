# backend/apps/clients/tests/test_deterrence_7d.py
"""
CHUNK 7-D - the server half of the client-gallery deterrence layer.

7-B already made originals and Download Masters private (random key part, signed
one-hour URLs) and left only derivatives public. 7-D adds no new server rule; this
file PROVES that a visitor-facing payload still carries nothing else, on every
public route that returns media, so the browser-side deterrence (no right-click
menu or drag on the media, utils/mediaDeterrence.js) only ever sits on a
watermarked derivative:

  - every URL in the gallery payload, the paginated photos route and a favorites
    list is either a public derivative key (the exact names PublicMediaStorage
    writes, apps/core/media.py::is_public_path) or a gated app endpoint
    (/api/v1/public/...): never an original, a Download Master or a signed URL;
  - the derivative URL carries the watermark version (`?v=`), so a stale
    un-watermarked copy cannot be served from a browser or CDN cache once the
    watermark changes;
  - a signed private URL is short-lived (an hour) and a stale one is refused,
    which is what the owner's own `original_url` and the downloads use.

This is deterrence, not protection: a derivative is still a viewable image.
"""
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.files.base import ContentFile
from rest_framework import status

from apps.clients.tests.test_favorite_lists import FavBase
from apps.core.media import is_public_path
from apps.core.storage import LOCAL_SIGNED_URL_SALT
from apps.photos.models import (
    MediaAsset,
    get_display_photo_path,
    get_medium_photo_path,
    get_thumbnail_photo_path,
    get_video_poster_path,
    get_video_playback_path,
)

PRIVATE_NAMES = ('_original', '_download')


def _urls(value):
    """Every string that looks like a URL anywhere in a JSON-able payload."""
    if isinstance(value, str):
        if value.startswith(('http://', 'https://', '/')):
            yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _urls(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _urls(item)


class PublicPayloadCarriesDerivativesOnlyTests(FavBase):
    """Real-shaped storage keys (the model's own path functions), not placeholder strings."""

    def setUp(self):
        super().setUp()
        for index, asset in enumerate(self.photos):
            asset.original_file.save(f'o{index}.jpg', ContentFile(b'\xff\xd8\xff\xe0-original'), save=False)
            asset.download_file.save(f'o{index}.jpg', ContentFile(b'\xff\xd8\xff\xe0-master'), save=False)
            asset.display_file = get_display_photo_path(asset, 'x')
            asset.medium_file = get_medium_photo_path(asset, 'x')
            asset.thumbnail_file = get_thumbnail_photo_path(asset, 'x')
            asset.watermark_signature = 'abc123'
            asset.save()
        self.video = MediaAsset(
            gallery=self.gallery, media_type='video', original_name='clip.mp4', file_size=10, order=9,
            processing_status='ready',
        )
        self.video.original_file.save('clip.mp4', ContentFile(b'video-original'), save=False)
        self.video.save()
        self.video.poster_image = get_video_poster_path(self.video, 'x')
        self.video.playback_file = get_video_playback_path(self.video, 'x')
        self.video.save(update_fields=['poster_image', 'playback_file'])
        self.gallery.allow_download = True
        self.gallery.save(update_fields=['allow_download'])

    def _assert_only_derivatives(self, payload, where):
        urls = list(_urls(payload))
        self.assertTrue(urls, f'{where}: expected URLs in the payload')
        for url in urls:
            parsed = urlparse(url)
            self.assertNotIn('sig', parse_qs(parsed.query), f'{where}: signed URL leaked: {url}')
            for name in PRIVATE_NAMES:
                self.assertNotIn(name, parsed.path, f'{where}: private file name in {url}')
            if parsed.path.startswith('/api/v1/public/'):
                continue                      # a gated app endpoint (download / video stream)
            self.assertTrue(parsed.path.startswith(settings.MEDIA_URL), f'{where}: not a media URL: {url}')
            relative = parsed.path[len(settings.MEDIA_URL):]
            self.assertTrue(is_public_path(relative), f'{where}: not a public derivative: {url}')

    def test_gallery_payload_is_derivatives_only(self):
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['photos']), len(self.photos) + 1)
        self._assert_only_derivatives(response.data['photos'], 'gallery payload')

    def test_paginated_photos_route_is_derivatives_only(self):
        response = self.client.get(f'{self.base}photos/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self._assert_only_derivatives(response.data['results'], 'photos route')

    def test_a_favorites_list_is_derivatives_only(self):
        visitor = self.visitor()
        self.heart(visitor, 'deter-uid', self.photos[0])
        self.heart(visitor, 'deter-uid', self.photos[1])
        listing = self.lists(visitor, 'deter-uid')
        self.assertEqual(listing.status_code, 200, listing.data)
        list_id = listing.data['results'][0]['id']
        response = visitor.get(f'{self.base}favorites/lists/{list_id}/', {'client_uid': 'deter-uid'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['results']), 2)
        self._assert_only_derivatives(response.data['results'], 'favorites list')
        self._assert_only_derivatives(listing.data['results'], 'favorites lists')

    def test_the_payload_has_no_original_or_master_field(self):
        photo = self.client.get(self.base).data['photos'][0]
        # `original_name` is the file's label, not a path; every private field is absent.
        forbidden = {'original_url', 'original_file', 'download_file', 'download_url_private', 'storage_path'}
        self.assertEqual(forbidden & set(photo), set())

    def test_a_derivative_url_carries_the_watermark_version(self):
        photo = next(p for p in self.client.get(self.base).data['photos'] if p['media_type'] == 'image')
        for field in ('display_url', 'medium_url', 'thumbnail_url'):
            self.assertEqual(parse_qs(urlparse(photo[field]).query).get('v'), ['abc123'], field)

    def test_the_video_is_served_through_the_gated_stream_or_a_public_derivative(self):
        video = next(p for p in self.client.get(self.base).data['photos'] if p['media_type'] == 'video')
        self.assertIn('/api/v1/public/', video['playback_url'])
        self.assertTrue(is_public_path(urlparse(video['poster_url']).path[len(settings.MEDIA_URL):]))


class PrivateUrlsAreShortLivedTests(FavBase):
    """The private side of the audit: what the owner and the download endpoints hand out."""

    def setUp(self):
        super().setUp()
        cache.clear()
        asset = self.photos[0]
        asset.original_file.save('own.jpg', ContentFile(b'\xff\xd8\xff\xe0-original'), save=True)
        self.asset = asset

    def test_a_private_original_url_is_signed_and_the_signature_expires(self):
        url = self.asset.original_file.url
        sig = parse_qs(urlparse(url).query)['sig'][0]
        path = urlparse(url).path[len(settings.MEDIA_URL):]
        signer = signing.TimestampSigner(salt=LOCAL_SIGNED_URL_SALT)
        self.assertEqual(signer.unsign(f'{path}:{sig}', max_age=3600), path)
        with self.assertRaises(signing.SignatureExpired):
            signer.unsign(f'{path}:{sig}', max_age=-1)

    def test_an_unsigned_request_for_the_private_original_is_a_404(self):
        path = urlparse(self.asset.original_file.url).path
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get(path, {'sig': 'bogus'}).status_code, 404)

    def test_the_original_key_is_not_derivable_from_a_public_derivative(self):
        derivative = get_display_photo_path(self.asset, 'x')
        guess = derivative.replace('_display.webp', '_original.jpg')
        self.assertNotEqual(guess, self.asset.original_file.name)
        self.assertFalse(is_public_path(self.asset.original_file.name))
