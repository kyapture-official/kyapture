# backend/apps/galleries/tests/test_trash_purge_and_quota.py
"""
Phase 4 regression tests — STORAGE/QUOTA INTEGRITY + TRASH/PURGE (F-30).

Covers:
  - free tier defaults to a 10-gallery cap (locked product decision #5)
  - soft-deleting a gallery sets trashed_at and still counts toward quota
    (the actual leak fix — deleting no longer frees quota until purged)
  - the scheduled purge task hard-deletes only galleries past their
    retention window, never an active or recently-trashed one
  - purging cascades to MediaAsset (and its files, via the existing
    post_delete signal) — no orphaned rows left behind
"""
from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from apps.galleries.models import Gallery
from apps.galleries.tasks import purge_trashed_galleries
from apps.photos.models import MediaAsset
from apps.core.utils import get_user_subscription_metrics

User = get_user_model()


class FreeTierGalleryCapTestCase(APITestCase):
    def setUp(self):
        self.photographer = User.objects.create_user(
            email="capuser@kyapture.com",
            password="SecurePassword123!",
            username="capuser",
        )
        self.client.force_authenticate(user=self.photographer)

    def test_default_free_tier_max_galleries_is_ten(self):
        metrics = get_user_subscription_metrics(self.photographer)
        self.assertEqual(metrics["max_galleries"], 10)

    def test_eleventh_gallery_is_blocked_on_free_tier(self):
        for i in range(10):
            Gallery.objects.create(
                photographer=self.photographer, title=f"Gallery {i}", slug=f"gallery-{i}",
            )
        response = self.client.post("/api/v1/galleries/", {"title": "Gallery 11"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("gallery_limit_reached", str(response.data))


class TrashQuotaAccountingTestCase(APITestCase):
    """The actual F-30 leak fix: trashed-but-unpurged data still counts."""

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="trashquota@kyapture.com",
            password="SecurePassword123!",
            username="trashquotauser",
        )
        self.client.force_authenticate(user=self.photographer)

    def test_deleting_a_gallery_is_permanent_not_a_trash_row(self):
        gallery = Gallery.objects.create(
            photographer=self.photographer, title="Doomed", slug="doomed",
        )
        response = self.client.delete(f"/api/v1/galleries/{gallery.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # The row is gone - no trashed_at/is_active=False leftover waiting for a sweep.
        self.assertFalse(Gallery.objects.filter(pk=gallery.pk).exists())

    def test_deleting_a_gallery_frees_its_quota_slot_because_it_is_really_gone(self):
        # The old soft-delete kept a trashed gallery counted so delete+reupload could not
        # outrun storage that was still occupied. Deletion is now permanent (rows and every
        # stored file), so the slot is genuinely free again.
        for i in range(10):
            Gallery.objects.create(
                photographer=self.photographer, title=f"Gallery {i}", slug=f"quota-gallery-{i}",
            )
        blocked = self.client.post("/api/v1/galleries/", {"title": "Over the limit"}, format="json")
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)

        self.client.delete("/api/v1/galleries/quota-gallery-0/")

        metrics = get_user_subscription_metrics(self.photographer)
        self.assertEqual(metrics["current_galleries_count"], 9)
        allowed = self.client.post("/api/v1/galleries/", {"title": "Fits now"}, format="json")
        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED, allowed.data)

    def test_deleting_a_gallery_frees_its_storage_quota(self):
        gallery = Gallery.objects.create(
            photographer=self.photographer, title="Heavy", slug="heavy-gallery",
        )
        MediaAsset.objects.create(
            gallery=gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="big.jpg",
            file_size=500 * 1024 * 1024,  # 500 MB
            original_file="photographers/x/galleries/x/originals/big.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        before = get_user_subscription_metrics(self.photographer)
        self.assertEqual(before["current_total_storage_bytes"], 500 * 1024 * 1024)

        self.client.delete(f"/api/v1/galleries/{gallery.slug}/")

        after = get_user_subscription_metrics(self.photographer)
        self.assertEqual(after["current_total_storage_bytes"], 0)


class PurgeTrashedGalleriesTestCase(APITestCase):
    def setUp(self):
        self.photographer = User.objects.create_user(
            email="purgeuser@kyapture.com",
            password="SecurePassword123!",
            username="purgeuser",
        )

    def _make_gallery(self, slug, is_active=True, trashed_at=None):
        gallery = Gallery.objects.create(
            photographer=self.photographer, title=slug, slug=slug, is_active=is_active,
        )
        if trashed_at is not None:
            Gallery.objects.filter(id=gallery.id).update(trashed_at=trashed_at)
            gallery.refresh_from_db()
        return gallery

    @override_settings(GALLERY_TRASH_RETENTION_DAYS=30)
    def test_purges_gallery_past_retention_window(self):
        old_trash = self._make_gallery(
            "old-trash", is_active=False, trashed_at=timezone.now() - timedelta(days=31)
        )
        purge_trashed_galleries()
        self.assertFalse(Gallery.objects.filter(id=old_trash.id).exists())

    @override_settings(GALLERY_TRASH_RETENTION_DAYS=30)
    def test_does_not_purge_recently_trashed_gallery(self):
        recent_trash = self._make_gallery(
            "recent-trash", is_active=False, trashed_at=timezone.now() - timedelta(days=5)
        )
        purge_trashed_galleries()
        self.assertTrue(Gallery.objects.filter(id=recent_trash.id).exists())

    @override_settings(GALLERY_TRASH_RETENTION_DAYS=30)
    def test_never_purges_an_active_gallery(self):
        active = self._make_gallery("still-active", is_active=True)
        purge_trashed_galleries()
        self.assertTrue(Gallery.objects.filter(id=active.id).exists())

    @override_settings(GALLERY_TRASH_RETENTION_DAYS=30)
    def test_trashed_with_no_timestamp_is_never_purged(self):
        """
        Safety net for pre-existing soft-deleted rows that somehow still
        have no trashed_at (should be backfilled by migration 0008, but
        this asserts the task's own defensive behavior regardless).
        """
        legacy_trash = self._make_gallery("legacy-trash", is_active=False, trashed_at=None)
        purge_trashed_galleries()
        self.assertTrue(Gallery.objects.filter(id=legacy_trash.id).exists())

    @override_settings(GALLERY_TRASH_RETENTION_DAYS=30)
    def test_purge_cascades_to_media_assets(self):
        gallery = self._make_gallery(
            "with-assets", is_active=False, trashed_at=timezone.now() - timedelta(days=31)
        )
        asset = MediaAsset.objects.create(
            gallery=gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="photo.jpg",
            file_size=1024,
            original_file="photographers/x/galleries/x/originals/photo.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        purge_trashed_galleries()
        self.assertFalse(Gallery.objects.filter(id=gallery.id).exists())
        self.assertFalse(MediaAsset.objects.filter(id=asset.id).exists())

    @override_settings(GALLERY_TRASH_RETENTION_DAYS=30)
    def test_purge_is_idempotent(self):
        self._make_gallery(
            "idempotent-trash", is_active=False, trashed_at=timezone.now() - timedelta(days=31)
        )
        first_count = purge_trashed_galleries()
        second_count = purge_trashed_galleries()
        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)
