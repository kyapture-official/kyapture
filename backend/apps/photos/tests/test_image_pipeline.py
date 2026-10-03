# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/tests/test_image_pipeline.py
"""
Phase 2 (media delivery): focused tests for the image pipeline.

Covers item G's IMAGE checklist: upload, processing, original
preservation, derivative generation, dimensions, content types,
retry/idempotency, cover assignment.
"""
import io
import math
from decimal import Decimal

import piexif
from PIL import Image as PILImage, ImageChops, ImageStat
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.utils import strip_exif_gps, process_image_pipeline
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.photos.tasks import _auto_assign_cover_if_missing, process_photo_asset

User = get_user_model()


def _build_jpeg_with_gps(size=(120, 90), color=(180, 60, 40)):
    """Real JPEG bytes carrying an EXIF GPS tag + a non-GPS EXIF tag."""
    img = PILImage.new("RGB", size, color=color)
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: ((40, 1), (0, 1), (0, 1)),
        piexif.GPSIFD.GPSLongitudeRef: "W",
        piexif.GPSIFD.GPSLongitude: ((74, 1), (0, 1), (0, 1)),
    }
    exif_dict = {
        "0th": {piexif.ImageIFD.Make: b"KyaptureCam"},
        "Exif": {piexif.ExifIFD.LensModel: b"50mm f/1.8"},
        "GPS": gps_ifd,
        "1st": {},
        "thumbnail": None,
    }
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=piexif.dump(exif_dict), quality=95)
    return buf.getvalue()


def _build_plain_jpeg(size=(2400, 1600), color=(20, 120, 200)):
    """A larger EXIF-free JPEG, to exercise real 640/1280/2048 downscaling."""
    img = PILImage.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _build_photographic_jpeg(size=(1800, 1200)):
    """A detail-rich JPEG that makes safe download-master compression measurable."""
    img = PILImage.effect_noise(size, 96).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=96)
    return buf.getvalue()


class StripExifGpsTestCase(APITestCase):
    """Unit-level: byte-preservation guarantee for the private original."""

    def test_gps_removed_but_pixels_and_other_exif_preserved(self):
        raw = _build_jpeg_with_gps()
        f = SimpleUploadedFile("in.jpg", raw, content_type="image/jpeg")

        cleaned = strip_exif_gps(f)
        cleaned.seek(0)
        cleaned_bytes = cleaned.read()

        # GPS is gone.
        exif_after = piexif.load(cleaned_bytes)
        self.assertFalse(exif_after.get("GPS"))

        # Non-GPS EXIF (camera make, lens) is untouched.
        self.assertEqual(exif_after["0th"].get(piexif.ImageIFD.Make), b"KyaptureCam")
        self.assertEqual(exif_after["Exif"].get(piexif.ExifIFD.LensModel), b"50mm f/1.8")

        # Pixel data is byte-for-byte identical — this is the "never
        # overwrite originals with a lossy derivative" guarantee: no
        # PIL decode/recompress happened, only the EXIF segment changed.
        before_pixels = list(PILImage.open(io.BytesIO(raw)).convert("RGB").getdata())
        after_pixels = list(PILImage.open(io.BytesIO(cleaned_bytes)).convert("RGB").getdata())
        self.assertEqual(before_pixels, after_pixels)

    def test_noop_when_no_gps_present(self):
        raw = _build_plain_jpeg(size=(40, 30))
        f = SimpleUploadedFile("in.jpg", raw, content_type="image/jpeg")

        result = strip_exif_gps(f)
        result.seek(0)
        # No GPS tag existed, so the function must return the ORIGINAL
        # file object untouched — not even a needless rewrite.
        self.assertIs(result, f)


