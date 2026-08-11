# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/tests/test_bulk_actions.py
# backend/apps/photos/tests/test_bulk_actions.py

import io
from decimal import Decimal
from PIL import Image as PILImage
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset

User = get_user_model()


class PhotoBulkActionsTestCase(APITestCase):
    """
    Automated integration tests validating the transactional bulk deletion 
    and decimal-sequenced drag-and-drop reordering views.
    """

    def setUp(self):
        # 1. Create photographer test profile
        self.photographer = User.objects.create_user(
            email="bulk_photog@kyapture.com",
            password="SecurePassword123!",
            username="bulkphotog"
        )
        self.photographer.is_active_plan = True
        self.photographer.save(update_fields=['is_active_plan'])

        # 2. Create active gallery owned by photographer
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Bulk Test Gallery",
            slug="bulk-test"
        )

        # Force authentication globally for the test client
        self.client.force_authenticate(user=self.photographer)

    def generate_dummy_image(self, name="photo.jpg"):
        """Generates a genuine in-memory JPEG file stream (with correct magic bytes)."""
        file_stream = io.BytesIO()
        image = PILImage.new("RGB", (50, 50), color="white")
        image.save(file_stream, "JPEG")
        return SimpleUploadedFile(
            name=name,
            content=file_stream.getvalue(),
            content_type="image/jpeg"
        )

    def create_test_asset(self, title, order_val):
        """Helper to create and save a MediaAsset record directly."""
        img = self.generate_dummy_image(f"{title}.jpg")
        return MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_file=img,
            original_name=f"{title}.jpg",
            file_size=img.size,
            title=title,
            processing_status=MediaAsset.ProcessingStatus.READY,
            order=Decimal(order_val)
        )

    def test_bulk_delete_assets_successfully(self):
        """
        Verify that a photographer can bulk-delete multiple selected assets in their gallery.
        Expected: Database rows are purged cleanly, S3 files are deleted, and only selected assets are deleted.
        """
        asset_1 = self.create_test_asset("entrance", "1.0")
        asset_2 = self.create_test_asset("ring_exchange", "2.0")
        asset_3 = self.create_test_asset("cake_cut", "3.0")

        bulk_delete_url = f"/api/v1/photos/{self.gallery.slug}/delete-bulk/"
        payload = {
            "photo_ids": [str(asset_1.id), str(asset_2.id)]
        }

        response = self.client.post(bulk_delete_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted_count"], 2)

        # Assert selected assets are purged
        self.assertFalse(MediaAsset.objects.filter(id=asset_1.id).exists())
        self.assertFalse(MediaAsset.objects.filter(id=asset_2.id).exists())
        # Assert unselected asset remains untouched
        self.assertTrue(MediaAsset.objects.filter(id=asset_3.id).exists())

    def test_bulk_delete_ignores_foreign_assets_silently(self):
        """
        Verify that attempting to bulk-delete assets belonging to another gallery/user 
        fails silently (unauthorized IDs are ignored and database security boundaries are preserved).
        """
        # Create photographer B and their private gallery
        other_user = User.objects.create_user(
            email="other_photog@test.com",
            password="SecurePassword123!",
            username="otherphotog"
        )
        other_user.is_active_plan = True
        other_user.save()
        
        other_gallery = Gallery.objects.create(
            photographer=other_user,
            title="Foreign Gallery",
            slug="foreign-gallery"
        )
        
        # Create asset in photographer B's gallery
        other_img = self.generate_dummy_image("foreign.jpg")
        foreign_asset = MediaAsset.objects.create(
            gallery=other_gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_file=other_img,
            original_name="foreign.jpg",
            file_size=other_img.size,
            title="Foreign",
            processing_status=MediaAsset.ProcessingStatus.READY,
            order=Decimal("1.0")
        )

        # Create asset in photographer A's gallery
        own_asset = self.create_test_asset("own_photo", "1.0")

        # Photographer A attempts to bulk-delete both their own asset AND the other photographer's asset
        bulk_delete_url = f"/api/v1/photos/{self.gallery.slug}/delete-bulk/"
        payload = {
            "photo_ids": [str(own_asset.id), str(foreign_asset.id)]
        }

        response = self.client.post(bulk_delete_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Assert only own asset was deleted; foreign asset is silently ignored and untouched
        self.assertEqual(response.data["deleted_count"], 1)
        self.assertFalse(MediaAsset.objects.filter(id=own_asset.id).exists())
        self.assertTrue(MediaAsset.objects.filter(id=foreign_asset.id).exists())

    def test_reorder_assets_sequentially(self):
        """
        Verify that sending an array of asset UUIDs updates their decimal sorting positions 
        sequentially based on the requested order array.
        """
        asset_1 = self.create_test_asset("first", "1.0")
        asset_2 = self.create_test_asset("second", "2.0")
        asset_3 = self.create_test_asset("third", "3.0")

        reorder_url = f"/api/v1/photos/{self.gallery.slug}/reorder/"
        
        # Request order inversion: [third, second, first]
        payload = {
            "ordered_ids": [str(asset_3.id), str(asset_2.id), str(asset_1.id)]
        }

        response = self.client.patch(reorder_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["success"], True)

        # Refetch from DB and verify decimal values updated sequentially (1.00, 2.00, 3.00)
        asset_3.refresh_from_db()
        asset_2.refresh_from_db()
        asset_1.refresh_from_db()

        self.assertEqual(asset_3.order, Decimal("1.0"))
        self.assertEqual(asset_2.order, Decimal("2.0"))
        self.assertEqual(asset_1.order, Decimal("3.0"))

    def test_reorder_rejects_foreign_or_invalid_ids(self):
        """
        Verify that attempting to reorder utilizing non-existent or foreign UUIDs 
        returns a 400 Bad Request to prevent grid-corruption injection attempts.
        """
        reorder_url = f"/api/v1/photos/{self.gallery.slug}/reorder/"
        fake_uuid = "019f74d0-7b7d-71b2-b425-5852e5334b41"

        response = self.client.patch(reorder_url, {"ordered_ids": [fake_uuid]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)