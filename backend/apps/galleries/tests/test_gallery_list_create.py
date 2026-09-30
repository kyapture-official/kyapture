# backend/apps/galleries/tests/test_gallery_list_create.py
"""
Regression tests for GET/POST /api/v1/galleries/.

Guards against the 2026-09-30 production regression: `design_settings`
(galleries/0005_gallery_design_settings) and the new MediaAsset derivative
fields (photos/0002_mediaasset_medium_file_...) were added to models.py but
the migrations were never applied to the running database, so every
authenticated GET/POST to /api/v1/galleries/ 500'd with
ProgrammingError: column "design_settings" of relation "galleries" does not
exist as soon as the ORM touched the galleries table.

These are plain APITestCase tests — Django's test runner always builds the
test database from the full migration history, so they cannot by
themselves detect "migration file exists but was never applied to THIS
database." That gap is a deploy/ops concern (run `manage.py migrate`
before serving traffic), not something a unit test can assert. What these
tests guard against is the underlying application-code contract: that
GalleryListSerializer/GalleryCreateSerializer/GalleryCreateSerializer.create()
stay consistent with the Gallery model's actual field set, so a future
field addition to the model doesn't silently break serialization the same
way once migrations ARE applied.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset

User = get_user_model()


class GalleryListCreateTestCase(APITestCase):
    """GET/POST /api/v1/galleries/ regression coverage."""

    url = "/api/v1/galleries/"

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="photog@kyapture.com",
            password="SecurePassword123!",
            username="photog",
            display_name="Photog Studio",
        )
        self.client.force_authenticate(user=self.photographer)

    # ── GET: empty state must not 500 ─────────────────────────────────────
    def test_get_list_empty(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    # ── GET: with an existing gallery row, list serialization must succeed ─
    def test_get_list_with_existing_gallery_does_not_500(self):
        Gallery.objects.create(
            photographer=self.photographer,
            title="Existing Gallery",
            slug="existing-gallery",
            branding_color="#000000",
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["count"], 1)
        result = response.data["results"][0]
        self.assertEqual(result["title"], "Existing Gallery")
        self.assertIn("cover_url", result)
        self.assertIn("photo_count", result)

    # ── GET: a gallery with a cover_photo set exercises the
    #    select_related('cover_photo') join against every MediaAsset
    #    field, including the newer derivative fields. ─────────────────────
    def test_get_list_with_cover_photo_does_not_500(self):
        gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Gallery With Cover",
            slug="gallery-with-cover",
        )
        asset = MediaAsset.objects.create(
            gallery=gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="cover.jpg",
            file_size=1024,
            original_file="photographers/test/galleries/test/originals/cover.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        gallery.cover_photo = asset
        gallery.save(update_fields=["cover_photo"])

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["results"][0]["title"], "Gallery With Cover")

    # ── POST: create must persist design_settings' default and not 500 ────
    def test_post_create_gallery_succeeds(self):
        response = self.client.post(self.url, {"title": "New Gallery"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["title"], "New Gallery")
        self.assertEqual(response.data["slug"], "new-gallery")
        self.assertEqual(response.data["design_settings"], {})

        gallery = Gallery.objects.get(slug="new-gallery")
        self.assertEqual(gallery.photographer, self.photographer)
        self.assertEqual(gallery.design_settings, {})

    # ── POST -> GET: the created gallery must actually appear in the list ──
    def test_created_gallery_appears_in_subsequent_list(self):
        create_response = self.client.post(
            self.url, {"title": "Round Trip Gallery"}, format="json"
        )
        self.assertEqual(
            create_response.status_code, status.HTTP_201_CREATED, create_response.data
        )

        list_response = self.client.get(self.url)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK, list_response.data)
        titles = [g["title"] for g in list_response.data["results"]]
        self.assertIn("Round Trip Gallery", titles)
