# backend/apps/photos/tests/test_upload_security.py
"""
Phase 4 regression tests — UPLOAD SECURITY.

Covers:
  - a decompression-bomb PNG (huge declared dimensions, tiny actual file)
    is rejected with a clean validation error, never a crash
  - an excessively long filename/title is truncated to fit the DB
    column instead of surfacing a raw database error
"""
import struct
import zlib

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from rest_framework import status

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset

User = get_user_model()


def _make_fake_png(width, height):
    """A syntactically valid PNG header declaring huge dimensions, with
    no real pixel data — Pillow reads width/height from IHDR before
    decoding any pixels, so this triggers the decompression-bomb check
    without needing to actually construct a multi-gigabyte file."""
    sig = b'\x89PNG\r\n\x1a\n'

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return sig + chunk(b'IHDR', ihdr) + chunk(b'IEND', b'')


class DecompressionBombTestCase(APITestCase):
    def setUp(self):
        self.photographer = User.objects.create_user(
            email="bombtest@kyapture.com", password="SecurePassword123!", username="bombtestphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer, title="Bomb Test", slug="bomb-test",
        )
        self.client.force_authenticate(user=self.photographer)
        self.url = f"/api/v1/photos/{self.gallery.slug}/upload/"

    def test_decompression_bomb_rejected_cleanly(self):
        bomb_bytes = _make_fake_png(50000, 50000)  # 2.5 billion declared pixels
        upload = SimpleUploadedFile("bomb.png", bomb_bytes, content_type="image/png")

        response = self.client.post(self.url, {"image": upload}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(MediaAsset.objects.filter(gallery=self.gallery).exists())

    def test_normal_sized_image_still_uploads(self):
        import io
        from PIL import Image as PILImage

        buf = io.BytesIO()
        PILImage.new("RGB", (100, 100), color="blue").save(buf, format="JPEG")
        upload = SimpleUploadedFile("normal.jpg", buf.getvalue(), content_type="image/jpeg")

        response = self.client.post(self.url, {"image": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)


class FilenameTruncationTestCase(APITestCase):
    def setUp(self):
        self.photographer = User.objects.create_user(
            email="longname@kyapture.com", password="SecurePassword123!", username="longnamephotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer, title="Long Name Test", slug="long-name-test",
        )
        self.client.force_authenticate(user=self.photographer)
        self.url = f"/api/v1/photos/{self.gallery.slug}/upload/"

    def test_excessively_long_filename_is_truncated_not_a_db_error(self):
        import io
        from PIL import Image as PILImage

        buf = io.BytesIO()
        PILImage.new("RGB", (50, 50), color="red").save(buf, format="JPEG")
        long_name = ("a" * 400) + ".jpg"
        upload = SimpleUploadedFile(long_name, buf.getvalue(), content_type="image/jpeg")

        response = self.client.post(self.url, {"image": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)

        asset = MediaAsset.objects.get(gallery=self.gallery)
        self.assertLessEqual(len(asset.original_name), 255)
        self.assertLessEqual(len(asset.title), 200)
