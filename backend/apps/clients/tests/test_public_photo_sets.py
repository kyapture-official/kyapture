# backend/apps/clients/tests/test_public_photo_sets.py
"""
Phase 3 regression tests — client-facing PhotoSet tabs.

Covers:
  - PublicGallerySerializer exposes 'photo_sets' with READY-only counts
  - ?set=<id> filters both the embedded first page (PublicGalleryView)
    and the pagination continuation endpoint (PublicGalleryPhotosView)
  - a set id from another gallery cannot be used to leak its photos
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet

User = get_user_model()


def _ready_asset(gallery, name, photo_set=None, order=1):
    return MediaAsset.objects.create(
        gallery=gallery,
        media_type=MediaAsset.MediaType.IMAGE,
        original_name=name,
        file_size=1024,
        order=order,
        original_file=f"photographers/x/galleries/x/originals/{name}",
        processing_status=MediaAsset.ProcessingStatus.READY,
        photo_set=photo_set,
    )


class PublicPhotoSetTestCase(APITestCase):
    def setUp(self):
        self.photographer = User.objects.create_user(
            email="pubsets@kyapture.com",
            password="SecurePassword123!",
            username="pubsetsphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Wedding",
            slug="wedding-sets",
            is_published=True,
            is_active=True,
        )
        self.ceremony = PhotoSet.objects.create(gallery=self.gallery, name="Ceremony", order=1)
        self.reception = PhotoSet.objects.create(gallery=self.gallery, name="Reception", order=2)

        self.ceremony_photo = _ready_asset(self.gallery, "c1.jpg", self.ceremony, order=1)
        _ready_asset(self.gallery, "c2.jpg", self.ceremony, order=2)
        self.reception_photo = _ready_asset(self.gallery, "r1.jpg", self.reception, order=3)
        self.unsorted_photo = _ready_asset(self.gallery, "u1.jpg", None, order=4)

        self.base_url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"

    def test_gallery_payload_includes_set_metadata_with_counts(self):
        response = self.client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        sets_by_name = {s["name"]: s for s in response.data["photo_sets"]}
        self.assertEqual(sets_by_name["Ceremony"]["photo_count"], 2)
        self.assertEqual(sets_by_name["Reception"]["photo_count"], 1)

    def test_unfiltered_gallery_payload_includes_all_photos(self):
        response = self.client.get(self.base_url)
        self.assertEqual(response.data["photos_count"], 4)

    def test_set_filter_on_main_gallery_endpoint(self):
        response = self.client.get(self.base_url, {"set": str(self.ceremony.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["photos_count"], 2)
        names = [p["original_name"] for p in response.data["photos"]]
        self.assertEqual(names, ["c1.jpg", "c2.jpg"])

    def test_set_filter_on_pagination_continuation_endpoint(self):
        url = f"{self.base_url}photos/"
        response = self.client.get(url, {"set": str(self.reception.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["original_name"], "r1.jpg")

    def test_set_from_another_gallery_returns_no_photos(self):
        other_gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Other",
            slug="other-sets-gallery",
            is_published=True,
            is_active=True,
        )
        foreign_set = PhotoSet.objects.create(gallery=other_gallery, name="Foreign", order=1)
        _ready_asset(other_gallery, "foreign.jpg", foreign_set, order=1)

        response = self.client.get(self.base_url, {"set": str(foreign_set.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # The set id is real, just not one that belongs to THIS gallery —
        # the filter is always AND-ed with gallery=gallery, so it yields
        # zero photos rather than leaking the other gallery's asset.
        self.assertEqual(response.data["photos_count"], 0)
