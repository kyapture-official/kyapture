# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/tests/test_video_pipeline.py
"""
Phase 2 (media delivery): focused tests for the video pipeline.

Covers item G's VIDEO checklist: upload, processing, poster, derivative,
original protection, retry. Uses real ffmpeg-generated synthetic clips
(lavfi test sources) — no mocking of the FFmpeg/FFprobe subprocess layer,
since that's exactly the layer this phase's bug fixes (short-video poster
seek, H.264/AAC MP4 derivative, chunked spooling) live in.
"""
import io
import os
import subprocess
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from PIL import Image as PILImage

from apps.core.storage import PrivateMediaStorage, PublicMediaStorage
from apps.core.utils import process_video_pipeline
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.photos.tasks import process_video_asset
from apps.subscriptions.models import SubscriptionPlan, UserSubscription

User = get_user_model()


def _make_video_bytes(width=640, height=360, duration=2, with_audio=True, extra_args=None):
    """
    Builds a real, small synthetic video with ffmpeg (a generated test
    pattern, not a mocked byte string) and returns its raw bytes.
    """
    fd, path = tempfile.mkstemp(suffix=(extra_args or {}).get("suffix", ".mp4"))
    os.close(fd)
    try:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=25:duration={duration}"]
        if with_audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}", "-shortest"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if with_audio:
            cmd += ["-c:a", "aac"]
        cmd += [path]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        with open(path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(path):
            os.remove(path)


def _video_upload_file(name="clip.mp4", **kwargs):
    data = _make_video_bytes(**kwargs)
    return SimpleUploadedFile(name, data, content_type="video/mp4")


class ProcessVideoPipelineTestCase(APITestCase):
    """Unit-level: FFmpeg/FFprobe subprocess pipeline correctness."""

    def test_generates_poster_and_h264_aac_mp4_playback_derivative(self):
        raw = _make_video_bytes(width=640, height=360, duration=3)
        f = SimpleUploadedFile("clip.mp4", raw, content_type="video/mp4")

        poster_file, playback_file, duration = process_video_pipeline(f)

        self.assertEqual(duration, 3)

        # Poster is a real, openable JPEG.
        self.assertEqual(poster_file.content_type, "image/jpeg")
        poster_file.seek(0)
        poster_img = PILImage.open(poster_file)
        self.assertEqual(poster_img.format, "JPEG")

        # Playback derivative is H.264/AAC MP4 with yuv420p (broad
        # decoder compatibility, notably Safari/iOS).
        self.assertEqual(playback_file.content_type, "video/mp4")
        fd, path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        try:
            playback_file.seek(0)
            with open(path, "wb") as out:
                out.write(playback_file.read())
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "stream=codec_name,codec_type,pix_fmt",
                 "-of", "default=noprint_wrappers=1", path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
            )
            self.assertIn("codec_name=h264", probe.stdout)
            self.assertIn("codec_name=aac", probe.stdout)
            self.assertIn("pix_fmt=yuv420p", probe.stdout)
        finally:
            os.remove(path)

    def test_short_video_under_two_seconds_still_generates_a_poster(self):
        """
        Regression test for the exact bug this phase fixes: the old
        pipeline hardcoded '-ss 00:00:02' for the poster frame, which
        produced ZERO frames (empty/failed ffmpeg output) for any video
        shorter than 2 seconds. A 1-second clip is exactly that case.
        """
        raw = _make_video_bytes(width=320, height=240, duration=1)
        f = SimpleUploadedFile("short.mp4", raw, content_type="video/mp4")

        poster_file, playback_file, duration = process_video_pipeline(f)

        self.assertEqual(duration, 1)
        poster_file.seek(0)
        poster_bytes = poster_file.read()
        self.assertGreater(len(poster_bytes), 0)
        img = PILImage.open(io.BytesIO(poster_bytes))
        self.assertEqual(img.format, "JPEG")

    def test_scale_down_only_never_upscales(self):
        """A source already under 1080p height must stay at its own
        resolution — the playback derivative must never grow it."""
        raw = _make_video_bytes(width=640, height=360, duration=1)
        f = SimpleUploadedFile("small.mp4", raw, content_type="video/mp4")
        _, playback_file, _ = process_video_pipeline(f)

        fd, path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        try:
            playback_file.seek(0)
            with open(path, "wb") as out:
                out.write(playback_file.read())
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height",
                 "-of", "default=noprint_wrappers=1", path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
            )
            self.assertIn("width=640", probe.stdout)
            self.assertIn("height=360", probe.stdout)
        finally:
            os.remove(path)

    def test_mov_container_input_produces_playable_mp4(self):
        raw = _make_video_bytes(width=480, height=270, duration=1, extra_args={"suffix": ".mov"})
        f = SimpleUploadedFile("clip.mov", raw, content_type="video/quicktime")
        poster_file, playback_file, duration = process_video_pipeline(f)
        self.assertEqual(duration, 1)
        playback_file.seek(0)
        self.assertGreater(len(playback_file.read()), 0)

    def test_video_without_audio_track_processes_successfully(self):
        """FFmpeg must not fail when asked for '-c:a aac' on a source
        that has no audio stream at all — a silent video upload."""
        raw = _make_video_bytes(width=320, height=240, duration=1, with_audio=False)
        f = SimpleUploadedFile("silent.mp4", raw, content_type="video/mp4")
        poster_file, playback_file, duration = process_video_pipeline(f)
        self.assertEqual(duration, 1)
        playback_file.seek(0)
        self.assertGreater(len(playback_file.read()), 0)


