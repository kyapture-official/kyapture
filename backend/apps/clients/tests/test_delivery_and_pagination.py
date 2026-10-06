# backend/apps/clients/tests/test_delivery_and_pagination.py
"""
Phase 2 tests — item G, DELIVERY and GALLERY checklists.

DELIVERY:
  - private original is never reachable through any public serializer
    field or unauthenticated endpoint
  - a password-protected gallery's photo download / video stream /
    paginated photos endpoints all require a valid session token
  - a public derivative (thumbnail/medium/display/poster/playback) is
    reachable without any password gate on an open gallery
  - original_file uses PrivateMediaStorage, derivative fields use
    PublicMediaStorage (storage-class boundary, mirrors the same check
    already made for video in test_video_pipeline.py, extended to images
    and to the public API layer)

GALLERY (pagination):
  - PublicGalleryView's first page + photos_count/photos_has_more/
    photos_page_size fields behave correctly at exactly the page
    boundary and beyond it
  - PublicGalleryPhotosView serves the correct subsequent-page envelope
    and enforces the same password gate as the main gallery endpoint
"""
import bcrypt
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.core.storage import PrivateMediaStorage, PublicMediaStorage
from apps.core.pagination import GalleryMediaPagination

User = get_user_model()


def _make_ready_asset(gallery, index, media_type=MediaAsset.MediaType.IMAGE):
    """
    Builds a single READY MediaAsset with plausible derivative paths.

    original_file is written as a REAL backing file (via .save(), not
    just a string path assignment) so tests that actually open/stream it
    (the download endpoint) exercise real bytes through real storage,
    not just URL-string plumbing. The derivative fields are left as bare
    path assignments — nothing under test ever opens their bytes, only
    builds a URL from the field name, which FileSystemStorage does with
    no existence check.
    """
    base = f"photographers/{gallery.photographer.username}/galleries/{gallery.slug}"
    asset = MediaAsset(
        gallery=gallery,
        media_type=media_type,
        original_name=f"photo{index}.jpg",
        file_size=2048,
        order=index,
        processing_status=MediaAsset.ProcessingStatus.READY,
    )
    asset.original_file.save(
        f"photo{index}.jpg",
        ContentFile(b"\xff\xd8\xff\xe0-not-a-real-jpeg-but-real-bytes"),
        save=False,
    )
    if media_type == MediaAsset.MediaType.IMAGE:
        # Placeholder bytes cannot be decoded, so a processed upload's master stands in (6-D: the
        # original only replaces a missing master when it is a readable image within 3600 px).
        asset.download_file.save(
            f"photo{index}.master.jpg", ContentFile(b"\xff\xd8\xff\xe0-placeholder-master"), save=False,
        )
    asset.save()
    asset.display_file = f"{base}/display/photo{index}_display.webp"
    asset.medium_file = f"{base}/medium/photo{index}_medium.webp"
    asset.thumbnail_file = f"{base}/thumb/photo{index}_thumb.webp"
    asset.save(update_fields=["display_file", "medium_file", "thumbnail_file"])
    return asset


