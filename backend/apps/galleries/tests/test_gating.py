import io
from PIL import Image as PILImage
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.subscriptions.models import SubscriptionPlan, UserSubscription
from apps.galleries.models import Gallery
from apps.photos.models import Photo

User = get_user_model()


class SaaSResourceGatingTestCase(APITestCase):
    """
    Automated integration tests validating subscription resource gating limits.
    """

    def setUp(self):
        # 1. Create photographer test profile
        self.photographer = User.objects.create_user(
            email="test_photog@kyapture.com",
            password="SecurePassword123!",
            display_name="Test Studio"
        )
        
        # 2. Build strict mock subscription plan to trigger limits with low usage
        self.strict_plan = SubscriptionPlan.objects.create(
            name="Strict Gating Plan",
            price=19.99,
            max_galleries=2,
            max_photos_per_gallery=2,
            storage_gb=1,
            is_active=True
        )

        # 3. Bind active subscription to photographer
        self.subscription = UserSubscription.objects.create(
            user=self.photographer,
            plan=self.strict_plan,
            status=UserSubscription.SubscriptionStatus.ACTIVE,
            starts_at=timezone_now_fallback(),
            expires_at=timezone_now_fallback() + timedelta_fallback(days=30),
            payment_method=UserSubscription.PaymentMethod.MANUAL
        )

        # 4. Activate photographer billing permission flag to pass IsSubscribed view-level gate
        self.photographer.is_active_plan = True
        self.photographer.save(update_fields=['is_active_plan'])

        # Force authentication globally for the test client
        self.client.force_authenticate(user=self.photographer)

    def generate_dummy_image(self, name="photo.jpg"):
        file_stream = io.BytesIO()
        image = PILImage.new("RGB", (50, 50), color="white")
        image.save(file_stream, "JPEG")
        file_stream.seek(0)
        return SimpleUploadedFile(
            name=name,
            content=file_stream.read(),
            content_type="image/jpeg"
        )

    def test_gallery_creation_limit_gating(self):
        """
        Verify that a photographer cannot exceed their plan's maximum active gallery count.
        Expected: Creating 1st and 2nd succeeds. Creating 3rd raises gallery_limit_reached (403).
        """
        create_url = "/api/v1/galleries/"

        # Create Gallery 1 (Success)
        response_1 = self.client.post(create_url, {"title": "Wedding Gallery"})
        self.assertEqual(response_1.status_code, status.HTTP_201_CREATED)

        # Create Gallery 2 (Success)
        response_2 = self.client.post(create_url, {"title": "Engagement Gallery"})
        self.assertEqual(response_2.status_code, status.HTTP_201_CREATED)

        # Attempt Gallery 3 (Must Fail with Gating Violation)
        response_3 = self.client.post(create_url, {"title": "Portrait Gallery"})
        
        self.assertEqual(response_3.status_code, status.HTTP_403_FORBIDDEN)
        # Resilient payload search (handles standard DRF and global nested exceptions)
        self.assertIn("gallery_limit_reached", str(response_3.data))

    def test_photo_upload_count_gating(self):
        """
        Verify that a photographer cannot exceed their plan's maximum photos per gallery limit.
        Expected: Uploading up to 2 photos succeeds. Uploading the 3rd raises photo_limit_reached (400).
        """
        gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="SaaS Test Gallery",
            slug="saas-test-gallery"
        )
        upload_url = f"/api/v1/photos/{gallery.slug}/upload/"

        # Upload Photo 1 (Success)
        img_1 = self.generate_dummy_image("file_1.jpg")
        response_1 = self.client.post(upload_url, {"image": [img_1]}, format="multipart")
        self.assertEqual(response_1.status_code, status.HTTP_201_CREATED)

        # Upload Photo 2 (Success)
        img_2 = self.generate_dummy_image("file_2.jpg")
        response_2 = self.client.post(upload_url, {"image": [img_2]}, format="multipart")
        self.assertEqual(response_2.status_code, status.HTTP_201_CREATED)

        # Upload Photo 3 (Must Fail with Gating Violation)
        img_3 = self.generate_dummy_image("file_3.jpg")
        response_3 = self.client.post(upload_url, {"image": [img_3]}, format="multipart")

        self.assertEqual(response_3.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("photo_limit_reached", str(response_3.data))

    def test_storage_quota_gating(self):
        """
        Verify that a photographer cannot upload files exceeding their aggregate storage quota.
        Expected: Image upload with 0 bytes storage plan limit returns storage_quota_exceeded / storage_limit_reached (400).
        """
        self.strict_plan.storage_gb = 0
        self.strict_plan.save()

        gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Storage Test Gallery",
            slug="storage-test"
        )
        upload_url = f"/api/v1/photos/{gallery.slug}/upload/"

        img = self.generate_dummy_image("heavy_photo.jpg")
        response = self.client.post(upload_url, {"image": [img]}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_str = str(response.data)
        self.assertTrue(
            "storage_limit_reached" in response_str or "storage_quota_exceeded" in response_str
        )


def timezone_now_fallback():
    try:
        from django.utils import timezone
        return timezone.now()
    except ImportError:
        import datetime
        return datetime.datetime.now()

def timedelta_fallback(days):
    import datetime
    return datetime.timedelta(days=days)