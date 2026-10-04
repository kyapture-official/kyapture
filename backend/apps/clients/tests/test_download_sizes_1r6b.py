# backend/apps/clients/tests/test_download_sizes_1r6b.py
"""
Task 1R.6-B — Download > General sizes layout.

  - Web Size choices are 2048 / 1024 / 640; a stored/sent 1280 is the same
    (medium) tier and reads and saves as 1024, never an error
  - a source that cannot be decoded falls back to the nearest stored tier (the exact-px
    derivation for decodable images is covered in test_download_pages_1r5b)
  - at least one of High Resolution / Web Size must stay on
  - the Pro-only Original rule is unchanged (also covered in
    test_download_policy_1r6.OriginalDownloadEntitlementTests)
"""
from django.core.cache import cache
from django.core.files.base import ContentFile
from rest_framework import status

from apps.clients.tests.test_download_access_flow import DownloadFlowBase, _zip_entries


class WebSizeTierTests(DownloadFlowBase):
    with_pin = False

    def setUp(self):
        super().setUp()
        for asset in (self.a1, self.a2, self.b1):
            name = asset.original_name
            asset.medium_file.save(f"{name}.medium.webp", ContentFile(b"MEDIUM:" + name.encode()), save=False)
            asset.thumbnail_file.save(f"{name}.thumb.webp", ContentFile(b"THUMB:" + name.encode()), save=False)
            asset.save(update_fields=["medium_file", "thumbnail_file"])
        self.detail_url = f"/api/v1/galleries/{self.gallery.slug}/"

    def _store_px(self, px):
        self.gallery.design_settings = {"downloads": {"web": {"enabled": True, "px": px}}}
        self.gallery.save(update_fields=["design_settings"])

    def _patch_web(self, px):
        self.client.force_authenticate(user=self.photographer)
        return self.client.patch(
            self.detail_url, {"design_settings": {"downloads": {"web": {"enabled": True, "px": px}}}}, format="json",
        )

    def test_a_stored_1280_reads_as_1024_in_the_public_policy(self):
        self._store_px(1280)
        self.assertEqual(self.client.get(self.base).data["download_policy"]["web_px"], 1024)

    def test_stored_1280_still_downloads_without_error_from_the_medium_tier(self):
        self._store_px(1280)
        token = self.token()
        entries = _zip_entries(self.zip(token, resolution="web"))
        self.assertEqual(entries["a1.webp"], b"MEDIUM:a1.jpg")

    def test_an_undecodable_source_falls_back_to_the_nearest_stored_tier(self):
        for px, expected in ((1024, b"MEDIUM:a1.jpg"), (2048, b"DISPLAY:a1.jpg"), (640, b"THUMB:a1.jpg")):
            cache.clear()  # download-access + ZIP prepare share a 5/min throttle
            self._store_px(px)
            # a unique email per size: an identical ready job is reused, not rebuilt
            token = self.token(email=f"size{px}@example.com")
            entries = _zip_entries(self.zip(token, resolution="web"))
            self.assertEqual(entries["a1.webp"], expected, px)

    def test_saving_1280_is_accepted_and_stored_as_1024(self):
        response = self._patch_web(1280)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["design_settings"]["downloads"]["web"]["px"], 1024)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.design_settings["downloads"]["web"]["px"], 1024)

    def test_the_three_labelled_sizes_save_as_is(self):
        for px in (2048, 1024, 640):
            response = self._patch_web(px)
            self.assertEqual(response.status_code, status.HTTP_200_OK, (px, response.data))
            self.assertEqual(response.data["design_settings"]["downloads"]["web"]["px"], px)

    def test_other_sizes_are_rejected(self):
        for bad in (1000, 3600, "1024", True, None):
            response = self._patch_web(bad)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)

    def test_a_malformed_stored_px_falls_back_instead_of_crashing(self):
        for bad in ("big", None, [1], True, 777):
            self._store_px(bad)
            response = self.client.get(self.base)
            self.assertEqual(response.status_code, status.HTTP_200_OK, bad)
            self.assertEqual(response.data["download_policy"]["web_px"], 2048, bad)


class AtLeastOneSizeTests(DownloadFlowBase):
    with_pin = False

    def _patch(self, high_res, web):
        self.client.force_authenticate(user=self.photographer)
        return self.client.patch(
            f"/api/v1/galleries/{self.gallery.slug}/",
            {"design_settings": {"downloads": {"high_res": {"enabled": high_res}, "web": {"enabled": web}}}},
            format="json",
        )

    def test_both_sizes_off_is_rejected_and_nothing_is_saved(self):
        response = self._patch(False, False)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("at least one", str(response.data).lower())
        self.gallery.refresh_from_db()
        self.assertNotIn("downloads", self.gallery.design_settings or {})

    def test_either_one_alone_is_fine(self):
        self.assertEqual(self._patch(True, False).status_code, status.HTTP_200_OK)
        self.assertEqual(self._patch(False, True).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(self.base).data["download_policy"]["allowed_sizes"], ["web"])
