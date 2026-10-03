# backend/apps/clients/tests/test_download_hardening.py
"""
Phase 4 regression tests — DOWNLOAD HARDENING.

Covers:
  - a malformed UUID in asset_ids returns 400, never an unhandled 500
  - untrusted original_name is sanitized before reaching a ZIP entry /
    Content-Disposition header (path traversal / header injection)
  - duplicate filenames within one ZIP are de-duplicated, not silently
    collapsed into one entry
  - DownloadLog is never written for a request that never actually
    compiles a download (e.g. no matching assets)
  - the synchronous-ZIP size/count guard rejects an oversized request
    with a clear 400 instead of hanging a worker
"""
import zipfile
import io

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.clients.models import DownloadLog
from apps.clients.models import ClientSession
from apps.clients.tests.zip_flow import InlineDownloadJobsMixin, request_zip

User = get_user_model()


def _ready_image(gallery, original_name, file_size=1024, content=b"BYTES"):
    asset = MediaAsset(
        gallery=gallery,
        media_type=MediaAsset.MediaType.IMAGE,
        original_name=original_name,
        file_size=file_size,
        processing_status=MediaAsset.ProcessingStatus.READY,
    )
    asset.original_file.save(original_name.split('/')[-1] or "file", ContentFile(content), save=False)
    asset.save()
    return asset


