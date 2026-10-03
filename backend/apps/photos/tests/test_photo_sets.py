# backend/apps/photos/tests/test_photo_sets.py
"""
Phase 3 regression tests — PHOTO SETS.

Covers CRUD, reordering, photo assignment, per-set counts, and tenant
isolation for /api/v1/photos/{gallery_slug}/sets/... — see
docs/KYAPTURE_EXECUTION_STATE.md's Phase 3 section for the full feature.
"""
import importlib
import io
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from PIL import Image as PILImage

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet

User = get_user_model()


class PhotoSetTestCase(APITestCase):
    def setUp(self):
        self.photographer = User.objects.create_user(
            email="sets@kyapture.com",
            password="SecurePassword123!",
            username="setsphotog",
            display_name="Sets Studio",
        )
        self.other_photographer = User.objects.create_user(
            email="otherssets@kyapture.com",
            password="SecurePassword123!",
            username="othersetsphotog",
            display_name="Other Studio",
        )
        self.client.force_authenticate(user=self.photographer)

        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Wedding",
            slug="wedding",
        )
        self.other_gallery = Gallery.objects.create(
            photographer=self.other_photographer,
            title="Other Wedding",
            slug="other-wedding",
        )
        self.highlights = PhotoSet.objects.get(gallery=self.gallery, name="Highlights")

        self.base_url = f"/api/v1/photos/{self.gallery.slug}/sets/"

        self.asset1 = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="a.jpg",
            file_size=1024,
            original_file="photographers/x/galleries/x/originals/a.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        self.asset2 = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="b.jpg",
            file_size=1024,
            original_file="photographers/x/galleries/x/originals/b.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )

    @staticmethod
    def image_upload(name="set-upload.jpg"):
        buffer = io.BytesIO()
        PILImage.new("RGB", (20, 20), color="white").save(buffer, "JPEG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")

    # ── Create ────────────────────────────────────────────────────────────
    def test_create_set(self):
        response = self.client.post(
            self.base_url,
            {"name": "<b>Ceremony</b>", "description": "<em>Family ceremony</em>"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["name"], "Ceremony")
        self.assertEqual(response.data["description"], "Family ceremony")
        self.assertEqual(response.data["photo_count"], 0)
        self.assertEqual(set(response.data), {"id", "name", "description", "order", "photo_count"})
        self.assertTrue(PhotoSet.objects.filter(gallery=self.gallery, name="Ceremony").exists())

    def test_create_duplicate_name_rejected(self):
        self.client.post(self.base_url, {"name": "Ceremony"}, format="json")
        response = self.client.post(self.base_url, {"name": "Ceremony"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_empty_name_rejected(self):
        response = self.client.post(self.base_url, {"name": "   "}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_description_over_500_characters_rejected(self):
        response = self.client.post(
            self.base_url, {"name": "Ceremony", "description": "x" * 501}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("apps.photos.views.PhotoSet.objects.filter", side_effect=RuntimeError("sensitive test failure"))
    def test_unexpected_set_api_error_is_safe_json(self, _mock_filter):
        response = self.client.post(self.base_url, {"name": "Ceremony"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        self.assertEqual(response.json()["code"], "internal_server_error")
        self.assertNotIn("sensitive test failure", response.content.decode())

    def test_cannot_create_set_on_another_photographers_gallery(self):
        url = f"/api/v1/photos/{self.other_gallery.slug}/sets/"
        response = self.client.post(url, {"name": "Sneaky"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(PhotoSet.objects.filter(name="Sneaky").exists())

    # ── List + counts ─────────────────────────────────────────────────────
    def test_list_sets_includes_live_photo_count(self):
        photo_set = PhotoSet.objects.create(gallery=self.gallery, name="Reception", order=Decimal("1.0"))
        self.asset1.photo_set = photo_set
        self.asset1.save(update_fields=["photo_set"])

        response = self.client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        sets_by_name = {item["name"]: item for item in response.data}
        self.assertEqual(sets_by_name["Reception"]["photo_count"], 1)
        self.assertEqual(sets_by_name["Highlights"]["photo_count"], 0)

    def test_list_sets_scoped_to_gallery(self):
        PhotoSet.objects.create(gallery=self.gallery, name="Mine", order=Decimal("1.0"))
        PhotoSet.objects.create(gallery=self.other_gallery, name="TheirsOnly", order=Decimal("1.0"))

        response = self.client.get(self.base_url)
        names = [s["name"] for s in response.data]
        self.assertIn("Mine", names)
        self.assertNotIn("TheirsOnly", names)

    # ── Rename / delete ───────────────────────────────────────────────────
    def test_rename_set(self):
        photo_set = PhotoSet.objects.create(gallery=self.gallery, name="Old Name", order=Decimal("1.0"))
        url = f"{self.base_url}{photo_set.id}/"
        response = self.client.patch(
            url,
            {"name": "New Name", "description": "<script>bad()</script>Wedding dinner"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        photo_set.refresh_from_db()
        self.assertEqual(photo_set.name, "New Name")
        self.assertEqual(photo_set.description, "bad()Wedding dinner")

    def test_cannot_rename_another_photographers_set(self):
        foreign_set = PhotoSet.objects.create(gallery=self.other_gallery, name="Foreign", order=Decimal("1.0"))
        url = f"{self.base_url}{foreign_set.id}/"
        response = self.client.patch(url, {"name": "Hijacked"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        foreign_set.refresh_from_db()
        self.assertEqual(foreign_set.name, "Foreign")

    def test_delete_set_moves_member_photos_to_first_remaining_set(self):
        photo_set = PhotoSet.objects.create(gallery=self.gallery, name="Doomed", order=Decimal("1.0"))
        self.asset1.photo_set = photo_set
        self.asset1.save(update_fields=["photo_set"])

        url = f"{self.base_url}{photo_set.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(PhotoSet.objects.filter(id=photo_set.id).exists())
        self.asset1.refresh_from_db()
        self.assertEqual(self.asset1.photo_set_id, self.highlights.id)
        self.assertTrue(MediaAsset.objects.filter(id=self.asset1.id, gallery=self.gallery).exists())

    def test_cannot_delete_the_final_remaining_set(self):
        response = self.client.delete(f"{self.base_url}{self.highlights.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertTrue(PhotoSet.objects.filter(id=self.highlights.id).exists())

    def test_cannot_delete_another_photographers_set(self):
        foreign_set = PhotoSet.objects.create(gallery=self.other_gallery, name="Foreign", order=Decimal("1.0"))
        url = f"{self.base_url}{foreign_set.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(PhotoSet.objects.filter(id=foreign_set.id).exists())

    # ── Reorder ───────────────────────────────────────────────────────────
    def test_reorder_sets(self):
        set_a = PhotoSet.objects.create(gallery=self.gallery, name="A", order=Decimal("1.0"))
        set_b = PhotoSet.objects.create(gallery=self.gallery, name="B", order=Decimal("2.0"))
        set_c = PhotoSet.objects.create(gallery=self.gallery, name="C", order=Decimal("3.0"))

        url = f"{self.base_url}reorder/"
        response = self.client.patch(
            url, {"ordered_ids": [str(set_c.id), str(set_a.id), str(set_b.id)]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        set_a.refresh_from_db()
        set_b.refresh_from_db()
        set_c.refresh_from_db()
        self.assertTrue(set_c.order < set_a.order < set_b.order)

    def test_reorder_ignores_ids_from_another_gallery(self):
        foreign_set = PhotoSet.objects.create(gallery=self.other_gallery, name="Foreign", order=Decimal("1.0"))
        mine = PhotoSet.objects.create(gallery=self.gallery, name="Mine", order=Decimal("1.0"))

        url = f"{self.base_url}reorder/"
        response = self.client.patch(
            url, {"ordered_ids": [str(foreign_set.id), str(mine.id)]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        foreign_set.refresh_from_db()
        # Untouched — reorder only ever wrote the id(s) that actually
        # belong to this gallery.
        self.assertEqual(foreign_set.order, Decimal("1.0"))

    # ── Assign / unassign photos ──────────────────────────────────────────
    def test_assign_photos_to_set(self):
        photo_set = PhotoSet.objects.create(gallery=self.gallery, name="Getting Ready", order=Decimal("1.0"))
        url = f"/api/v1/photos/{self.gallery.slug}/move/"
        response = self.client.patch(
            url,
            {"set_id": str(photo_set.id), "photo_ids": [str(self.asset1.id), str(self.asset2.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["updated_count"], 2)

        self.asset1.refresh_from_db()
        self.asset2.refresh_from_db()
        self.assertEqual(self.asset1.photo_set_id, photo_set.id)
        self.assertEqual(self.asset2.photo_set_id, photo_set.id)

    def test_unassign_photos_with_null_set_id(self):
        photo_set = PhotoSet.objects.create(gallery=self.gallery, name="Ceremony", order=Decimal("1.0"))
        self.asset1.photo_set = photo_set
        self.asset1.save(update_fields=["photo_set"])

        url = f"/api/v1/photos/{self.gallery.slug}/move/"
        response = self.client.patch(
            url, {"set_id": None, "photo_ids": [str(self.asset1.id)]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.asset1.refresh_from_db()
        self.assertIsNone(self.asset1.photo_set_id)

    def test_cannot_assign_photos_using_a_set_from_another_gallery(self):
        foreign_set = PhotoSet.objects.create(gallery=self.other_gallery, name="Foreign", order=Decimal("1.0"))
        url = f"/api/v1/photos/{self.gallery.slug}/move/"
        response = self.client.patch(
            url, {"set_id": str(foreign_set.id), "photo_ids": [str(self.asset1.id)]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.asset1.refresh_from_db()
        self.assertIsNone(self.asset1.photo_set_id)

    def test_assign_silently_ignores_photo_ids_from_another_gallery(self):
        foreign_asset = MediaAsset.objects.create(
            gallery=self.other_gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="foreign.jpg",
            file_size=1024,
            original_file="photographers/y/galleries/y/originals/foreign.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        photo_set = PhotoSet.objects.create(gallery=self.gallery, name="Ceremony", order=Decimal("1.0"))
        url = f"/api/v1/photos/{self.gallery.slug}/move/"
        response = self.client.patch(
            url,
            {"set_id": str(photo_set.id), "photo_ids": [str(self.asset1.id), str(foreign_asset.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # Only the asset that actually belongs to this gallery got updated.
        self.assertEqual(response.data["updated_count"], 1)
        foreign_asset.refresh_from_db()
        self.assertIsNone(foreign_asset.photo_set_id)

    # ── Full-gallery ordering is unaffected ─────────────────────────────────
    def test_assigning_to_a_set_does_not_change_full_gallery_order(self):
        original_order = self.asset1.order
        photo_set = PhotoSet.objects.create(gallery=self.gallery, name="Ceremony", order=Decimal("1.0"))
        url = f"/api/v1/photos/{self.gallery.slug}/move/"
        self.client.patch(
            url, {"set_id": str(photo_set.id), "photo_ids": [str(self.asset1.id)]}, format="json"
        )
        self.asset1.refresh_from_db()
        self.assertEqual(self.asset1.order, original_order)

    def test_inactive_gallery_is_not_accessible(self):
        self.gallery.is_active = False
        self.gallery.save(update_fields=["is_active"])
        response = self.client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_gallery_creation_creates_highlights_set(self):
        gallery = Gallery.objects.create(
            photographer=self.photographer, title="New Gallery", slug="new-gallery"
        )
        self.assertEqual(list(gallery.sets.values_list("name", flat=True)), ["Highlights"])

    @patch("apps.photos.views.process_photo_asset.delay")
    def test_upload_assigns_selected_set(self, mock_process):
        photo_set = PhotoSet.objects.create(gallery=self.gallery, name="Ceremony", order=2)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/v1/photos/{self.gallery.slug}/upload/",
                {"image": self.image_upload(), "set_id": str(photo_set.id)},
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
        self.assertEqual(response.data[0]["photo_set"], photo_set.id)
        self.assertEqual(MediaAsset.objects.get(id=response.data[0]["id"]).photo_set_id, photo_set.id)

    @patch("apps.photos.views.process_photo_asset.delay")
    def test_upload_without_set_assigns_first_set(self, mock_process):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/v1/photos/{self.gallery.slug}/upload/",
                {"image": self.image_upload()},
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
        self.assertEqual(response.data[0]["photo_set"], self.highlights.id)

    def test_photo_list_filters_by_own_set_and_rejects_foreign_set(self):
        photo_set = PhotoSet.objects.create(gallery=self.gallery, name="Ceremony", order=2)
        self.asset1.photo_set = photo_set
        self.asset1.save(update_fields=["photo_set"])
        self.asset2.photo_set = self.highlights
        self.asset2.save(update_fields=["photo_set"])

        list_url = f"/api/v1/photos/{self.gallery.slug}/"
        response = self.client.get(list_url, {"set": str(photo_set.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([item["id"] for item in response.data], [str(self.asset1.id)])

        foreign_set = PhotoSet.objects.get(gallery=self.other_gallery, name="Highlights")
        response = self.client.get(list_url, {"set": str(foreign_set.id)})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_highlights_backfill_is_idempotent_and_preserves_membership(self):
        self.highlights.delete()
        existing_set = PhotoSet.objects.create(gallery=self.gallery, name="Existing", order=2)
        self.asset2.photo_set = existing_set
        self.asset2.save(update_fields=["photo_set"])

        migration = importlib.import_module("apps.photos.migrations.0004_photoset_v2_delta")
        migration.backfill_highlights_sets(importlib.import_module("django.apps").apps, None)
        migration.backfill_highlights_sets(importlib.import_module("django.apps").apps, None)

        highlights = PhotoSet.objects.get(gallery=self.gallery, name="Highlights")
        self.asset1.refresh_from_db()
        self.asset2.refresh_from_db()
        self.assertEqual(self.asset1.photo_set_id, highlights.id)
        self.assertEqual(self.asset2.photo_set_id, existing_set.id)
        self.assertEqual(PhotoSet.objects.filter(gallery=self.gallery, name="Highlights").count(), 1)
