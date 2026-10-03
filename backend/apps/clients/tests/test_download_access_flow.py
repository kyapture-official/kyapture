# backend/apps/clients/tests/test_download_access_flow.py
"""
Explicit-download flow tests — Pixieset-style client download behaviour.

Covers:
  - opening/browsing a gallery never needs (or triggers) download
    authorization, even when a download PIN is configured
  - gallery password and download PIN are separate gates
  - POST .../download-access/: PIN verified server-side, email captured only
    there, returns a short-lived signed token
  - that token authorizes single-photo and full-gallery/set downloads, is
    remembered across photos, and is bound to its gallery and to the PIN
  - direct endpoint calls, forged/expired/foreign tokens, and gallery/set/
    asset id manipulation cannot bypass any gate
  - DownloadLog rows carry email / scope / resolution / pin_verified, and the
    photographer's Download Activity API returns them
  - errors use the existing {'error', 'code'} shape and never leak exceptions
"""
import io
import zipfile
from unittest import mock

import bcrypt
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.clients.models import ClientSession, DownloadLog
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet

User = get_user_model()

PIN = "4821"


def _asset(gallery, name="photo.jpg", photo_set=None, order=0):
    asset = MediaAsset(
        gallery=gallery,
        media_type=MediaAsset.MediaType.IMAGE,
        original_name=name,
        file_size=1024,
        order=order,
        photo_set=photo_set,
        processing_status=MediaAsset.ProcessingStatus.READY,
    )
    # original_name is untrusted (it may hold ../ segments); storage only
    # ever sees a plain basename, exactly as the upload pipeline does.
    stored = name.split("/")[-1]
    asset.original_file.save(stored, ContentFile(b"ORIGINAL:" + name.encode()), save=False)
    asset.save()
    asset.display_file.save(f"{stored}.display.webp", ContentFile(b"DISPLAY:" + name.encode()), save=False)
    asset.download_file.save(f"{stored}.master.jpg", ContentFile(b"MASTER:" + name.encode()), save=False)
    asset.save(update_fields=["display_file", "download_file"])
    return asset


def _zip_entries(response):
    with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


class DownloadFlowBase(APITestCase):
    username = "flowphotog"
    slug = "flow-gallery"
    with_pin = True

    def setUp(self):
        cache.clear()
        self.photographer = User.objects.create_user(
            email=f"{self.username}@kyapture.com", password="SecurePassword123!", username=self.username,
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer, title="Flow", slug=self.slug,
            is_published=True, is_active=True, allow_download=True,
        )
        if self.with_pin:
            self.gallery.download_pin_hash = bcrypt.hashpw(PIN.encode(), bcrypt.gensalt()).decode()
            self.gallery.save(update_fields=["download_pin_hash"])
        self.ceremony = PhotoSet.objects.create(gallery=self.gallery, name="Ceremony", order=1)
        self.party = PhotoSet.objects.create(gallery=self.gallery, name="Party", order=2)
        self.a1 = _asset(self.gallery, "a1.jpg", self.ceremony, order=1)
        self.a2 = _asset(self.gallery, "a2.jpg", self.ceremony, order=2)
        self.b1 = _asset(self.gallery, "b1.jpg", self.party, order=3)

        self.base = f"/api/v1/public/{self.username}/{self.slug}/"
        self.access_url = f"{self.base}download-access/"
        self.zip_url = f"{self.base}download-all/"

    def photo_url(self, asset, gallery_base=None):
        return f"{gallery_base or self.base}photo/{asset.id}/download/"

    def authorize(self, **body):
        body.setdefault("email", "client@example.com")
        if self.with_pin:
            body.setdefault("pin", PIN)
        return self.client.post(self.access_url, body, format="json")

    def token(self, **body):
        response = self.authorize(**body)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data["download_token"]