class VideoUploadIntegrationTestCase(APITestCase):
    """
    Integration-level: real upload → on_commit-dispatched Celery task
    (CELERY_TASK_ALWAYS_EAGER=True) → READY asset with poster + playback
    derivative, protected original, and retry-on-failure behavior.
    """

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="video_pipeline@kyapture.com",
            password="SecurePassword123!",
            username="videopipeline",
        )
        self.photographer.is_active_plan = True
        self.photographer.save(update_fields=["is_active_plan"])

        # Video uploads are gated on an active paid plan
        # (get_user_subscription_metrics -> allow_video=True only with
        # one) — free tier is images-only, so without this every video
        # upload in these tests would 403 before ever reaching the
        # pipeline under test.
        plan = SubscriptionPlan.objects.create(
            name="Video Pipeline Test Plan",
            price=29.99,
            max_galleries=5,
            max_photos_per_gallery=500,
            storage_gb=50,
            is_active=True,
        )
        UserSubscription.objects.create(
            user=self.photographer,
            plan=plan,
            status=UserSubscription.SubscriptionStatus.ACTIVE,
            starts_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(days=30),
            payment_method=UserSubscription.PaymentMethod.MANUAL,
        )

        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Video Pipeline Gallery",
            slug="video-pipeline-gallery",
        )
        self.client.force_authenticate(user=self.photographer)

    def _upload_one(self, name="wedding-toast.mp4", **kwargs):
        video = _video_upload_file(name=name, duration=2, **kwargs)
        upload_url = f"/api/v1/photos/{self.gallery.slug}/upload/"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(upload_url, {"video": [video]}, format="multipart")
        return response

    def test_upload_processes_to_ready_with_poster_and_playback(self):
        response = self._upload_one()
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        asset = MediaAsset.objects.get(gallery=self.gallery)
        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.READY)
        self.assertTrue(asset.original_file)
        self.assertTrue(asset.poster_image)
        self.assertTrue(asset.playback_file)
        self.assertEqual(asset.duration, 2)

    def test_original_uses_private_storage_derivative_uses_public_storage(self):
        """
        Storage-class boundary check (item C/K: 'original downloads
        remain protected', 'keep original available only to authorized
        downloads'): the original video and its playback derivative must
        be on different storage classes with different access contracts.
        """
        self._upload_one()
        asset = MediaAsset.objects.get(gallery=self.gallery)
        self.assertIsInstance(asset.original_file.storage, PrivateMediaStorage)
        self.assertIsInstance(asset.playback_file.storage, PublicMediaStorage)
        self.assertIsInstance(asset.poster_image.storage, PublicMediaStorage)

    def test_retrying_a_ready_video_asset_is_a_no_op(self):
        self._upload_one()
        asset = MediaAsset.objects.get(gallery=self.gallery)
        playback_name_before = asset.playback_file.name

        process_video_asset(str(asset.id))  # direct call, not .delay()

        asset.refresh_from_db()
        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.READY)
        self.assertEqual(asset.playback_file.name, playback_name_before)

    def test_ready_video_retry_backfills_a_missing_cover(self):
        """The READY fast path must also restore a missing video cover."""
        asset = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.VIDEO,
            original_file=SimpleUploadedFile("already-ready.mp4", b"video", content_type="video/mp4"),
            original_name="already-ready.mp4",
            file_size=5,
            title="already ready video",
            processing_status=MediaAsset.ProcessingStatus.READY,
            order=Decimal("1.0"),
        )

        process_video_asset(str(asset.id))

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, asset.id)

    def test_failed_video_processing_marks_asset_failed_and_preserves_original(self):
        bogus = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.VIDEO,
            original_file=SimpleUploadedFile("bad.mp4", b"not a real video", content_type="video/mp4"),
            original_name="bad.mp4",
            file_size=16,
            title="bad",
            processing_status=MediaAsset.ProcessingStatus.PENDING,
            order=Decimal("1.0"),
        )

        with self.assertRaises(Exception):
            process_video_asset(str(bogus.id))

        bogus.refresh_from_db()
        self.assertEqual(bogus.processing_status, MediaAsset.ProcessingStatus.FAILED)
        self.assertTrue(bogus.original_file)
        self.assertFalse(bogus.playback_file)