class ProcessImagePipelineTestCase(APITestCase):
    """Unit-level: the 640/1280/2048 WebP derivative set + BlurHash."""

    def test_generates_640_1280_2048_webp_tiers_within_bounds(self):
        raw = _build_plain_jpeg(size=(3000, 2000))
        f = SimpleUploadedFile("big.jpg", raw, content_type="image/jpeg")

        display_file, medium_file, thumb_file, download_file, blurhash_str = process_image_pipeline(f)

        for derivative, max_edge, expected_ct in [
            (display_file, 2048, "image/webp"),
            (medium_file, 1280, "image/webp"),
            (thumb_file, 640, "image/webp"),
        ]:
            self.assertEqual(derivative.content_type, expected_ct)
            derivative.seek(0)
            img = PILImage.open(derivative)
            self.assertEqual(img.format, "WEBP")
            self.assertLessEqual(max(img.size), max_edge)
            # Aspect ratio preserved (3000x2000 = 3:2)
            self.assertAlmostEqual(img.size[0] / img.size[1], 3000 / 2000, places=1)

        # BlurHash is a real computed hash now, not the old permanent
        # fallback placeholder (the bug this phase fixed — missing
        # dependency + wrong kwargs + wrong input shape).
        self.assertIsInstance(blurhash_str, str)
        self.assertGreater(len(blurhash_str), 0)
        self.assertEqual(download_file.content_type, "image/jpeg")
        download_file.seek(0)
        self.assertEqual(PILImage.open(download_file).size, (3000, 2000))

    def test_jpeg_download_master_keeps_dimensions_and_reduces_size(self):
        raw = _build_photographic_jpeg()
        download_file = process_image_pipeline(
            SimpleUploadedFile("camera.jpg", raw, content_type="image/jpeg")
        )[3]

        download_file.seek(0)
        optimized_bytes = download_file.read()
        optimized = PILImage.open(io.BytesIO(optimized_bytes))
        self.assertEqual(optimized.format, "JPEG")
        self.assertEqual(optimized.size, (1800, 1200))
        self.assertLess(len(optimized_bytes), len(raw))

        original = PILImage.open(io.BytesIO(raw)).convert("RGB")
        difference = ImageChops.difference(original, optimized.convert("RGB"))
        channel_rms = ImageStat.Stat(difference).rms
        mean_square_error = sum(value ** 2 for value in channel_rms) / len(channel_rms)
        psnr = 20 * math.log10(255 / math.sqrt(mean_square_error))
        self.assertGreater(psnr, 30, "Download Master must retain strong visual fidelity")

    def test_png_download_master_is_lossless_and_retains_transparency(self):
        image = PILImage.new("RGBA", (120, 80), (10, 20, 30, 0))
        image.putpixel((20, 20), (250, 120, 40, 128))
        raw_stream = io.BytesIO()
        image.save(raw_stream, format="PNG")

        download_file = process_image_pipeline(
            SimpleUploadedFile("transparent.png", raw_stream.getvalue(), content_type="image/png")
        )[3]
        download_file.seek(0)
        optimized = PILImage.open(download_file)
        self.assertEqual(optimized.format, "PNG")
        self.assertEqual(optimized.mode, "RGBA")
        self.assertEqual(optimized.size, (120, 80))
        self.assertEqual(optimized.getpixel((20, 20)), (250, 120, 40, 128))

    def test_pipeline_is_deterministic_for_idempotent_retries(self):
        """
        A Celery retry re-runs process_image_pipeline on the same original
        bytes. For that retry to be safe to simply overwrite the previous
        attempt's derivative (PublicMediaStorage's file_overwrite=True),
        the pipeline itself must be a pure function of its input.
        """
        raw = _build_plain_jpeg(size=(800, 600))

        f1 = SimpleUploadedFile("a.jpg", raw, content_type="image/jpeg")
        d1, m1, t1, download1, h1 = process_image_pipeline(f1)
        d1.seek(0); m1.seek(0); t1.seek(0); download1.seek(0)

        f2 = SimpleUploadedFile("a.jpg", raw, content_type="image/jpeg")
        d2, m2, t2, download2, h2 = process_image_pipeline(f2)
        d2.seek(0); m2.seek(0); t2.seek(0); download2.seek(0)

        self.assertEqual(d1.read(), d2.read())
        self.assertEqual(m1.read(), m2.read())
        self.assertEqual(t1.read(), t2.read())
        self.assertEqual(download1.read(), download2.read())
        self.assertEqual(h1, h2)

    def test_small_image_is_never_upscaled(self):
        raw = _build_plain_jpeg(size=(100, 80))
        f = SimpleUploadedFile("small.jpg", raw, content_type="image/jpeg")
        display_file, medium_file, thumb_file, download_file, _ = process_image_pipeline(f)
        for derivative in (display_file, medium_file, thumb_file, download_file):
            derivative.seek(0)
            img = PILImage.open(derivative)
            # thumbnail() only ever shrinks — a 100x80 source must stay
            # 100x80 (or smaller due to WebP color-space rounding), never
            # grow to fill the 640/1280/2048 ceiling.
            self.assertLessEqual(img.size[0], 100)
            self.assertLessEqual(img.size[1], 80)


