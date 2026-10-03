# backend/apps/clients/tests/test_download_pin_resolution.py
"""
Phase 3 regression tests — DOWNLOAD PIN + RESOLUTION + ACTIVITY LOGGING.

Covers:
  - the optional gallery download PIN: set/clear via the photographer
    endpoint, never stored as plaintext, required + verified on both the
    ZIP and single-file download endpoints, wrong/missing PIN rejected
  - Web Size vs High Resolution: which derivative actually gets served
  - DownloadLog entries are written only after a successful, authorized
    download, with the right type/resolution/pin_verified fields
  - the photographer-facing paginated download-logs endpoint, tenant-scoped
"""
import bcrypt
import io
import zipfile
from PIL import Image as PILImage
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.clients.models import DownloadLog

User = get_user_model()


def _make_ready_asset_with_display(gallery, name="photo.jpg"):
    """A READY image asset with both an original (real bytes) and a
    display derivative (bare path — nothing here opens its bytes for
    assertions beyond 'file was served', which reads whichever field the
    view selects)."""
    asset = MediaAsset(
        gallery=gallery,
        media_type=MediaAsset.MediaType.IMAGE,
        original_name=name,
        file_size=1024,
        processing_status=MediaAsset.ProcessingStatus.READY,
    )
    asset.original_file.save(name, ContentFile(b"ORIGINAL-BYTES-HERE"), save=False)
    asset.save()
    asset.display_file.save(
        f"{name}.display.webp", ContentFile(b"DISPLAY-DERIVATIVE-BYTES"), save=False
    )
    asset.download_file.save(
        f"{name}.download.jpg", ContentFile(b"DOWNLOAD-MASTER-BYTES"), save=False
    )
    asset.save(update_fields=["display_file", "download_file"])
    return asset


