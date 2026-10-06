# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/tests/test_download_master_6b.py
"""
Chunk 6-B: production-safe Download Master encoder (jpegli q90, Pillow fallback).

Covers the 3600 px rule, no upscale, EXIF orientation, sRGB, lossless PNG, the
fallback when cjpegli is missing / fails / times out / writes garbage, temp-file
cleanup, the size guard, and byte-identical originals (hash before/after).
"""
import hashlib
import io
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from unittest import mock, skipUnless

import piexif
from PIL import Image as PILImage, ImageCms
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core import utils as core_utils
from apps.core.utils import (
    DOWNLOAD_MAX_EDGE,
    _make_download_master,
    process_download_master,
    process_image_pipeline,
)
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset

User = get_user_model()

CJPEGLI_AVAILABLE = os.path.exists(core_utils.CJPEGLI_BIN)
needs_cjpegli = skipUnless(CJPEGLI_AVAILABLE, "cjpegli is not installed on this host")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _photo_like(size, seed_noise=24):
    """Smooth gradient + noise: compresses like a photo, unlike pure noise."""
    w, h = size
    gradient = PILImage.linear_gradient("L").resize(size)
    noise = PILImage.effect_noise(size, seed_noise)
    channel = PILImage.blend(gradient, noise, 0.35)
    return PILImage.merge("RGB", (channel, channel.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT), noise))


def _jpeg_bytes(image, quality=95, **kwargs):
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality, **kwargs)
    return buf.getvalue()


def _master(raw, name="m.jpg"):
    """Run the production entry point exactly as the Celery task does."""
    f = SimpleUploadedFile(name, raw, content_type="image/jpeg")
    return process_image_pipeline(f)[3]


def _open(upload):
    upload.seek(0)
    return PILImage.open(io.BytesIO(upload.read()))


def _adobe_rgb_like_profile():
    """A minimal ICC v2 matrix/TRC RGB profile with Adobe RGB (1998) primaries."""
    def s15(v):
        return struct.pack(">i", int(round(v * 65536)))

    def xyz(x, y, z):
        return b"XYZ \x00\x00\x00\x00" + s15(x) + s15(y) + s15(z)

    def text(s):
        return b"text\x00\x00\x00\x00" + s + b"\x00"

    def desc(s):
        return (b"desc\x00\x00\x00\x00" + struct.pack(">I", len(s) + 1) + s + b"\x00"
                + b"\x00" * 8 + b"\x00\x00" + b"\x00" + b"\x00" * 67)

    gamma = b"curv\x00\x00\x00\x00" + struct.pack(">I", 1) + struct.pack(">H", int(2.19921875 * 256))
    tags = [
        (b"desc", desc(b"Test AdobeRGB-like")),
        (b"cprt", text(b"none")),
        (b"wtpt", xyz(0.9642, 1.0, 0.8249)),
        (b"rXYZ", xyz(0.60974, 0.31111, 0.01947)),
        (b"gXYZ", xyz(0.20528, 0.62567, 0.06087)),
        (b"bXYZ", xyz(0.14919, 0.06322, 0.74457)),
        (b"rTRC", gamma), (b"gTRC", gamma), (b"bTRC", gamma),
    ]
    offset = 128 + 4 + 12 * len(tags)
    table, body = b"", b""
    for sig, data in tags:
        data += b"\x00" * (-len(data) % 4)
        table += sig + struct.pack(">II", offset + len(body), len(data))
        body += data
    total = offset + len(body)
    header = (struct.pack(">I", total) + b"\x00\x00\x00\x00" + struct.pack(">I", 0x02200000)
              + b"mntrRGB XYZ " + b"\x00" * 12 + b"acsp" + b"\x00" * 24
              + struct.pack(">I", 0) + s15(0.9642) + s15(1.0) + s15(0.8249) + b"\x00" * 48)
    header = header[:128].ljust(128, b"\x00")
    return header + struct.pack(">I", len(tags)) + table + body


class ThreeThousandSixHundredRuleTests(SimpleTestCase):
    def test_landscape_source_is_capped_at_3600_long_edge(self):
        master = _master(_jpeg_bytes(_photo_like((5000, 3333)), 92))
        self.assertIsNotNone(master)
        self.assertEqual(max(_open(master).size), DOWNLOAD_MAX_EDGE)
        self.assertEqual(_open(master).size, (3600, 2400))

    def test_portrait_source_is_capped_at_3600_long_edge(self):
        master = _master(_jpeg_bytes(_photo_like((2500, 4800)), 92))
        self.assertEqual(_open(master).size, (1875, 3600))

    def test_sources_at_or_below_3600_are_never_upscaled(self):
        for size in ((3600, 2400), (3000, 2000), (800, 600)):
            with self.subTest(size=size):
                master = _master(_jpeg_bytes(_photo_like(size), 96))
                self.assertIsNotNone(master)
                self.assertEqual(_open(master).size, size)


