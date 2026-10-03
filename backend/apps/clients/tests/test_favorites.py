# backend/apps/clients/tests/test_favorites.py
"""
Phase 3 regression tests — FAVORITES.

Covers add/remove idempotency, persistence (batch list-back), the two
client-identity paths (open gallery client_uid vs protected-gallery
session token), cross-gallery/cross-tenant isolation, and the
photographer-facing favorite activity feed.
"""
import bcrypt
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.clients.models import ClientSession, Favorite

User = get_user_model()


def _make_asset(gallery, name="photo.jpg"):
    return MediaAsset.objects.create(
        gallery=gallery,
        media_type=MediaAsset.MediaType.IMAGE,
        original_name=name,
        file_size=1024,
        original_file=f"photographers/x/galleries/x/originals/{name}",
        processing_status=MediaAsset.ProcessingStatus.READY,
    )


class OpenGalleryFavoritesTestCase(APITestCase):
    """A non-password-protected gallery: identity is a client-supplied uid."""

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="favopen@kyapture.com",
            password="SecurePassword123!",
            username="favopenphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Open Gallery",
            slug="open-gallery",
            is_published=True,
            is_active=True,
        )
        self.asset = _make_asset(self.gallery)
        self.url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/favorites/"

    def test_client_uid_required_on_open_gallery(self):
        response = self.client.post(self.url, {"media_asset_id": str(self.asset.id)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_favorite_then_list_shows_it(self):
        response = self.client.post(
            self.url,
            {"media_asset_id": str(self.asset.id), "client_uid": "visitor-abc"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["favorited"])

        list_response = self.client.get(self.url, {"client_uid": "visitor-abc"})
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(str(self.asset.id), list_response.data["favorited_ids"])

    def test_favoriting_twice_is_idempotent(self):
        payload = {"media_asset_id": str(self.asset.id), "client_uid": "visitor-abc"}
        self.client.post(self.url, payload, format="json")
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Favorite.objects.filter(gallery=self.gallery, media_asset=self.asset).count(), 1
        )

    def test_unfavorite_removes_it(self):
        payload = {"media_asset_id": str(self.asset.id), "client_uid": "visitor-abc"}
        self.client.post(self.url, payload, format="json")
        response = self.client.delete(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["favorited"])
        self.assertFalse(Favorite.objects.filter(gallery=self.gallery, media_asset=self.asset).exists())

    def test_unfavoriting_something_never_favorited_is_a_no_op(self):
        payload = {"media_asset_id": str(self.asset.id), "client_uid": "visitor-abc"}
        response = self.client.delete(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["favorited"])

    def test_different_client_uids_have_independent_favorites(self):
        self.client.post(
            self.url, {"media_asset_id": str(self.asset.id), "client_uid": "visitor-a"}, format="json"
        )
        list_b = self.client.get(self.url, {"client_uid": "visitor-b"})
        self.assertEqual(list_b.data["favorited_ids"], [])

    def test_cannot_favorite_asset_from_another_gallery(self):
        other_gallery = Gallery.objects.create(
            photographer=self.photographer, title="Other", slug="other-open", is_published=True, is_active=True,
        )
        other_asset = _make_asset(other_gallery, "other.jpg")
        response = self.client.post(
            self.url,
            {"media_asset_id": str(other_asset.id), "client_uid": "visitor-abc"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ProtectedGalleryFavoritesTestCase(APITestCase):
    """A password-protected gallery: identity is the verified session token."""

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="favprot@kyapture.com",
            password="SecurePassword123!",
            username="favprotphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Protected Gallery",
            slug="protected-fav-gallery",
            is_published=True,
            is_active=True,
            is_password_protected=True,
        )
        self.gallery.password_hash = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["password_hash"])
        self.asset = _make_asset(self.gallery)
        self.url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/favorites/"

    def _unlock(self, email=""):
        response = self.client.post(
            f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/unlock/",
            {"password": "secret123", "email": email},
            format="json",
        )
        return response.data["access_token"]

    def test_favorite_requires_valid_session(self):
        response = self.client.post(self.url, {"media_asset_id": str(self.asset.id)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_token_rejected(self):
        response = self.client.post(
            self.url,
            {"media_asset_id": str(self.asset.id)},
            format="json",
            HTTP_AUTHORIZATION="Bearer not-a-real-token",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_favorite_with_valid_session_links_session_and_email(self):
        token = self._unlock(email="guest@example.com")
        response = self.client.post(
            self.url,
            {"media_asset_id": str(self.asset.id)},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        favorite = Favorite.objects.get(gallery=self.gallery, media_asset=self.asset)
        self.assertEqual(favorite.client_key, token)
        self.assertEqual(favorite.email, "guest@example.com")
        self.assertEqual(favorite.client_session.access_token, token)

    def test_client_cannot_fabricate_identity_for_protected_gallery(self):
        """
        A client_uid in the body is simply ignored for a protected gallery
        — identity always comes from the verified session token, never
        from client-supplied input, even if both are present.
        """
        token = self._unlock()
        self.client.post(
            self.url,
            {"media_asset_id": str(self.asset.id), "client_uid": "attacker-supplied-id"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        favorite = Favorite.objects.get(gallery=self.gallery, media_asset=self.asset)
        self.assertEqual(favorite.client_key, token)
        self.assertNotEqual(favorite.client_key, "attacker-supplied-id")


class PhotographerFavoriteActivityTestCase(APITestCase):
    """GET /api/v1/galleries/{slug}/favorites/ — photographer-facing view."""

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="favactivity@kyapture.com",
            password="SecurePassword123!",
            username="favactivityphotog",
        )
        self.other_photographer = User.objects.create_user(
            email="otherfavactivity@kyapture.com",
            password="SecurePassword123!",
            username="otherfavactivityphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Mine",
            slug="mine-fav-activity",
            is_published=True,
            is_active=True,
        )
        self.other_gallery = Gallery.objects.create(
            photographer=self.other_photographer,
            title="Theirs",
            slug="theirs-fav-activity",
            is_published=True,
            is_active=True,
        )
        self.asset = _make_asset(self.gallery)
        self.other_asset = _make_asset(self.other_gallery, "theirs.jpg")

        Favorite.objects.create(
            gallery=self.gallery, media_asset=self.asset, client_key="visitor-1", email="a@example.com"
        )
        Favorite.objects.create(
            gallery=self.other_gallery, media_asset=self.other_asset, client_key="visitor-2"
        )

    def test_photographer_sees_only_their_own_gallerys_favorites(self):
        self.client.force_authenticate(user=self.photographer)
        response = self.client.get(f"/api/v1/galleries/{self.gallery.slug}/favorites/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        emails = [row["email"] for row in response.data["results"]]
        self.assertIn("a@example.com", emails)
        self.assertEqual(len(response.data["results"]), 1)

    def test_cannot_view_another_photographers_favorite_activity(self):
        self.client.force_authenticate(user=self.photographer)
        response = self.client.get(f"/api/v1/galleries/{self.other_gallery.slug}/favorites/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_requires_authentication(self):
        response = self.client.get(f"/api/v1/galleries/{self.gallery.slug}/favorites/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
