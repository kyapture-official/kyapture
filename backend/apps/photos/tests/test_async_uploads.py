# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/tests/test_async_uploads.py
import io
from unittest.mock import patch
from PIL import Image as PILImage
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.subscriptions.models import SubscriptionPlan, UserSubscription
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset

User = get_user_model()


class PhotoAsyncUploadTestCase(APITestCase):
    """
    Automated integration tests validating the asynchronous, non-blocking 
    upload pipeline, magic-byte safety validations, and Celery task dispatchers.
    """

    def setUp(self):
        # 1. Create photographer test profile
        self.photographer = User.objects.create_user(
            email="async_photog@kyapture.com",
            password="SecurePassword123!",
            display_name="Async Studio"
        )
        
        # 2. Build mock subscription plan
        self.plan = SubscriptionPlan.objects.create(
            name="Async Pro Plan",
            price=29.99,
            max_galleries=5,
            max_photos_per_gallery=100,
            storage_gb=10,
            is_active=True
        )

        # 3. Bind active subscription to photographer
        self.subscription = UserSubscription.objects.create(
            user=self.photographer,
            plan=self.plan,
            status=UserSubscription.SubscriptionStatus.ACTIVE,
            starts_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(days=30),
            payment_method=UserSubscription.PaymentMethod.MANUAL
        )

        # 4. Activate photographer billing permission flag
        self.photographer.is_active_plan = True
        self.photographer.save(update_fields=['is_active_plan'])

        # 5. Create active gallery
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Async Collection",
            slug="async-collection"
        )

        # Force authentication globally for the test client
        self.client.force_authenticate(user=self.photographer)

    def generate_dummy_image(self, name="photo.jpg"):
        """Generates a genuine in-memory JPEG file stream (with correct magic bytes)."""
        file_stream = io.BytesIO()
        image = PILImage.new("RGB", (50, 50), color="white")
        image.save(file_stream, "JPEG")
        file_stream.seek(0)
        return SimpleUploadedFile(
            name=name,
            content=file_stream.getvalue(),
            content_type="image/jpeg"
        )

    @patch('apps.photos.views.process_photo_asset.delay')
    def test_non_blocking_upload_returns_202_and_dispatches_task(self, mock_celery_task):
        """
        Verify that a valid image upload is non-blocking.
        Expected: Returns 202 Accepted, asset is marked 'pending', 
        and Celery task is dispatched exactly once with the asset's UUID.
        """
        upload_url = f"/api/v1/photos/{self.gallery.slug}/upload/"
        img = self.generate_dummy_image("wedding_entrance.jpg")

        response = self.client.post(upload_url, {"image": [img]}, format="multipart")
        
        # ─── DEBUG PRINT ───
        print("\n=== DEBUG: UPLOAD RESPONSE DATA ===")
        print(response.data if hasattr(response, 'data') else response.content)
        print("===================================\n")

        # 1. Assert HTTP Status 202 Accepted (Non-blocking design)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # 2. Assert that a MediaAsset record was written to the DB under 'pending' status
        self.assertEqual(MediaAsset.objects.filter(gallery=self.gallery).count(), 1)
        asset = MediaAsset.objects.first()
        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.PENDING)
        self.assertEqual(asset.media_type, MediaAsset.MediaType.IMAGE)

        # 3. Assert the response data matches 'pending' serialization expectations
        self.assertEqual(response.data[0]["processing_status"], "pending")
        self.assertEqual(response.data[0]["id"], str(asset.id))

        # 4. Assert that the Celery background task was dispatched with the correct UUID
        mock_celery_task.assert_called_once_with(str(asset.id))

    def test_upload_fails_on_invalid_magic_bytes(self):
        """
        Verify that uploading a malicious non-image file renamed with a '.jpg' extension 
        is intercepted at the gate and rejected before database writes or tasks occur.
        """
        upload_url = f"/api/v1/photos/{self.gallery.slug}/upload/"
        
        # Construct a fake image file containing plain text bytes (violates magic-byte signatures)
        fake_image = SimpleUploadedFile(
            name="exploit.jpg",
            content=b"System exploit script payload.",
            content_type="image/jpeg"
        )

        response = self.client.post(upload_url, {"image": [fake_image]}, format="multipart")

        # Assert HTTP Status 400 Bad Request
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Assert the database remains untouched
        self.assertEqual(MediaAsset.objects.filter(gallery=self.gallery).count(), 0)
        # Safe match: Passes whether caught by Django's native image field validator or our custom magic-byte gate
        response_str = str(response.data)
        self.assertTrue(
            "invalid_file_signature" in response_str or "invalid_image" in response_str
        )