class OrientationAndColourTests(SimpleTestCase):
    def test_exif_orientation_is_applied_and_tag_is_not_carried(self):
        # 1200x800 landscape, red marker top-left, EXIF orientation 6 (rotate 90 CW):
        # displayed image is 800x1200 and the marker lands top-RIGHT.
        img = PILImage.new("RGB", (1200, 800), (30, 30, 30))
        img.paste((255, 0, 0), (0, 0, 200, 200))
        exif = piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None})
        master = _master(_jpeg_bytes(img, 98, exif=exif))
        out = _open(master)
        self.assertEqual(out.size, (800, 1200))
        r, g, b = out.getpixel((750, 50))
        self.assertGreater(r, 200)
        self.assertLess(g, 60)
        self.assertNotIn("exif", out.info)

    def test_wide_gamut_source_is_converted_to_srgb_and_profile_dropped(self):
        profile = _adobe_rgb_like_profile()
        src = PILImage.new("RGB", (400, 300), (200, 100, 50))
        raw = _jpeg_bytes(src, 98, icc_profile=profile)
        # What the sRGB pixel must be: the same ICC conversion the pipeline uses.
        expected = ImageCms.profileToProfile(
            PILImage.open(io.BytesIO(raw)),
            ImageCms.ImageCmsProfile(io.BytesIO(profile)),
            ImageCms.createProfile("sRGB"),
            outputMode="RGB",
        ).getpixel((200, 150))
        master = _master(raw)
        out = _open(master)
        got = out.getpixel((200, 150))
        self.assertNotIn("icc_profile", out.info, "pixels are sRGB, no foreign profile may be carried")
        self.assertTrue(all(abs(a - b) <= 4 for a, b in zip(got, expected)), (got, expected))
        # And the conversion really changed the pixel (this was not an sRGB no-op).
        self.assertTrue(any(abs(a - b) >= 8 for a, b in zip(got, (200, 100, 50))), got)


class PngStaysLosslessTests(SimpleTestCase):
    def test_png_master_is_pixel_exact_and_never_touches_the_jpeg_encoder(self):
        img = _photo_like((900, 600))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        with mock.patch.object(core_utils, "_encode_jpegli") as jpegli, \
                mock.patch.object(core_utils, "_encode_jpeg_pillow") as pillow:
            master = process_image_pipeline(
                SimpleUploadedFile("p.png", buf.getvalue(), content_type="image/png")
            )[3]
        jpegli.assert_not_called()
        pillow.assert_not_called()
        out = _open(master)
        self.assertEqual(out.format, "PNG")
        self.assertEqual(list(out.convert("RGB").getdata()), list(img.getdata()))

    def test_png_above_3600_keeps_the_capped_master_even_if_larger_than_source(self):
        # Mirror of the JPEG rule (debt row 50): never hand a Free client the >3600 px original.
        img = PILImage.new("RGB", (4000, 1000), (10, 20, 30))
        result = _make_download_master(img, "PNG", "wide", original_size=1)
        self.assertIsNotNone(result)
        self.assertEqual(_open(result).size, (3600, 900))

    def test_small_png_larger_than_source_gets_no_master(self):
        img = PILImage.new("RGB", (200, 100), (10, 20, 30))
        self.assertIsNone(_make_download_master(img, "PNG", "tiny", original_size=1))


@needs_cjpegli
class JpegliPathTests(SimpleTestCase):
    def test_jpegli_is_used_and_pillow_fallback_is_not(self):
        raw = _jpeg_bytes(_photo_like((3000, 2000)), 96)
        with mock.patch.object(core_utils, "_encode_jpeg_pillow", wraps=core_utils._encode_jpeg_pillow) as pillow:
            master = _master(raw)
        pillow.assert_not_called()
        out = _open(master)
        self.assertEqual(out.format, "JPEG")
        self.assertEqual(out.size, (3000, 2000))
        self.assertLessEqual(master.size, len(raw))

    def test_jpegli_output_is_deterministic(self):
        raw = _jpeg_bytes(_photo_like((2000, 1500)), 96)
        self.assertEqual(_master(raw).read(), _master(raw).read())

    def test_subprocess_is_called_with_fixed_argv_no_shell_and_a_timeout(self):
        raw = _jpeg_bytes(_photo_like((800, 600)), 96)
        with mock.patch.object(core_utils.subprocess, "run", wraps=subprocess.run) as run:
            _master(raw)
        args, kwargs = run.call_args
        argv = args[0]
        self.assertIsInstance(argv, list)
        self.assertEqual(argv[0], core_utils.CJPEGLI_BIN)
        self.assertIn("--chroma_subsampling=420", argv)
        self.assertIn("--progressive_level=2", argv)
        self.assertEqual(argv[argv.index("-q") + 1], "90")
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["timeout"], core_utils.CJPEGLI_TIMEOUT_SECONDS)


