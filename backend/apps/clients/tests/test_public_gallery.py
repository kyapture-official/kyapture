# backend/apps/clients/tests/test_public_gallery.py
"""
Phase 1 regression tests — PUBLIC GALLERY PAYLOAD & CLIENT ERROR HANDLING.

Covers F-11 (PublicGallerySerializer missing cover_url/event_date) and the
404/401 behavior ClientGalleryPage.jsx depends on (nonexistent/unpublished
gallery -> 404, password-protected gallery -> requires_password gate,
invalid unlock token -> 401). See docs/KYAPTURE_VERIFIED_EXECUTION_PLAN.md.
"""
import bcrypt
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset

User = get_user_model()


class PublicGalleryPayloadTestCase(APITestCase):
    def setUp(self):
        self.photographer = User.objects.create_user(
            email="pub@kyapture.com",
            password="SecurePassword123!",
            username="pubphotog",
            display_name="Pub Studio",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Public Gallery",
            slug="public-gallery",
            is_published=True,
            is_active=True,
            allow_download=True,
            event_date="2026-05-01",
        )
        self.ready_asset = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="ready.jpg",
            file_size=1024,
            original_file="photographers/pub/galleries/public-gallery/originals/ready.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        self.pending_asset = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="pending.jpg",
            file_size=1024,
            original_file="photographers/pub/galleries/public-gallery/originals/pending.jpg",
            processing_status=MediaAsset.ProcessingStatus.PENDING,
        )
        self.gallery.cover_photo = self.ready_asset
        self.gallery.save(update_fields=["cover_photo"])

    def test_public_gallery_payload_includes_cover_and_event_date(self):
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("cover_url", response.data)
        self.assertEqual(response.data["event_date"], "2026-05-01")
        self.assertTrue(response.data["allow_download"])

    def test_public_gallery_hides_non_ready_assets(self):
        """
        Only READY-processed assets should ever reach a guest — a pending
        or failed asset has no usable thumbnail/display file yet.
        """
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        returned_ids = {p["id"] for p in response.data["photos"]}
        self.assertIn(str(self.ready_asset.id), returned_ids)
        self.assertNotIn(str(self.pending_asset.id), returned_ids)

    def test_nonexistent_gallery_returns_404(self):
        url = f"/api/v1/public/{self.photographer.username}/does-not-exist/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unpublished_gallery_returns_404_same_as_nonexistent(self):
        """
        A draft (unpublished) gallery must be indistinguishable from a
        nonexistent one to an unauthenticated guest — this is what lets
        ClientGalleryPage.jsx treat both as the same "not found" state
        without leaking which case it is.
        """
        self.gallery.is_published = False
        self.gallery.save(update_fields=["is_published"])
        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_password_protected_gallery_requires_password(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["is_password_protected", "password_hash"])

        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["requires_password"])

    def test_invalid_unlock_token_returns_401(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["is_password_protected", "password_hash"])

        url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"
        response = self.client.get(url, HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wrong_unlock_password_returns_useful_error(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["is_password_protected", "password_hash"])

        unlock_url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/unlock/"
        response = self.client.post(unlock_url, {"password": "wrong-password"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("password", response.data)


class AutoCoverAssignTestCase(TestCase):
    """
    Phase 1, item 6: the gallery's cover is auto-assigned from the first
    READY photo/video when the gallery doesn't have one yet.
    """

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="cover@kyapture.com",
            password="SecurePassword123!",
            username="coverphotog",
            display_name="Cover Studio",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Cover Test Gallery",
            slug="cover-test-gallery",
        )

    def test_auto_assign_cover_when_missing(self):
        from apps.photos.tasks import _auto_assign_cover_if_missing

        asset = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="first.jpg",
            file_size=1024,
            original_file="photographers/cover/galleries/cover-test-gallery/originals/first.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        self.assertIsNone(self.gallery.cover_photo_id)

        _auto_assign_cover_if_missing(asset)

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, asset.id)

    def test_auto_assign_cover_does_not_override_existing_cover(self):
        from apps.photos.tasks import _auto_assign_cover_if_missing

        existing_cover = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="existing.jpg",
            file_size=1024,
            original_file="photographers/cover/galleries/cover-test-gallery/originals/existing.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        self.gallery.cover_photo = existing_cover
        self.gallery.save(update_fields=["cover_photo"])

        second_asset = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="second.jpg",
            file_size=1024,
            original_file="photographers/cover/galleries/cover-test-gallery/originals/second.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )

        _auto_assign_cover_if_missing(second_asset)

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, existing_cover.id)