class OpeningAGalleryNeverNeedsDownloadAuthTests(DownloadFlowBase):
    def test_gallery_with_download_pin_opens_without_any_pin_or_email(self):
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertNotIn("requires_password", response.data)
        self.assertTrue(response.data["has_download_pin"])
        self.assertTrue(response.data["allow_download"])
        self.assertEqual(len(response.data["photos"]), 3)

    def test_browsing_pagination_and_sets_trigger_no_download_authorization(self):
        self.assertEqual(self.client.get(self.base).status_code, 200)
        self.assertEqual(self.client.get(f"{self.base}photos/").status_code, 200)
        self.assertEqual(self.client.get(self.base, {"set": str(self.ceremony.id)}).status_code, 200)
        self.assertFalse(DownloadLog.objects.exists())
        self.assertFalse(ClientSession.objects.exists())

    def test_favorites_work_without_download_email_or_pin(self):
        response = self.client.post(
            f"{self.base}favorites/",
            {"media_asset_id": str(self.a1.id), "client_uid": "browser-1"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(DownloadLog.objects.exists())

    def test_photo_payload_exposes_download_url_even_with_pin(self):
        # The grid keeps its download affordance; the PIN is enforced when
        # the client actually downloads, not by hiding the button.
        photo = self.client.get(self.base).data["photos"][0]
        self.assertTrue(photo["download_url"])


class GalleryPasswordAndDownloadPinAreSeparateTests(DownloadFlowBase):
    def setUp(self):
        super().setUp()
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b"gallerypass", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["is_password_protected", "password_hash"])
        unlock = self.client.post(f"{self.base}unlock/", {"password": "gallerypass"}, format="json")
        self.assertEqual(unlock.status_code, 200, unlock.data)
        self.unlock_token = unlock.data["access_token"]

    def test_protected_gallery_still_requires_the_gallery_password_to_open(self):
        self.assertTrue(self.client.get(self.base).data.get("requires_password"))

    def test_gallery_password_alone_does_not_grant_download(self):
        response = self.client.get(self.photo_url(self.a1), {"token": self.unlock_token})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "pin_required")
        zipped = self.client.get(self.zip_url, {"token": self.unlock_token})
        self.assertEqual(zipped.status_code, status.HTTP_403_FORBIDDEN)

    def test_correct_pin_alone_does_not_bypass_the_gallery_password(self):
        response = self.client.post(self.access_url, {"email": "c@example.com", "pin": PIN}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "session_required")

    def test_download_token_does_not_replace_the_gallery_unlock_session(self):
        token = self.token(token=self.unlock_token)
        no_session = self.client.get(self.photo_url(self.a1), {"download_token": token})
        self.assertEqual(no_session.status_code, status.HTTP_401_UNAUTHORIZED)
        both = self.client.get(self.photo_url(self.a1), {"download_token": token, "token": self.unlock_token})
        self.assertEqual(both.status_code, status.HTTP_200_OK)

    def test_unlock_session_token_is_accepted_via_bearer_header(self):
        response = self.client.post(
            self.access_url, {"email": "c@example.com", "pin": PIN}, format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.unlock_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_email_given_at_unlock_is_reused_so_download_does_not_ask_again(self):
        session = ClientSession.objects.get(access_token=self.unlock_token)
        session.email = "known@example.com"
        session.save(update_fields=["email"])
        response = self.client.post(
            self.access_url, {"pin": PIN, "token": self.unlock_token}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["email"], "known@example.com")

    def test_download_email_is_saved_on_the_session_when_it_had_none(self):
        self.authorize(token=self.unlock_token, email="new@example.com")
        session = ClientSession.objects.get(access_token=self.unlock_token)
        self.assertEqual(session.email, "new@example.com")
        self.assertTrue(session.has_download_access)

    def test_existing_session_email_is_never_overwritten(self):
        session = ClientSession.objects.get(access_token=self.unlock_token)
        session.email = "first@example.com"
        session.save(update_fields=["email"])
        self.authorize(token=self.unlock_token, email="second@example.com")
        session.refresh_from_db()
        self.assertEqual(session.email, "first@example.com")


class DownloadAccessEndpointTests(DownloadFlowBase):
    def test_public_download_policy_defaults_to_email_and_both_sizes(self):
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['download_policy'],
            {'allowed_sizes': ['download', 'web'], 'require_email': True},
        )

    def test_correct_pin_and_email_issue_a_token(self):
        response = self.authorize()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["download_token"])
        self.assertTrue(response.data["pin_verified"])
        self.assertEqual(response.data["email"], "client@example.com")
        self.assertGreater(response.data["expires_in"], 0)
        # Authorizing is not downloading: no activity row yet.
        self.assertFalse(DownloadLog.objects.exists())

    def test_wrong_pin_rejected(self):
        response = self.authorize(pin="0000")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "invalid_pin")
        self.assertNotIn("download_token", response.data)

    def test_missing_pin_rejected(self):
        response = self.client.post(self.access_url, {"email": "c@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "pin_required")

    def test_non_string_pin_is_a_clean_rejection_not_a_server_error(self):
        for bad in (1234, None, ["1", "2"], {"a": 1}, True):
            cache.clear()
            response = self.client.post(
                self.access_url, {"email": "c@example.com", "pin": bad}, format="json"
            )
            self.assertIn(response.status_code, (401,), (bad, response.data))

    def test_email_is_required_when_there_is_no_session_email(self):
        response = self.client.post(self.access_url, {"pin": PIN}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "email_required")

    def test_malformed_email_rejected(self):
        for bad in ("not-an-email", "a@", "x" * 300 + "@example.com"):
            cache.clear()
            response = self.authorize(email=bad)
            self.assertEqual(response.status_code, 400, bad)
            self.assertEqual(response.data["code"], "invalid_email")

    def test_downloads_disabled_gallery_cannot_authorize(self):
        self.gallery.allow_download = False
        self.gallery.save(update_fields=["allow_download"])
        response = self.authorize()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unpublished_or_unknown_gallery_is_404(self):
        self.gallery.is_published = False
        self.gallery.save(update_fields=["is_published"])
        self.assertEqual(self.authorize().status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.post(
            f"/api/v1/public/{self.username}/no-such-gallery/download-access/",
            {"email": "c@example.com", "pin": PIN}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pin_guessing_is_throttled(self):
        codes = []
        for guess in ("1111", "2222", "3333", "4444", "5555", "6666", "7777"):
            codes.append(self.authorize(pin=guess).status_code)
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[-1], status.HTTP_429_TOO_MANY_REQUESTS)

    def test_gallery_without_pin_still_captures_email_and_issues_a_token(self):
        self.gallery.download_pin_hash = None
        self.gallery.save(update_fields=["download_pin_hash"])
        response = self.client.post(self.access_url, {"email": "c@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data["pin_verified"])

    def test_pin_only_policy_does_not_require_email(self):
        self.gallery.design_settings = {
            'downloads': {'allowed_sizes': ['download', 'web'], 'require_email': False}
        }
        self.gallery.save(update_fields=['design_settings'])
        response = self.client.post(self.access_url, {'pin': PIN}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNone(response.data['email'])


class SinglePhotoDownloadWithTokenTests(DownloadFlowBase):
    def test_disabled_size_cannot_be_bypassed_by_a_direct_url(self):
        self.gallery.design_settings = {
            'downloads': {'allowed_sizes': ['web'], 'require_email': True}
        }
        self.gallery.save(update_fields=['design_settings'])
        token = self.token()
        denied = self.client.get(self.photo_url(self.a1), {'download_token': token, 'resolution': 'download'})
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(denied.data['code'], 'resolution_not_allowed')
        allowed = self.client.get(self.photo_url(self.a1), {'download_token': token, 'resolution': 'web'})
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
    def test_authorized_client_downloads_one_photo_at_each_resolution(self):
        token = self.token()
        expected = {
            "download": (b"MASTER:a1.jpg", DownloadLog.Resolution.DOWNLOAD),
            "web": (b"DISPLAY:a1.jpg", DownloadLog.Resolution.WEB),
            "original": (b"ORIGINAL:a1.jpg", DownloadLog.Resolution.ORIGINAL),
        }
        for resolution, (body, logged) in expected.items():
            response = self.client.get(
                self.photo_url(self.a1), {"download_token": token, "resolution": resolution}
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, resolution)
            self.assertEqual(b"".join(response.streaming_content), body, resolution)
            self.assertIn("attachment", response["Content-Disposition"])
            self.assertEqual(DownloadLog.objects.latest("created_at").resolution, logged)

    def test_default_resolution_is_the_download_master(self):
        token = self.token()
        response = self.client.get(self.photo_url(self.a1), {"download_token": token})
        self.assertEqual(b"".join(response.streaming_content), b"MASTER:a1.jpg")

    def test_activity_row_records_email_scope_resolution_and_pin_state(self):
        token = self.token(email="Lead@Example.com")
        self.client.get(self.photo_url(self.a2), {"download_token": token, "resolution": "web"})
        log = DownloadLog.objects.get()
        self.assertEqual(log.email, "Lead@Example.com")
        self.assertEqual(log.gallery_id, self.gallery.id)
        self.assertEqual(log.media_asset_id, self.a2.id)
        self.assertEqual(log.download_type, DownloadLog.DownloadType.PHOTO)
        self.assertEqual(log.resolution, DownloadLog.Resolution.WEB)
        self.assertTrue(log.pin_verified)
        self.assertIsNotNone(log.created_at)

    def test_one_authorization_is_remembered_across_many_downloads(self):
        token = self.token()
        for asset in (self.a1, self.a2, self.b1):
            response = self.client.get(self.photo_url(asset), {"download_token": token})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        zipped = self.client.get(self.zip_url, {"download_token": token})
        self.assertEqual(zipped.status_code, status.HTTP_200_OK)
        logs = DownloadLog.objects.all()
        self.assertEqual(logs.count(), 4)
        self.assertEqual({log.email for log in logs}, {"client@example.com"})

    def test_token_authorization_does_not_count_against_the_pin_throttle(self):
        token = self.token()
        for _ in range(8):
            response = self.client.get(self.photo_url(self.a1), {"download_token": token})
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_raw_pin_query_still_works_for_scripted_callers_but_is_throttled(self):
        statuses = [
            self.client.get(self.photo_url(self.a1), {"pin": "0000"}).status_code for _ in range(6)
        ]
        self.assertEqual(statuses[:5], [401] * 5)
        self.assertEqual(statuses[5], status.HTTP_429_TOO_MANY_REQUESTS)

    def test_gallery_without_pin_still_requires_email_authorization_by_default(self):
        self.gallery.download_pin_hash = None
        self.gallery.save(update_fields=["download_pin_hash"])
        response = self.client.get(self.photo_url(self.a1))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "download_access_required")
        token = self.token()
        response = self.client.get(self.photo_url(self.a1), {"download_token": token})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(DownloadLog.objects.get().email, "client@example.com")
        self.assertFalse(DownloadLog.objects.get().pin_verified)

    def test_frictionless_download_requires_an_explicit_email_off_setting(self):
        self.gallery.download_pin_hash = None
        self.gallery.design_settings = {
            "downloads": {"allowed_sizes": ["download", "web"], "require_email": False}
        }
        self.gallery.save(update_fields=["download_pin_hash", "design_settings"])
        response = self.client.get(self.photo_url(self.a1))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(DownloadLog.objects.get().email)
        self.assertFalse(DownloadLog.objects.get().pin_verified)


class FullGalleryDownloadWithTokenTests(DownloadFlowBase):
    def test_full_gallery_zip_contains_every_ready_asset_and_logs_scope(self):
        token = self.token()
        response = self.client.get(self.zip_url, {"download_token": token})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/zip")
        entries = _zip_entries(response)
        self.assertEqual(
            entries,
            {"a1.jpg": b"MASTER:a1.jpg", "a2.jpg": b"MASTER:a2.jpg", "b1.jpg": b"MASTER:b1.jpg"},
        )
        log = DownloadLog.objects.get()
        self.assertEqual(log.download_type, DownloadLog.DownloadType.GALLERY)
        self.assertEqual(log.email, "client@example.com")
        self.assertIsNone(log.photo_set)
        self.assertTrue(log.pin_verified)

    def test_set_scoped_zip_contains_only_that_set_and_logs_it(self):
        token = self.token()
        response = self.client.get(
            self.zip_url, {"download_token": token, "set": str(self.ceremony.id)}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(_zip_entries(response)), {"a1.jpg", "a2.jpg"})
        self.assertIn("Ceremony", response["Content-Disposition"])
        self.assertEqual(DownloadLog.objects.get().photo_set_id, self.ceremony.id)

    def test_web_size_zip_uses_display_derivatives_with_matching_extension(self):
        token = self.token()
        response = self.client.get(self.zip_url, {"download_token": token, "resolution": "web"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entries = _zip_entries(response)
        self.assertEqual(set(entries), {"a1.webp", "a2.webp", "b1.webp"})
        self.assertEqual(entries["a1.webp"], b"DISPLAY:a1.jpg")
        self.assertEqual(DownloadLog.objects.get().resolution, DownloadLog.Resolution.WEB)

    def test_high_resolution_zip_serves_the_download_master_not_the_original(self):
        token = self.token()
        response = self.client.get(self.zip_url, {"download_token": token, "resolution": "download"})
        self.assertEqual(_zip_entries(response)["a1.jpg"], b"MASTER:a1.jpg")

    def test_invalid_resolution_is_a_400(self):
        token = self.token()
        response = self.client.get(self.zip_url, {"download_token": token, "resolution": "ultra"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DownloadLog.objects.exists())

    def test_only_ready_assets_are_packaged(self):
        pending = _asset(self.gallery, "pending.jpg", self.party, order=9)
        pending.processing_status = MediaAsset.ProcessingStatus.PENDING
        pending.save(update_fields=["processing_status"])
        token = self.token()
        self.assertNotIn("pending.jpg", _zip_entries(self.client.get(self.zip_url, {"download_token": token})))

    def test_duplicate_and_case_variant_filenames_never_collide(self):
        _asset(self.gallery, "A1.JPG", self.party, order=10)
        _asset(self.gallery, "a1.jpg", self.party, order=11)
        token = self.token()
        names = list(_zip_entries(self.client.get(self.zip_url, {"download_token": token})))
        self.assertEqual(len(names), 5)
        self.assertEqual(len({n.lower() for n in names}), 5)

    def test_hostile_filename_cannot_escape_the_archive(self):
        _asset(self.gallery, "../../etc/passwd.jpg", self.party, order=10)
        token = self.token()
        for name in _zip_entries(self.client.get(self.zip_url, {"download_token": token})):
            self.assertNotIn("..", name)
            self.assertFalse(name.startswith("/"))

    @override_settings(SYNC_ZIP_MAX_ASSET_COUNT=2)
    def test_zip_size_guard_still_applies(self):
        token = self.token()
        response = self.client.get(self.zip_url, {"download_token": token})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "download_too_large")
        self.assertFalse(DownloadLog.objects.exists())

    def test_post_zip_accepts_a_download_token_and_takes_email_from_it(self):
        token = self.token(email="viaToken@example.com")
        response = self.client.post(
            f"{self.base}download/", {"download_token": token, "asset_ids": [str(self.a1.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(_zip_entries(response)), {"a1.jpg"})
        self.assertEqual(DownloadLog.objects.get().email, "viaToken@example.com")


class DirectEndpointCannotBypassTests(DownloadFlowBase):
    def test_no_credentials_on_a_pin_gallery_is_refused_everywhere(self):
        self.assertEqual(self.client.get(self.photo_url(self.a1)).status_code, 401)
        self.assertEqual(self.client.get(self.zip_url).status_code, 403)
        self.assertEqual(
            self.client.post(f"{self.base}download/", {"email": "c@example.com"}, format="json").status_code,
            401,
        )
        self.assertFalse(DownloadLog.objects.exists())

    def test_forged_garbage_and_tampered_tokens_are_rejected(self):
        good = self.token()
        tampered = good[:-3] + ("AAA" if not good.endswith("AAA") else "BBB")
        for bad in ("garbage", "a.b.c", tampered, "x" * 500):
            response = self.client.get(self.photo_url(self.a1), {"download_token": bad})
            self.assertEqual(response.status_code, 401, bad)
            self.assertEqual(response.data["code"], "download_access_expired")
            self.assertEqual(self.client.get(self.zip_url, {"download_token": bad}).status_code, 403)
        self.assertFalse(DownloadLog.objects.exists())

    def test_expired_token_is_rejected_and_asks_the_client_to_reauthorize(self):
        token = self.token()
        with override_settings(DOWNLOAD_ACCESS_TTL_SECONDS=-1):
            response = self.client.get(self.photo_url(self.a1), {"download_token": token})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "download_access_expired")

    def test_changing_the_pin_revokes_outstanding_tokens(self):
        token = self.token()
        self.gallery.download_pin_hash = bcrypt.hashpw(b"9999", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["download_pin_hash"])
        self.assertEqual(self.client.get(self.photo_url(self.a1), {"download_token": token}).status_code, 401)
        self.assertEqual(self.client.get(self.zip_url, {"download_token": token}).status_code, 403)

    def test_a_pin_added_after_an_ungated_token_was_issued_revokes_it(self):
        self.gallery.download_pin_hash = None
        self.gallery.save(update_fields=["download_pin_hash"])
        token = self.client.post(self.access_url, {"email": "c@example.com"}, format="json").data["download_token"]
        self.gallery.download_pin_hash = bcrypt.hashpw(PIN.encode(), bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["download_pin_hash"])
        self.assertEqual(self.client.get(self.photo_url(self.a1), {"download_token": token}).status_code, 401)

    def test_disabling_downloads_blocks_a_previously_issued_token(self):
        token = self.token()
        self.gallery.allow_download = False
        self.gallery.save(update_fields=["allow_download"])
        self.assertEqual(self.client.get(self.photo_url(self.a1), {"download_token": token}).status_code, 403)
        self.assertEqual(self.client.get(self.zip_url, {"download_token": token}).status_code, 403)
        self.assertEqual(
            self.client.post(f"{self.base}download/", {"download_token": token}, format="json").status_code, 403
        )

    def test_unpublishing_blocks_a_previously_issued_token(self):
        token = self.token()
        self.gallery.is_published = False
        self.gallery.save(update_fields=["is_published"])
        self.assertEqual(self.client.get(self.photo_url(self.a1), {"download_token": token}).status_code, 404)
        self.assertEqual(self.client.get(self.zip_url, {"download_token": token}).status_code, 403)

    def test_a_pin_in_the_wrong_place_is_not_accepted(self):
        # PIN in a header/cookie/body-on-GET must not authorize anything.
        response = self.client.get(self.photo_url(self.a1), HTTP_X_DOWNLOAD_PIN=PIN)
        self.assertEqual(response.status_code, 401)


class ForeignGalleryAndAssetTests(DownloadFlowBase):
    def setUp(self):
        super().setUp()
        self.other_user = User.objects.create_user(
            email="other@kyapture.com", password="SecurePassword123!", username="otherphotog",
        )
        self.other = Gallery.objects.create(
            photographer=self.other_user, title="Other", slug="other-gallery",
            is_published=True, is_active=True, allow_download=True,
        )
        self.other.download_pin_hash = bcrypt.hashpw(PIN.encode(), bcrypt.gensalt()).decode()
        self.other.save(update_fields=["download_pin_hash"])
        self.other_set = PhotoSet.objects.create(gallery=self.other, name="Secret", order=1)
        self.other_asset = _asset(self.other, "secret.jpg", self.other_set)
        self.other_base = f"/api/v1/public/{self.other_user.username}/{self.other.slug}/"

    def test_a_token_for_one_gallery_never_authorizes_another_even_with_the_same_pin(self):
        token = self.token()
        photo = self.client.get(self.photo_url(self.other_asset, self.other_base), {"download_token": token})
        self.assertEqual(photo.status_code, 401)
        self.assertEqual(photo.data["code"], "download_access_expired")
        self.assertEqual(self.client.get(f"{self.other_base}download-all/", {"download_token": token}).status_code, 403)

    def test_another_galleries_asset_id_is_404_through_my_url_even_with_a_valid_token(self):
        token = self.token()
        response = self.client.get(self.photo_url(self.other_asset), {"download_token": token})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(DownloadLog.objects.exists())

    def test_another_galleries_asset_id_in_post_zip_selection_is_ignored(self):
        token = self.token()
        response = self.client.post(
            f"{self.base}download/",
            {"download_token": token, "asset_ids": [str(self.other_asset.id)]}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DownloadLog.objects.exists())

    def test_foreign_or_malformed_set_id_is_not_widened_to_the_whole_gallery(self):
        token = self.token()
        for bad in (str(self.other_set.id), "not-a-uuid", "01a0f000-0000-7000-8000-000000000000"):
            response = self.client.get(self.zip_url, {"download_token": token, "set": bad})
            self.assertEqual(response.status_code, 404, bad)
        self.assertFalse(DownloadLog.objects.exists())

    def test_wrong_username_for_a_real_slug_is_404(self):
        token = self.token()
        wrong = f"/api/v1/public/otherphotog/{self.slug}/photo/{self.a1.id}/download/"
        self.assertEqual(self.client.get(wrong, {"download_token": token}).status_code, 404)

    def test_malformed_photo_uuid_never_reaches_the_view(self):
        response = self.client.get(f"{self.base}photo/not-a-uuid/download/", {"download_token": self.token()})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PostZipRobustnessAndErrorShapeTests(DownloadFlowBase):
    with_pin = False

    def test_null_and_non_string_fields_on_a_protected_gallery_are_clean_401s(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["is_password_protected", "password_hash"])
        for token in (None, 123, ["x"], {"a": 1}):
            response = self.client.post(
                f"{self.base}download/", {"email": "c@example.com", "token": token}, format="json"
            )
            self.assertEqual(response.status_code, 401, token)

    def test_non_string_email_is_a_clean_400(self):
        for bad in (None, 42, ["a@b.co"], {"x": 1}):
            response = self.client.post(f"{self.base}download/", {"email": bad}, format="json")
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn(response.data["code"], ("email_required", "invalid_email"), bad)

    def test_malformed_email_on_post_zip_is_rejected(self):
        response = self.client.post(f"{self.base}download/", {"email": "nope"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_email")

    def test_zip_compile_failure_does_not_leak_the_exception(self):
        secret = "boom /srv/private-bucket/keys.txt"
        with mock.patch("apps.clients.views._resolve_zip_source", side_effect=RuntimeError(secret)):
            post = self.client.post(f"{self.base}download/", {"email": "c@example.com"}, format="json")
            direct = self.client.get(self.zip_url)
        for response in (post, direct):
            self.assertEqual(response.status_code, 500)
            self.assertNotIn("private-bucket", str(response.data))
            self.assertNotIn("RuntimeError", str(response.data))
            self.assertIn("error", response.data)
        self.assertFalse(DownloadLog.objects.exists())

    def test_error_bodies_use_error_and_code_keys(self):
        response = self.client.post(self.access_url, {"email": "bad"}, format="json")
        self.assertEqual(set(response.data), {"error", "code"})


class DownloadActivityEndToEndTests(DownloadFlowBase):
    def test_photographer_sees_the_real_rows_the_client_flow_created(self):
        token = self.token(email="buyer@example.com")
        self.client.get(self.photo_url(self.a1), {"download_token": token, "resolution": "web"})
        self.client.get(self.zip_url, {"download_token": token, "set": str(self.ceremony.id)})

        self.client.force_authenticate(user=self.photographer)
        response = self.client.get(f"/api/v1/galleries/{self.slug}/download-logs/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 2)
        rows = {row["download_type"]: row for row in response.data["results"]}

        photo = rows["photo"]
        self.assertEqual(photo["email"], "buyer@example.com")
        self.assertEqual(photo["resolution"], "web")
        self.assertTrue(photo["pin_verified"])
        self.assertEqual(photo["media_asset_id"], str(self.a1.id))
        self.assertEqual(photo["media_asset_title"], "a1.jpg")  # falls back to the filename

        gallery_row = rows["gallery"]
        self.assertEqual(gallery_row["email"], "buyer@example.com")
        self.assertEqual(gallery_row["resolution"], "download")
        self.assertEqual(gallery_row["photo_set_name"], "Ceremony")
        self.assertIsNone(gallery_row["media_asset_id"])
        self.assertTrue(gallery_row["created_at"])

    def test_failed_or_refused_attempts_leave_no_activity_rows(self):
        self.client.get(self.photo_url(self.a1))
        self.client.get(self.zip_url)
        self.authorize(pin="0000")
        self.assertFalse(DownloadLog.objects.exists())