class FallbackTests(SimpleTestCase):
    """Whatever goes wrong with cjpegli, a valid, bounded master still comes out."""

    def setUp(self):
        self.raw = _jpeg_bytes(_photo_like((4200, 2800)), 95)

    def _assert_pillow_fallback_master(self, master):
        self.assertIsNotNone(master)
        out = _open(master)
        self.assertEqual(out.format, "JPEG")
        self.assertEqual(out.size, (3600, 2400))

    def test_missing_binary_falls_back_to_pillow(self):
        with mock.patch.object(core_utils, "CJPEGLI_BIN", "/nonexistent/cjpegli"):
            self._assert_pillow_fallback_master(_master(self.raw))

    def test_nonzero_exit_falls_back_to_pillow(self):
        failed = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"secret internal path /x/y")
        with mock.patch.object(core_utils.subprocess, "run", return_value=failed):
            self._assert_pillow_fallback_master(_master(self.raw))

    def test_timeout_falls_back_to_pillow(self):
        with mock.patch.object(core_utils.subprocess, "run", side_effect=subprocess.TimeoutExpired("cjpegli", 60)):
            self._assert_pillow_fallback_master(_master(self.raw))

    def test_garbage_output_falls_back_to_pillow(self):
        def write_garbage(argv, **kwargs):
            with open(argv[2], "wb") as handle:
                handle.write(b"not a jpeg")
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

        with mock.patch.object(core_utils.subprocess, "run", side_effect=write_garbage):
            self._assert_pillow_fallback_master(_master(self.raw))

    def test_wrong_dimensions_from_encoder_fall_back_to_pillow(self):
        def write_small(argv, **kwargs):
            PILImage.new("RGB", (10, 10)).save(argv[2], format="JPEG")
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

        with mock.patch.object(core_utils.subprocess, "run", side_effect=write_small):
            self._assert_pillow_fallback_master(_master(self.raw))

    @skipUnless(sys.platform != "win32", "needs a POSIX shell script")
    def test_a_really_hung_encoder_is_killed_and_the_master_still_arrives(self):
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, True)
        hang = os.path.join(scratch, "hang.sh")
        with open(hang, "w") as handle:
            handle.write("#!/bin/sh\nexec sleep 30\n")
        os.chmod(hang, os.stat(hang).st_mode | stat.S_IXUSR)
        with mock.patch.object(core_utils, "CJPEGLI_BIN", hang), \
                mock.patch.object(core_utils, "CJPEGLI_TIMEOUT_SECONDS", 1):
            import time
            started = time.monotonic()
            master = _master(self.raw)
            elapsed = time.monotonic() - started
        self._assert_pillow_fallback_master(master)
        self.assertLess(elapsed, 15)

    def test_encoder_stderr_is_never_part_of_the_result(self):
        failed = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"secret internal path /x/y")
        with mock.patch.object(core_utils.subprocess, "run", return_value=failed):
            master = _master(self.raw)
        master.seek(0)
        self.assertNotIn(b"secret internal path", master.read())