class DownloadPinSettingTestCase(APITestCase):
    """POST /api/v1/galleries/{slug}/set-download-pin/ (photographer-facing)."""

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="pinowner@kyapture.com",
            password="SecurePassword123!",
            username="pinowner",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer, title="Pinned", slug="pinned-gallery",
        )
        self.client.force_authenticate(user=self.photographer)
        self.url = f"/api/v1/galleries/{self.gallery.slug}/set-download-pin/"

    def test_set_pin_hashes_it_never_stores_plaintext(self):
        response = self.client.post(self.url, {"pin": "4321"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.gallery.refresh_from_db()
        self.assertIsNotNone(self.gallery.download_pin_hash)
        self.assertNotEqual(self.gallery.download_pin_hash, "4321")
        self.assertTrue(bcrypt.checkpw(b"4321", self.gallery.download_pin_hash.encode()))

    def test_rejects_non_numeric_pin(self):
        response = self.client.post(self.url, {"pin": "abcd"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_too_short_pin(self):
        response = self.client.post(self.url, {"pin": "12"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_clearing_pin_removes_protection(self):
        self.client.post(self.url, {"pin": "4321"}, format="json")
        response = self.client.post(self.url, {"pin": ""}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.gallery.refresh_from_db()
        self.assertIsNone(self.gallery.download_pin_hash)

    def test_cannot_set_pin_on_another_photographers_gallery(self):
        other = User.objects.create_user(
            email="otherpin@kyapture.com", password="SecurePassword123!", username="otherpinowner"
        )
        other_gallery = Gallery.objects.create(photographer=other, title="Theirs", slug="theirs-pin")
        url = f"/api/v1/galleries/{other_gallery.slug}/set-download-pin/"
        response = self.client.post(url, {"pin": "1234"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        other_gallery.refresh_from_db()
        self.assertIsNone(other_gallery.download_pin_hash)


class GalleryZipDownloadPinAndResolutionTestCase(APITestCase):
    """POST /api/v1/public/{username}/{slug}/download/"""

    def setUp(self):
        # This view shares the 'password_unlock' throttle scope (5/min) —
        # clear it per test so multiple test methods in this class don't
        # trip each other's rate limit via the shared process-wide cache.
        cache.clear()
        self.photographer = User.objects.create_user(
            email="zippin@kyapture.com", password="SecurePassword123!", username="zippinphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Zip Gallery",
            slug="zip-gallery",
            is_published=True,
            is_active=True,
            allow_download=True,
        )
        self.gallery.download_pin_hash = bcrypt.hashpw(b"9999", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["download_pin_hash"])
        self.asset = _make_ready_asset_with_display(self.gallery)
        self.url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/download/"

    def test_missing_pin_rejected(self):
        response = self.client.post(self.url, {"email": "guest@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data.get("code"), "pin_required")
        self.assertFalse(DownloadLog.objects.exists())

    def test_wrong_pin_rejected(self):
        response = self.client.post(
            self.url, {"email": "guest@example.com", "pin": "0000"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data.get("code"), "invalid_pin")
        self.assertFalse(DownloadLog.objects.exists())

    def test_pin_cannot_be_bypassed_by_omitting_it_as_empty_string(self):
        response = self.client.post(
            self.url, {"email": "guest@example.com", "pin": ""}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_correct_pin_succeeds_and_logs_pin_verified(self):
        response = self.client.post(
            self.url, {"email": "guest@example.com", "pin": "9999"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log = DownloadLog.objects.get()
        self.assertTrue(log.pin_verified)
        self.assertEqual(log.download_type, DownloadLog.DownloadType.GALLERY)
        self.assertEqual(log.email, "guest@example.com")

    def test_gallery_without_pin_does_not_require_one(self):
        self.gallery.download_pin_hash = None
        self.gallery.save(update_fields=["download_pin_hash"])
        response = self.client.post(self.url, {"email": "guest@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log = DownloadLog.objects.get()
        self.assertFalse(log.pin_verified)

    def test_default_resolution_is_download_master(self):
        response = self.client.post(
            self.url, {"email": "guest@example.com", "pin": "9999"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(archive.read("photo.jpg"), b"DOWNLOAD-MASTER-BYTES")
        log = DownloadLog.objects.get()
        self.assertEqual(log.resolution, DownloadLog.Resolution.DOWNLOAD)

    def test_web_resolution_recorded(self):
        response = self.client.post(
            self.url,
            {"email": "guest@example.com", "pin": "9999", "resolution": "web"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log = DownloadLog.objects.get()
        self.assertEqual(log.resolution, DownloadLog.Resolution.WEB)

    def test_invalid_resolution_rejected(self):
        response = self.client.post(
            self.url,
            {"email": "guest@example.com", "pin": "9999", "resolution": "ultra-hd"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SinglePhotoDownloadPinAndResolutionTestCase(APITestCase):
    """GET /api/v1/public/{username}/{slug}/photo/{photo_id}/download/"""

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="singlepin@kyapture.com", password="SecurePassword123!", username="singlepinphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Single Gallery",
            slug="single-gallery",
            is_published=True,
            is_active=True,
            allow_download=True,
        )
        self.gallery.download_pin_hash = bcrypt.hashpw(b"5555", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["download_pin_hash"])
        self.asset = _make_ready_asset_with_display(self.gallery)
        self.url = (
            f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}"
            f"/photo/{self.asset.id}/download/"
        )

    def test_missing_pin_rejected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(DownloadLog.objects.exists())

    def test_wrong_pin_rejected(self):
        response = self.client.get(self.url, {"pin": "1111"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_correct_pin_succeeds_no_email_required(self):
        response = self.client.get(self.url, {"pin": "5555"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log = DownloadLog.objects.get()
        self.assertIsNone(log.email)
        self.assertTrue(log.pin_verified)
        self.assertEqual(log.download_type, DownloadLog.DownloadType.PHOTO)
        self.assertEqual(log.media_asset_id, self.asset.id)

    def test_web_resolution_serves_display_derivative(self):
        response = self.client.get(self.url, {"pin": "5555", "resolution": "web"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Phase 4: streamed via FileResponse (not loaded fully into
        # memory) — .content isn't available on a streaming response;
        # draining streaming_content is the test-only equivalent.
        self.assertEqual(b"".join(response.streaming_content), b"DISPLAY-DERIVATIVE-BYTES")
        log = DownloadLog.objects.get()
        self.assertEqual(log.resolution, DownloadLog.Resolution.WEB)

    def test_original_resolution_serves_original_bytes(self):
        response = self.client.get(self.url, {"pin": "5555", "resolution": "original"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(response.streaming_content), b"ORIGINAL-BYTES-HERE")

    def test_default_resolution_without_param_is_download_master(self):
        response = self.client.get(self.url, {"pin": "5555"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(response.streaming_content), b"DOWNLOAD-MASTER-BYTES")
        self.assertIn(self.asset.original_name, response["Content-Disposition"])

    def test_legacy_image_download_backfills_a_missing_master(self):
        source = io.BytesIO()
        PILImage.new("RGB", (80, 60), (30, 100, 180)).save(source, format="JPEG", quality=95)
        self.asset.original_file.save("photo.jpg", ContentFile(source.getvalue()), save=False)
        self.asset.download_file = None
        self.asset.save(update_fields=["original_file", "download_file"])

        response = self.client.get(self.url, {"pin": "5555"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        self.assertTrue(self.asset.download_file)


class DownloadLogsActivityEndpointTestCase(APITestCase):
    """GET /api/v1/galleries/{slug}/download-logs/ (photographer-facing)."""

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="logsowner@kyapture.com", password="SecurePassword123!", username="logsowner",
        )
        self.other = User.objects.create_user(
            email="otherlogs@kyapture.com", password="SecurePassword123!", username="otherlogsowner",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer, title="Mine", slug="mine-logs",
        )
        self.other_gallery = Gallery.objects.create(
            photographer=self.other, title="Theirs", slug="theirs-logs",
        )
        DownloadLog.objects.create(gallery=self.gallery, email="a@example.com")
        DownloadLog.objects.create(gallery=self.other_gallery, email="b@example.com")

    def test_photographer_sees_only_their_own_logs(self):
        self.client.force_authenticate(user=self.photographer)
        response = self.client.get(f"/api/v1/galleries/{self.gallery.slug}/download-logs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        emails = [row["email"] for row in response.data["results"]]
        self.assertEqual(emails, ["a@example.com"])

    def test_cannot_view_another_photographers_download_logs(self):
        self.client.force_authenticate(user=self.photographer)
        response = self.client.get(f"/api/v1/galleries/{self.other_gallery.slug}/download-logs/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_requires_authentication(self):
        response = self.client.get(f"/api/v1/galleries/{self.gallery.slug}/download-logs/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_response_is_paginated_not_unbounded(self):
        for i in range(5):
            DownloadLog.objects.create(gallery=self.gallery, email=f"extra{i}@example.com")
        self.client.force_authenticate(user=self.photographer)
        response = self.client.get(f"/api/v1/galleries/{self.gallery.slug}/download-logs/")
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 6)