class ImageUploadIntegrationTestCase(APITestCase):
    """
    Integration-level: real upload → on_commit-dispatched Celery task
    (CELERY_TASK_ALWAYS_EAGER=True in development settings runs it
    synchronously) → READY asset with real derivatives, original
    preserved, and gallery cover auto-assignment.
    """

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="img_pipeline@kyapture.com",
            password="SecurePassword123!",
            username="imgpipeline",
        )
        self.photographer.is_active_plan = True
        self.photographer.save(update_fields=["is_active_plan"])

        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Image Pipeline Gallery",
            slug="image-pipeline-gallery",
        )
        self.client.force_authenticate(user=self.photographer)

    def _upload_one(self, name="entrance.jpg"):
        raw = _build_plain_jpeg(size=(1600, 1200))
        img = SimpleUploadedFile(name, raw, content_type="image/jpeg")
        upload_url = f"/api/v1/photos/{self.gallery.slug}/upload/"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(upload_url, {"image": [img]}, format="multipart")
        return response

    def test_upload_processes_to_ready_with_original_and_derivatives(self):
        response = self._upload_one()
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        asset = MediaAsset.objects.get(gallery=self.gallery)
        asset.refresh_from_db()

        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.READY)
        # Original preserved — never deleted/replaced by processing.
        self.assertTrue(asset.original_file)
        self.assertTrue(asset.original_file.name.endswith("_original.jpg"))
        # All three derivative tiers were generated.
        self.assertTrue(asset.display_file)
        self.assertTrue(asset.medium_file)
        self.assertTrue(asset.thumbnail_file)
        self.assertTrue(asset.download_file)
        self.assertTrue(asset.blurhash)
        self.assertEqual(asset.width, 1600)
        self.assertEqual(asset.height, 1200)

    def test_first_ready_upload_auto_assigns_gallery_cover(self):
        self.assertIsNone(self.gallery.cover_photo_id)
        self._upload_one()

        self.gallery.refresh_from_db()
        asset = MediaAsset.objects.get(gallery=self.gallery)
        self.assertEqual(self.gallery.cover_photo_id, asset.id)

    def test_ready_retry_backfills_a_missing_cover_without_reprocessing(self):
        """
        Regression for galleries that already contain a READY asset but have
        no cover (for example, a task replay after an interrupted historic
        processing run). The READY fast path must retain its no-reprocess
        behavior while still enforcing the gallery-cover invariant.
        """
        asset = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_file=SimpleUploadedFile(
                "already-ready.jpg", _build_plain_jpeg(size=(80, 60)), content_type="image/jpeg"
            ),
            original_name="already-ready.jpg",
            file_size=1,
            title="already ready",
            processing_status=MediaAsset.ProcessingStatus.READY,
            order=Decimal("1.0"),
        )

        process_photo_asset(str(asset.id))

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, asset.id)

    def test_ready_retry_never_replaces_a_manually_selected_cover(self):
        self._upload_one("manual-cover.jpg")
        manual_cover = MediaAsset.objects.get(gallery=self.gallery)
        self.gallery.cover_photo = manual_cover
        self.gallery.save(update_fields=["cover_photo"])

        retry_asset = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_file=SimpleUploadedFile(
                "later-ready.jpg", _build_plain_jpeg(size=(80, 60)), content_type="image/jpeg"
            ),
            original_name="later-ready.jpg",
            file_size=1,
            title="later ready",
            processing_status=MediaAsset.ProcessingStatus.READY,
            order=Decimal("2.0"),
        )

        process_photo_asset(str(retry_asset.id))

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, manual_cover.id)

    def test_first_ready_asset_wins_when_multiple_ready_assets_backfill(self):
        """The conditional update keeps the first READY winner stable."""
        first = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_file=SimpleUploadedFile(
                "first-ready.jpg", _build_plain_jpeg(size=(80, 60)), content_type="image/jpeg"
            ),
            original_name="first-ready.jpg",
            file_size=1,
            title="first ready",
            processing_status=MediaAsset.ProcessingStatus.READY,
            order=Decimal("1.0"),
        )
        second = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_file=SimpleUploadedFile(
                "second-ready.jpg", _build_plain_jpeg(size=(80, 60)), content_type="image/jpeg"
            ),
            original_name="second-ready.jpg",
            file_size=1,
            title="second ready",
            processing_status=MediaAsset.ProcessingStatus.READY,
            order=Decimal("2.0"),
        )

        _auto_assign_cover_if_missing(first)
        _auto_assign_cover_if_missing(second)

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, first.id)

    def test_retrying_a_ready_asset_is_a_no_op(self):
        """
        process_photo_asset guards on processing_status == READY and
        returns early — re-running it (e.g. a stray duplicate task
        message) must not regenerate or corrupt an already-ready asset.
        """
        self._upload_one()
        asset = MediaAsset.objects.get(gallery=self.gallery)
        display_name_before = asset.display_file.name

        process_photo_asset(str(asset.id))  # direct call, not .delay()

        asset.refresh_from_db()
        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.READY)
        self.assertEqual(asset.display_file.name, display_name_before)

    def test_ready_retry_backfills_only_a_missing_download_master(self):
        self._upload_one()
        asset = MediaAsset.objects.get(gallery=self.gallery)
        display_name_before = asset.display_file.name
        asset.download_file = None
        asset.save(update_fields=["download_file"])

        process_photo_asset(str(asset.id))

        asset.refresh_from_db()
        self.assertTrue(asset.download_file)
        self.assertEqual(asset.display_file.name, display_name_before)

    def test_failed_processing_marks_asset_failed_and_is_retryable(self):
        """
        A corrupt/non-decodable original must not crash the task silently
        — it should land in FAILED (exposed processing state) rather than
        stuck in PENDING forever, and calling the task again (the retry
        path) must be safe to invoke.
        """
        bogus = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_file=SimpleUploadedFile("bad.jpg", b"not a real jpeg", content_type="image/jpeg"),
            original_name="bad.jpg",
            file_size=15,
            title="bad",
            processing_status=MediaAsset.ProcessingStatus.PENDING,
            order=Decimal("1.0"),
        )

        with self.assertRaises(Exception):
            process_photo_asset(str(bogus.id))

        bogus.refresh_from_db()
        self.assertEqual(bogus.processing_status, MediaAsset.ProcessingStatus.FAILED)
        # Original is still there — a failed derivative pass never
        # touches or discards the source file.
        self.assertTrue(bogus.original_file)