class MalformedAssetIdsTestCase(InlineDownloadJobsMixin, APITestCase):
    def setUp(self):
        cache.clear()
        self.photographer = User.objects.create_user(
            email="malformed@kyapture.com", password="SecurePassword123!", username="malformedphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Malformed Test",
            slug="malformed-test",
            is_published=True,
            is_active=True,
            allow_download=True,
        )
        _ready_image(self.gallery, "photo.jpg")
        self.base = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"

    def test_malformed_uuid_in_asset_ids_returns_400_not_500(self):
        response = request_zip(self.client, self.base, {
            "email": "guest@example.com",
            "asset_ids": ["not-a-uuid", "also-bad"],
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DownloadLog.objects.exists())

    def test_asset_ids_not_a_list_returns_400(self):
        response = request_zip(self.client, self.base, {
            "email": "guest@example.com",
            "asset_ids": "not-a-list",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_valid_uuid_but_nonexistent_asset_returns_400_no_log(self):
        response = request_zip(self.client, self.base, {
            "email": "guest@example.com",
            "asset_ids": ["01a0f000-0000-7000-8000-000000000000"],
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DownloadLog.objects.exists())

    def test_well_formed_asset_ids_still_work(self):
        asset = MediaAsset.objects.filter(gallery=self.gallery).first()
        response = request_zip(self.client, self.base, {
            "email": "guest@example.com",
            "asset_ids": [str(asset.id)],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(DownloadLog.objects.exists())


class FilenameSanitizationTestCase(InlineDownloadJobsMixin, APITestCase):
    def setUp(self):
        cache.clear()
        self.photographer = User.objects.create_user(
            email="filenames@kyapture.com", password="SecurePassword123!", username="filenamesphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Filename Test",
            slug="filename-test",
            is_published=True,
            is_active=True,
            allow_download=True,
        )
        self.base = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"

    def test_path_traversal_filename_cannot_escape_zip_entry(self):
        _ready_image(self.gallery, "../../../etc/passwd.jpg", content=b"EVIL")
        response = request_zip(self.client, self.base, {"email": "guest@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        zip_bytes = b"".join(response.streaming_content)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                self.assertNotIn("..", name)
                self.assertFalse(name.startswith("/"))

    def test_crlf_in_filename_does_not_break_response_headers(self):
        _ready_image(self.gallery, "evil\r\nX-Injected: true.jpg", content=b"EVIL")
        response = request_zip(self.client, self.base, {"email": "guest@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("\r", response["Content-Disposition"])
        self.assertNotIn("\n", response["Content-Disposition"])

    def test_duplicate_filenames_are_deduplicated_in_zip(self):
        _ready_image(self.gallery, "photo.jpg", content=b"FIRST")
        _ready_image(self.gallery, "photo.jpg", content=b"SECOND")

        response = request_zip(self.client, self.base, {"email": "guest@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        zip_bytes = b"".join(response.streaming_content)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            # Two distinct entries, not one overwriting the other.
            self.assertEqual(len(names), 2)
            self.assertEqual(len(set(names)), 2)
            contents = {zf.read(n) for n in names}
            self.assertEqual(contents, {b"FIRST", b"SECOND"})


class SyncZipSizeGuardTestCase(InlineDownloadJobsMixin, APITestCase):
    def setUp(self):
        cache.clear()
        self.photographer = User.objects.create_user(
            email="ziplimit@kyapture.com", password="SecurePassword123!", username="ziplimitphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Zip Limit Test",
            slug="zip-limit-test",
            is_published=True,
            is_active=True,
            allow_download=True,
        )
        self.base = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"

    @override_settings(SYNC_ZIP_MAX_ASSET_COUNT=2)
    def test_too_many_assets_rejected_with_clear_error(self):
        for i in range(3):
            _ready_image(self.gallery, f"photo{i}.jpg")

        response = request_zip(self.client, self.base, {"email": "guest@example.com"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get("code"), "download_too_large")
        self.assertFalse(DownloadLog.objects.exists())

    @override_settings(SYNC_ZIP_MAX_TOTAL_BYTES=1000)
    def test_too_many_total_bytes_rejected(self):
        _ready_image(self.gallery, "big.jpg", file_size=2000)
        response = request_zip(self.client, self.base, {"email": "guest@example.com"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get("code"), "download_too_large")

    def test_within_limits_still_succeeds(self):
        _ready_image(self.gallery, "small.jpg", file_size=100)
        response = request_zip(self.client, self.base, {"email": "guest@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PreparedGalleryDownloadTestCase(InlineDownloadJobsMixin, APITestCase):
    """The prepared gallery ZIP: POST .../download/ -> poll -> file."""

    def setUp(self):
        cache.clear()
        self.photographer = User.objects.create_user(
            email="directzip@kyapture.com", password="SecurePassword123!", username="directzipphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Direct ZIP",
            slug="direct-zip",
            is_published=True,
            is_active=True,
            allow_download=True,
        )
        self.base = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"
        self.guest = {"email": "guest@example.com"}

    def test_packages_only_ready_media_and_writes_audit_log(self):
        _ready_image(self.gallery, "first.jpg", content=b"READY")
        pending = _ready_image(self.gallery, "pending.jpg", content=b"PENDING")
        pending.processing_status = MediaAsset.ProcessingStatus.PENDING
        pending.save(update_fields=["processing_status"])

        response = request_zip(self.client, self.base, self.guest)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="direct-zip-photo-download-1of1.zip"'
        )
        with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(archive.namelist(), ["first.jpg"])
            self.assertEqual(archive.read("first.jpg"), b"READY")

        log = DownloadLog.objects.get()
        self.assertEqual(log.download_type, DownloadLog.DownloadType.GALLERY)
        self.assertEqual(log.resolution, DownloadLog.Resolution.DOWNLOAD)
        self.assertEqual(log.email, "guest@example.com")
        self.assertEqual(log.filename, "direct-zip-photo-download-1of1.zip")

    def test_requires_a_valid_unlock_token_for_protected_gallery(self):
        _ready_image(self.gallery, "first.jpg")
        self.gallery.is_password_protected = True
        self.gallery.save(update_fields=["is_password_protected"])
        session = ClientSession.objects.create(gallery=self.gallery)

        self.assertEqual(request_zip(self.client, self.base, self.guest).status_code, status.HTTP_401_UNAUTHORIZED)
        cache.clear()
        self.assertEqual(
            request_zip(self.client, self.base, self.guest, unlock_token=session.access_token).status_code,
            status.HTTP_200_OK,
        )

    def test_disabled_downloads_are_forbidden(self):
        _ready_image(self.gallery, "first.jpg")
        self.gallery.allow_download = False
        self.gallery.save(update_fields=["allow_download"])
        self.assertEqual(request_zip(self.client, self.base, self.guest).status_code, status.HTTP_403_FORBIDDEN)

    def test_unpublished_gallery_is_not_downloadable(self):
        _ready_image(self.gallery, "first.jpg")
        self.gallery.is_published = False
        self.gallery.save(update_fields=["is_published"])
        self.assertEqual(request_zip(self.client, self.base, self.guest).status_code, status.HTTP_404_NOT_FOUND)

    def test_zip_prefers_the_download_master(self):
        asset = _ready_image(self.gallery, "first.jpg", content=b"ORIGINAL")
        asset.download_file.save("first_download.jpg", ContentFile(b"DOWNLOAD-MASTER"), save=False)
        asset.save(update_fields=["download_file"])

        response = request_zip(self.client, self.base, self.guest)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(archive.read("first.jpg"), b"DOWNLOAD-MASTER")
