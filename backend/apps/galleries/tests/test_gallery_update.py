# backend/apps/galleries/tests/test_gallery_update.py
"""
Phase 1 regression tests — GALLERY UPDATE / DESIGN SETTINGS.

Covers the P0-1/F-01 bug (design_settings referenced in
GalleryUpdateSerializer with no backing model field, crashing every
PATCH/PUT) and F-13 (title edits regenerating the slug, breaking already
-shared gallery links). See docs/KYAPTURE_PRODUCT_DECISIONS.md #6 and
docs/KYAPTURE_VERIFIED_EXECUTION_PLAN.md.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.subscriptions.testing import grant_plan

User = get_user_model()

# These tests exercise GalleryUpdateSerializer's cover-photo handling, not
# the upload/storage pipeline — MediaAsset fixtures assign original_file as
# a plain string path rather than an actual uploaded file. Django's
# FileField treats a bare string assignment as an already-committed
# reference (no storage.save()/exists() round-trip), which keeps these
# tests independent of whatever storage backend (local/S3) the environment
# is configured with.


class GalleryUpdateTestCase(APITestCase):
    """PATCH/PUT /api/v1/galleries/{slug}/ regression coverage."""

    def setUp(self):
        self.photographer = User.objects.create_user(
            email="photog@kyapture.com",
            password="SecurePassword123!",
            username="photog",
            display_name="Photog Studio",
        )
        self.other_photographer = User.objects.create_user(
            email="other@kyapture.com",
            password="SecurePassword123!",
            username="otherphotog",
            display_name="Other Studio",
        )
        self.client.force_authenticate(user=self.photographer)

        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Original Title",
            slug="original-title",
            branding_color="#000000",
        )
        self.detail_url = f"/api/v1/galleries/{self.gallery.slug}/"

        # A ready photo belonging to this gallery, usable as a cover.
        self.asset = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="photo.jpg",
            file_size=1024,
            original_file="photographers/test/galleries/test/originals/photo.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )

        # A photo belonging to a DIFFERENT photographer's gallery — used to
        # verify cross-tenant cover assignment stays rejected.
        self.other_gallery = Gallery.objects.create(
            photographer=self.other_photographer,
            title="Other Gallery",
            slug="other-gallery",
        )
        self.foreign_asset = MediaAsset.objects.create(
            gallery=self.other_gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="foreign.jpg",
            file_size=1024,
            original_file="photographers/other/galleries/other/originals/foreign.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        self.same_photographer_gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Second Gallery",
            slug="second-gallery",
        )
        self.same_photographer_foreign_asset = MediaAsset.objects.create(
            gallery=self.same_photographer_gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="same-owner-foreign.jpg",
            file_size=1024,
            original_file="photographers/test/galleries/second/originals/foreign.jpg",
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        self.pending_asset = MediaAsset.objects.create(
            gallery=self.gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_name="pending.jpg",
            file_size=1024,
            original_file="photographers/test/galleries/test/originals/pending.jpg",
            processing_status=MediaAsset.ProcessingStatus.PENDING,
        )

    # ── F-01: design_settings must round-trip without crashing ──────────
    def test_patch_design_settings_round_trips(self):
        payload = {
            "design_settings": {
                "layout": "center",
                "typography": "serif",
                "colorPalette": "gold",
                "gridSpacing": 12,
            }
        }
        response = self.client.patch(self.detail_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["design_settings"]["layout"], "center")

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.design_settings["colorPalette"], "gold")

    # ── F-13: a title change must NEVER change the slug ──────────────────
    def test_patch_title_preserves_slug(self):
        original_slug = self.gallery.slug
        response = self.client.patch(
            self.detail_url, {"title": "A Brand New Title"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["title"], "A Brand New Title")
        self.assertEqual(response.data["slug"], original_slug)

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.slug, original_slug)
        self.assertEqual(self.gallery.title, "A Brand New Title")

    # ── Core supported-field round trip ──────────────────────────────────
    def test_patch_supported_fields_round_trip(self):
        # Watermark is a Pro+ feature; this round trip exercises it, so the
        # photographer needs the entitlement (the Free-user rejection is
        # covered in test_branding_watermark_entitlements).
        grant_plan(self.photographer)
        payload = {
            "cover_photo": str(self.asset.id),
            "branding_color": "#FF5733",
            "watermark_enabled": True,
            "event_date": "2026-06-15",
            "expires_at": "2026-12-31",
            "is_published": True,
            "is_downloadable": True,
        }
        response = self.client.patch(self.detail_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, self.asset.id)
        self.assertEqual(self.gallery.branding_color, "#FF5733")
        self.assertTrue(self.gallery.watermark_enabled)
        self.assertEqual(str(self.gallery.event_date), "2026-06-15")
        self.assertTrue(self.gallery.is_published)
        self.assertTrue(self.gallery.allow_download)
        self.assertIsNotNone(self.gallery.expires_at)

    # ── design_settings.coverPhoto syncs onto the model's cover_photo FK ──
    def test_design_settings_cover_photo_syncs_to_model_fk(self):
        self.assertIsNone(self.gallery.cover_photo_id)
        response = self.client.patch(
            self.detail_url,
            {"design_settings": {"coverPhoto": str(self.asset.id)}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, self.asset.id)
        # cover_url itself is None here because this fixture asset has no
        # processed display_file/thumbnail_file (it's a bare original_file
        # path, not a real processed upload) — what this test verifies is
        # the FK sync, which get_cover_url() then reads from unconditionally.
        self.assertIn("cover_url", response.data)

    def test_design_settings_save_without_cover_photo_keeps_existing_cover(self):
        self.gallery.cover_photo = self.asset
        self.gallery.save(update_fields=["cover_photo"])
        response = self.client.patch(
            self.detail_url,
            {"design_settings": {"layout": "left"}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, self.asset.id)

    def test_design_settings_null_cover_photo_keeps_existing_cover(self):
        self.gallery.cover_photo = self.asset
        self.gallery.save(update_fields=["cover_photo"])
        response = self.client.patch(
            self.detail_url,
            {"design_settings": {"layout": "left", "coverPhoto": None}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, self.asset.id)

    def test_design_settings_cover_photo_from_another_gallery_is_rejected(self):
        response = self.client.patch(
            self.detail_url,
            {"design_settings": {"coverPhoto": str(self.same_photographer_foreign_asset.id)}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.gallery.refresh_from_db()
        self.assertIsNone(self.gallery.cover_photo_id)

    def test_cannot_set_pending_photo_as_cover(self):
        response = self.client.patch(
            self.detail_url,
            {"cover_photo": str(self.pending_asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_set_deleted_photo_as_cover(self):
        deleted_id = str(self.asset.id)
        self.asset.delete()
        response = self.client.patch(
            self.detail_url,
            {"cover_photo": deleted_id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_set_same_photographers_other_gallery_photo_as_cover(self):
        response = self.client.patch(
            self.detail_url,
            {"cover_photo": str(self.same_photographer_foreign_asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_set_cover_photo_from_another_photographers_gallery(self):
        response = self.client.patch(
            self.detail_url,
            {"cover_photo": str(self.foreign_asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── PUT behaves the same as PATCH for this partial-update API ────────
    def test_put_updates_gallery(self):
        response = self.client.put(
            self.detail_url,
            {"title": "Put Title Change", "branding_color": "#123456"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.title, "Put Title Change")
        self.assertEqual(self.gallery.slug, "original-title")
        self.assertEqual(self.gallery.branding_color, "#123456")

    # ── Tenant isolation: cannot patch another photographer's gallery ────
    def test_cannot_patch_another_photographers_gallery(self):
        other_url = f"/api/v1/galleries/{self.other_gallery.slug}/"
        response = self.client.patch(other_url, {"title": "Hijacked"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── F-15: sanitize_text must preserve normal characters ───────────────
    def test_patch_title_sanitization_preserves_normal_characters(self):
        response = self.client.patch(
            self.detail_url,
            {"title": "Tom & Jerry's \"Big Day\" 🎉"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["title"], "Tom & Jerry's \"Big Day\" 🎉")

    def test_patch_title_strips_script_tags(self):
        response = self.client.patch(
            self.detail_url,
            {"title": "<script>alert(1)</script>Hello"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertNotIn("<script>", response.data["title"])
        self.assertIn("Hello", response.data["title"])