class TempFileCleanupTests(SimpleTestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.scratch, True)
        patcher = mock.patch.object(tempfile, "tempdir", self.scratch)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.raw = _jpeg_bytes(_photo_like((1600, 1200)), 95)

    def _leftovers(self):
        return os.listdir(self.scratch)

    @needs_cjpegli
    def test_success_leaves_no_temp_files(self):
        self.assertIsNotNone(_master(self.raw))
        self.assertEqual(self._leftovers(), [])

    def test_missing_binary_leaves_no_temp_files(self):
        with mock.patch.object(core_utils, "CJPEGLI_BIN", "/nonexistent/cjpegli"):
            self.assertIsNotNone(_master(self.raw))
        self.assertEqual(self._leftovers(), [])

    def test_timeout_leaves_no_temp_files(self):
        with mock.patch.object(core_utils.subprocess, "run", side_effect=subprocess.TimeoutExpired("cjpegli", 60)):
            self.assertIsNotNone(_master(self.raw))
        self.assertEqual(self._leftovers(), [])

    def test_unexpected_exception_still_cleans_up(self):
        with mock.patch.object(core_utils.subprocess, "run", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                _master(self.raw)
        self.assertEqual(self._leftovers(), [])


class SizeGuardTests(SimpleTestCase):
    def test_small_source_is_not_forced_into_a_larger_reencode(self):
        # An already low-quality, optimised JPEG: q90 and q85 re-encodes are both larger
        # than the source -> no master, the original (same pixels) is served.
        raw = _jpeg_bytes(_photo_like((600, 400)), 50, optimize=True, progressive=True, subsampling=2)
        self.assertIsNone(_master(raw))

    def test_source_over_3600_keeps_a_capped_master_even_if_larger_than_the_source(self):
        img = _photo_like((4400, 1000))
        result = _make_download_master(img, "JPEG", "wide", original_size=1)
        self.assertIsNotNone(result)
        self.assertEqual(_open(result).size, (3600, 818))

    def test_master_is_never_larger_than_the_source_when_the_original_is_the_fallback(self):
        for size in ((1600, 1200), (3000, 2000), (3600, 2400)):
            with self.subTest(size=size):
                raw = _jpeg_bytes(_photo_like(size), 90)
                master = _master(raw)
                if master is not None:
                    self.assertLessEqual(master.size, len(raw))


class OriginalsAreByteIdenticalTests(APITestCase):
    def test_pipeline_and_backfill_entry_points_never_modify_the_original(self):
        for raw, name in (
            (_jpeg_bytes(_photo_like((4200, 2800)), 95), "a.jpg"),
            (_jpeg_bytes(_photo_like((600, 400)), 95), "b.jpg"),
        ):
            for entry in (process_image_pipeline, process_download_master):
                with self.subTest(name=name, entry=entry.__name__):
                    source = SimpleUploadedFile(name, raw, content_type="image/jpeg")
                    before = _sha256(raw)
                    entry(source)
                    source.seek(0)
                    self.assertEqual(_sha256(source.read()), before)

    def test_stored_original_is_byte_identical_after_a_real_upload(self):
        user = User.objects.create_user(email="m6b@kyapture.com", password="SecurePassword123!", username="m6buser")
        user.is_active_plan = True
        user.save(update_fields=["is_active_plan"])
        gallery = Gallery.objects.create(photographer=user, title="M6B", slug="m6b-gallery")
        self.client.force_authenticate(user=user)
        raw = _jpeg_bytes(_photo_like((4200, 2800)), 95)
        upload = SimpleUploadedFile("camera.jpg", raw, content_type="image/jpeg")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/api/v1/photos/{gallery.slug}/upload/", {"image": [upload]}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        asset = MediaAsset.objects.get(gallery=gallery)
        asset.refresh_from_db()
        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.READY)
        with asset.original_file.open("rb") as handle:
            stored = handle.read()
        self.assertEqual(_sha256(stored), _sha256(raw))
        self.assertTrue(asset.download_file)
        with asset.download_file.open("rb") as handle:
            self.assertEqual(max(PILImage.open(io.BytesIO(handle.read())).size), DOWNLOAD_MAX_EDGE)


class BackfillKeepsCappedMasterTests(APITestCase):
    def test_backfill_never_falls_back_to_a_full_size_original_above_3600px(self):
        from django.core.management import call_command

        user = User.objects.create_user(email="m6bbf@kyapture.com", password="SecurePassword123!", username="m6bbf")
        gallery = Gallery.objects.create(photographer=user, title="M6B BF", slug="m6b-bf")
        # Very low quality 4400 px source: the 3600 px q85 re-encode is larger than it.
        raw = _jpeg_bytes(_photo_like((4400, 1000)), 15, optimize=True, progressive=True, subsampling=2)
        probe = _make_download_master(PILImage.open(io.BytesIO(raw)), "JPEG", "probe", original_size=len(raw))
        self.assertGreater(probe.size, len(raw), "precondition: capped master is larger than the original")

        asset = MediaAsset.objects.create(
            gallery=gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_file=SimpleUploadedFile("wide.jpg", raw, content_type="image/jpeg"),
            original_name="wide.jpg",
            file_size=len(raw),
            title="wide",
            processing_status=MediaAsset.ProcessingStatus.READY,
            order=1,
        )
        old_master = _jpeg_bytes(PILImage.open(io.BytesIO(raw)), 95)  # a 4400 px master from the old encoder
        asset.download_file.save("old.jpg", SimpleUploadedFile("old.jpg", old_master, content_type="image/jpeg"), save=True)

        call_command("backfill_download_masters", verbosity=0)

        asset.refresh_from_db()
        self.assertTrue(asset.download_file, "a Free client must not be sent the >3600 px original")
        with asset.download_file.open("rb") as handle:
            self.assertEqual(max(PILImage.open(io.BytesIO(handle.read())).size), DOWNLOAD_MAX_EDGE)
        with asset.original_file.open("rb") as handle:
            self.assertEqual(_sha256(handle.read()), _sha256(raw))