class OriginalDeliveryProtectionTestCase(APITestCase):
    """
    A password-protected gallery's original files (downloads, video
    streaming) must never be reachable without a valid unlocked session,
    and the public gallery payload must never surface a raw original URL.
    """

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="delivery@kyapture.com",
            password="SecurePassword123!",
            username="deliveryphotog",
            display_name="Delivery Studio",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Protected Gallery",
            slug="protected-gallery",
            is_published=True,
            is_active=True,
            allow_download=True,
            is_password_protected=True,
            # These tests are about the gallery-password gate, not the email rule.
            design_settings={"downloads": {"require_email": False}},
        )
        self.gallery.password_hash = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["password_hash"])

        self.asset = _make_ready_asset(self.gallery, 1)
        self.video_asset = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.VIDEO,
            original_name="clip.mp4",
            file_size=4096,
            order=2,
            original_file="photographers/deliveryphotog/galleries/protected-gallery/originals/clip.mp4",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        self.video_asset.poster_image = "photographers/deliveryphotog/galleries/protected-gallery/posters/clip_poster.jpg"
        self.video_asset.playback_file = "photographers/deliveryphotog/galleries/protected-gallery/playback/clip_playback.mp4"
        self.video_asset.save(update_fields=["poster_image", "playback_file"])

    def _unlock(self):
        response = self.client.post(
            f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/unlock/",
            {"password": "secret123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data["access_token"]

    def test_public_gallery_payload_never_exposes_a_raw_original_url(self):
        """
        Even with a valid unlocked session, the gallery/photos payloads
        should only ever carry derivative URLs (display/medium/thumbnail/
        poster/playback/download) — never a direct original_file path.
        """
        token = self._unlock()
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"
        response = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        payload_str = str(response.data)
        self.assertNotIn("original_file", payload_str)
        # download_url must be the gated app endpoint, never a bare storage URL
        for photo in response.data["photos"]:
            if photo.get("download_url"):
                self.assertIn("/download/", photo["download_url"])

    def test_photo_download_requires_unlocked_session(self):
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/photo/{self.asset.id}/download/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_photo_download_succeeds_with_valid_unlocked_session(self):
        token = self._unlock()
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/photo/{self.asset.id}/download/?token={token}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(self.asset.original_name, response["Content-Disposition"])

    def test_video_stream_requires_unlocked_session(self):
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/video/{self.video_asset.id}/stream/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_paginated_photos_endpoint_requires_unlocked_session(self):
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/photos/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_paginated_photos_endpoint_succeeds_with_valid_unlocked_session(self):
        token = self._unlock()
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/photos/?token={token}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("results", response.data)

    def test_invalid_token_still_rejected_on_all_gated_endpoints(self):
        bad = "not-a-real-session-token"
        photo_url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/photo/{self.asset.id}/download/?token={bad}"
        video_url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/video/{self.video_asset.id}/stream/?token={bad}"
        photos_url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/photos/?token={bad}"

        self.assertEqual(self.client.get(photo_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(video_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(photos_url).status_code, status.HTTP_401_UNAUTHORIZED)


class OpenGalleryDerivativeAccessTestCase(APITestCase):
    """A non-password-protected gallery's derivatives are reachable with no gate at all."""

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="open@kyapture.com",
            password="SecurePassword123!",
            username="openphotog",
            display_name="Open Studio",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Open Gallery",
            slug="open-gallery",
            is_published=True,
            is_active=True,
            allow_download=True,
            # An open, frictionless gallery: no email/PIN rule.
            design_settings={"downloads": {"require_email": False}},
        )
        self.asset = _make_ready_asset(self.gallery, 1)

    def test_derivative_urls_present_with_no_auth_required(self):
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        photo = response.data["photos"][0]
        self.assertTrue(photo["display_url"])
        self.assertTrue(photo["medium_url"])
        self.assertTrue(photo["thumbnail_url"])

    def test_photo_download_on_open_gallery_requires_no_token(self):
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/photo/{self.asset.id}/download/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class StorageClassBoundaryTestCase(TestCase):
    """
    Mirrors the video-pipeline storage-class check
    (test_video_pipeline.py's VideoUploadIntegrationTestCase) for images:
    the private original and the public derivatives must be attached to
    genuinely different storage backends at the model-field level, not
    just by file-path convention.
    """

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="storage@kyapture.com",
            password="SecurePassword123!",
            username="storagephotog",
            display_name="Storage Studio",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Storage Gallery",
            slug="storage-gallery",
        )
        self.asset = _make_ready_asset(self.gallery, 1)

    def test_original_uses_private_storage(self):
        self.assertIsInstance(self.asset.original_file.storage, PrivateMediaStorage)

    def test_derivatives_use_public_storage(self):
        self.assertIsInstance(self.asset.display_file.storage, PublicMediaStorage)
        self.assertIsInstance(self.asset.medium_file.storage, PublicMediaStorage)
        self.assertIsInstance(self.asset.thumbnail_file.storage, PublicMediaStorage)


class PublicGalleryPaginationTestCase(APITestCase):
    """
    GALLERY checklist: pagination, 100+ asset behavior, and the
    PublicGalleryPhotosView continuation endpoint.
    """

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="paginate@kyapture.com",
            password="SecurePassword123!",
            username="paginatephotog",
            display_name="Paginate Studio",
        )
        self.page_size = GalleryMediaPagination.page_size

    def _make_gallery_with_n_ready_assets(self, n, slug):
        gallery = Gallery.objects.create(
            photographer=self.photographer,
            title=f"Gallery {slug}",
            slug=slug,
            is_published=True,
            is_active=True,
        )
        for i in range(n):
            _make_ready_asset(gallery, i)
        return gallery

    def test_first_page_reports_has_more_false_when_under_page_size(self):
        gallery = self._make_gallery_with_n_ready_assets(5, "small-gallery")
        url = f"/api/v1/public/{self.photographer.username}/{gallery.slug}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["photos_count"], 5)
        self.assertFalse(response.data["photos_has_more"])
        self.assertEqual(len(response.data["photos"]), 5)
        self.assertEqual(response.data["photos_page_size"], self.page_size)

    def test_first_page_reports_has_more_true_when_over_page_size(self):
        """
        Simulates the 100+/500+/1000+/2000+ large-gallery requirement at a
        smaller, fast-to-build scale: creates 2x the page size and
        confirms the initial gallery payload embeds exactly ONE page,
        never the full asset list.
        """
        total = self.page_size * 2 + 7
        gallery = self._make_gallery_with_n_ready_assets(total, "large-gallery")

        url = f"/api/v1/public/{self.photographer.username}/{gallery.slug}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["photos_count"], total)
        self.assertTrue(response.data["photos_has_more"])
        self.assertEqual(len(response.data["photos"]), self.page_size)

    def test_photos_endpoint_serves_the_next_page_after_the_embedded_first_page(self):
        total = self.page_size + 10
        gallery = self._make_gallery_with_n_ready_assets(total, "next-page-gallery")

        first_page_url = f"/api/v1/public/{self.photographer.username}/{gallery.slug}/"
        first_response = self.client.get(first_page_url)
        first_page_ids = {p["id"] for p in first_response.data["photos"]}

        photos_url = f"/api/v1/public/{self.photographer.username}/{gallery.slug}/photos/?page=2"
        second_response = self.client.get(photos_url)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK, second_response.data)
        self.assertEqual(second_response.data["count"], total)
        self.assertIsNone(second_response.data["next"])
        self.assertIsNotNone(second_response.data["previous"])

        second_page_ids = {p["id"] for p in second_response.data["results"]}
        # The two pages must not overlap, and together must add up to the total.
        self.assertEqual(len(first_page_ids & second_page_ids), 0)
        self.assertEqual(len(first_page_ids) + len(second_page_ids), total)

    def test_photos_endpoint_excludes_non_ready_assets(self):
        gallery = self._make_gallery_with_n_ready_assets(3, "mixed-status-gallery")
        MediaAsset.objects.create(
            gallery=gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="pending.jpg",
            file_size=1024,
            original_file="photographers/paginatephotog/galleries/mixed-status-gallery/originals/pending.jpg",
            processing_status=MediaAsset.ProcessingStatus.PENDING,
        )
        url = f"/api/v1/public/{self.photographer.username}/{gallery.slug}/photos/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)

    def test_photos_endpoint_404s_for_nonexistent_gallery(self):
        url = f"/api/v1/public/{self.photographer.username}/does-not-exist/photos/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
