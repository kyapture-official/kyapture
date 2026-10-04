# backend/apps/clients/tests/test_download_jobs.py
"""
Prepared (background) gallery/set downloads — TASK 1R.2.

  - a job is created only AFTER every gate passes (nothing queued when refused)
  - status endpoint: preparing / ready / failed / expired, stale-preparing, bound
    to the visitor's download token and to the gallery
  - signed file URLs expire, and are rejected for another gallery / job / index
  - the stored ZIP can't be reached any other way (retired direct route, no
    file token, guessed job id, wrong PIN, no session on a protected gallery)
  - ZIP_STORED, filename "{slug}-photo-download-1of1.zip"
  - ONE Download Activity row per job with the real filename; notification text
  - expiry + purge remove the stored ZIP and the row
"""
import io
import zipfile
from datetime import timedelta
from unittest import mock

import bcrypt
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.clients.download_jobs import archive_filename, purge_expired_jobs, run_download_job
from apps.clients.models import ClientSession, DownloadJob, DownloadLog
from apps.clients.tests.zip_flow import InlineDownloadJobsMixin, follow_prepared, request_zip
from apps.core.storage import PrivateMediaStorage
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet
from apps.users.models import Notification

User = get_user_model()
PIN = "4821"


def _asset(gallery, name, photo_set=None, order=0):
    asset = MediaAsset(
        gallery=gallery, media_type=MediaAsset.MediaType.IMAGE, original_name=name, file_size=1024,
        order=order, photo_set=photo_set, processing_status=MediaAsset.ProcessingStatus.READY,
    )
    asset.original_file.save(name, ContentFile(b"ORIGINAL:" + name.encode()), save=False)
    asset.save()
    asset.download_file.save(f"{name}.master.jpg", ContentFile(b"MASTER:" + name.encode()), save=False)
    asset.save(update_fields=["download_file"])
    return asset


class JobBase(InlineDownloadJobsMixin, APITestCase):
    with_pin = True

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(
            email="jobowner@kyapture.com", password="SecurePassword123!", username="jobowner")
        self.gallery = Gallery.objects.create(
            photographer=self.owner, title="Jobs", slug="jobs-gallery",
            is_published=True, is_active=True, allow_download=True)
        if self.with_pin:
            self.gallery.download_pin_hash = bcrypt.hashpw(PIN.encode(), bcrypt.gensalt()).decode()
            self.gallery.save(update_fields=["download_pin_hash"])
        self.set_a = PhotoSet.objects.create(gallery=self.gallery, name="Ceremony", order=1)
        self.a1 = _asset(self.gallery, "a1.jpg", self.set_a, 1)
        self.a2 = _asset(self.gallery, "a2.jpg", self.set_a, 2)
        self.base = f"/api/v1/public/{self.owner.username}/{self.gallery.slug}/"

    def token(self, email="client@example.com", base=None, pin=PIN):
        body = {"email": email}
        if self.with_pin:
            body["pin"] = pin
        response = self.client.post(f"{base or self.base}download-access/", body, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["download_token"]

    def prepare(self, download_token, **body):
        return self.client.post(f"{self.base}download/", {"download_token": download_token, **body}, format="json")

    def status_of(self, job_id, download_token, **params):
        return self.client.get(f"{self.base}download-jobs/{job_id}/", {"download_token": download_token, **params})

    def other_gallery(self):
        other_user = User.objects.create_user(
            email="otherjob@kyapture.com", password="SecurePassword123!", username="otherjobowner")
        other = Gallery.objects.create(
            photographer=other_user, title="Other", slug="other-jobs",
            is_published=True, is_active=True, allow_download=True)
        other.download_pin_hash = self.gallery.download_pin_hash
        other.save(update_fields=["download_pin_hash"])
        _asset(other, "secret.jpg")
        return other, f"/api/v1/public/{other_user.username}/{other.slug}/"


class JobCreatedOnlyAfterAuthorizationTests(JobBase):
    def assert_nothing_queued(self):
        self.assertEqual(DownloadJob.objects.count(), 0)
        self.assertFalse(DownloadLog.objects.exists())

    def test_no_token_creates_no_job(self):
        self.assertEqual(self.client.post(f"{self.base}download/", {}, format="json").status_code, 401)
        self.assert_nothing_queued()

    def test_wrong_pin_never_reaches_the_prepare_step(self):
        response = request_zip(self.client, self.base, {"email": "c@example.com", "pin": "0000"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "invalid_pin")
        self.assert_nothing_queued()

    def test_missing_pin_is_pin_required(self):
        response = request_zip(self.client, self.base, {"email": "c@example.com"})
        self.assertEqual(response.data["code"], "pin_required")
        self.assert_nothing_queued()

    def test_forged_or_expired_token_creates_no_job(self):
        for bad in ("garbage", "a.b.c"):
            self.assertEqual(self.prepare(bad).status_code, 401)
        good = self.token()
        with override_settings(DOWNLOAD_ACCESS_TTL_SECONDS=-1):
            self.assertEqual(self.prepare(good).status_code, 401)
        self.assert_nothing_queued()

    def test_downloads_disabled_or_unpublished_create_no_job(self):
        token = self.token()
        self.gallery.allow_download = False
        self.gallery.save(update_fields=["allow_download"])
        self.assertEqual(self.prepare(token).status_code, 403)
        self.gallery.allow_download = True
        self.gallery.is_published = False
        self.gallery.save(update_fields=["allow_download", "is_published"])
        self.assertEqual(self.prepare(token).status_code, 404)
        self.assert_nothing_queued()

    def test_protected_gallery_needs_its_unlock_session_to_prepare(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["is_password_protected", "password_hash"])
        session = ClientSession.objects.create(gallery=self.gallery, email="c@example.com")
        grant = self.client.post(
            f"{self.base}download-access/", {"email": "c@example.com", "pin": PIN}, format="json",
            HTTP_AUTHORIZATION=f"Bearer {session.access_token}")
        token = grant.data["download_token"]
        self.assertEqual(self.prepare(token).status_code, 401)           # token alone is not a session
        self.assert_nothing_queued()
        self.assertEqual(self.prepare(token, token=session.access_token).status_code, 202)

    def test_an_authorized_request_creates_exactly_one_job_and_202(self):
        token = self.token()
        response = self.prepare(token)
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(set(response.data), {"job_id", "link_token", "state", "status_url"})
        self.assertEqual(DownloadJob.objects.count(), 1)
        job = DownloadJob.objects.get()
        self.assertEqual((job.gallery_id, job.email, job.pin_verified), (self.gallery.id, "client@example.com", True))
        self.assertFalse(DownloadLog.objects.exists())                   # nothing is "downloaded" yet

    def test_identical_requests_reuse_the_job(self):
        token = self.token()
        first = self.prepare(token).data["job_id"]
        cache.clear()
        second = self.prepare(token).data["job_id"]
        self.assertEqual(first, second)
        self.assertEqual(DownloadJob.objects.count(), 1)

    def test_a_foreign_or_malformed_set_is_refused_not_widened(self):
        token = self.token()
        other, _ = self.other_gallery()
        other_set = PhotoSet.objects.create(gallery=other, name="Secret", order=1)
        for bad in (str(other_set.id), "not-a-uuid"):
            self.assertEqual(self.prepare(token, set_id=bad).status_code, 404)
        self.assertEqual(DownloadJob.objects.count(), 0)

    def test_queue_outage_is_a_clean_503_with_a_failed_job(self):
        token = self.token()
        with mock.patch("apps.clients.views.prepare_download_job.delay", side_effect=ConnectionError("redis down")):
            response = self.prepare(token)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "prepare_unavailable")
        self.assertNotIn("redis", str(response.data))
        self.assertEqual(DownloadJob.objects.get().state, "failed")


class JobStatusTests(JobBase):
    def test_preparing_then_ready_with_name_size_and_signed_url(self):
        token = self.token()
        with mock.patch("apps.clients.views.prepare_download_job.delay"):    # task not run: still preparing
            job_id = self.prepare(token).data["job_id"]
        waiting = self.status_of(job_id, token)
        self.assertEqual(waiting.status_code, 200)
        self.assertEqual(waiting.data, {"state": "preparing", "files": [], "will_email": True})

        run_download_job(job_id)
        ready = self.status_of(job_id, token)
        self.assertEqual(ready.data["state"], "ready")
        (entry,) = ready.data["files"]
        self.assertEqual(set(entry), {"name", "size_bytes", "url"})
        self.assertEqual(entry["name"], "jobs-gallery-photo-download-1of1.zip")
        self.assertGreater(entry["size_bytes"], 0)
        self.assertIn("file_token=", entry["url"])
        self.assertNotIn("storage_path", str(ready.data))
        self.assertNotIn("download_jobs/", str(ready.data))               # never a private storage key

    def test_a_job_with_nothing_to_package_fails_with_a_clear_code(self):
        MediaAsset.objects.filter(gallery=self.gallery).update(processing_status="pending")
        token = self.token()
        # nothing READY -> refused up front
        response = self.prepare(token)
        self.assertEqual((response.status_code, response.data["code"]), (400, "no_media"))

    def test_worker_failure_reads_as_failed_without_leaking_details(self):
        token = self.token()
        with mock.patch("apps.clients.views._resolve_zip_source", side_effect=RuntimeError("/srv/secret/bucket")):
            job_id = self.prepare(token).data["job_id"]
        failed = self.status_of(job_id, token)
        self.assertEqual(failed.data["state"], "failed")
        self.assertEqual(failed.data["files"], [])
        self.assertNotIn("secret", str(failed.data))
        self.assertFalse(DownloadLog.objects.exists())

    def test_stale_preparing_job_becomes_failed(self):
        token = self.token()
        with mock.patch("apps.clients.views.prepare_download_job.delay"):
            job_id = self.prepare(token).data["job_id"]
        DownloadJob.objects.filter(pk=job_id).update(created_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(self.status_of(job_id, token).data["state"], "failed")

    def test_expired_ready_job_reads_as_expired(self):
        token = self.token()
        job_id = self.prepare(token).data["job_id"]
        DownloadJob.objects.filter(pk=job_id).update(expires_at=timezone.now() - timedelta(seconds=1))
        body = self.status_of(job_id, token).data
        self.assertEqual((body["state"], body["code"]), ("failed", "download_expired"))

    def test_status_requires_a_valid_download_token(self):
        token = self.token()
        job_id = self.prepare(token).data["job_id"]
        self.assertEqual(self.client.get(f"{self.base}download-jobs/{job_id}/").status_code, 401)
        self.assertEqual(self.status_of(job_id, "garbage").status_code, 401)

    def test_another_visitors_token_cannot_read_my_job(self):
        mine = self.token(email="mine@example.com")
        job_id = self.prepare(mine).data["job_id"]
        theirs = self.token(email="theirs@example.com")
        self.assertEqual(self.status_of(job_id, theirs).status_code, 404)

    def test_another_gallerys_token_and_url_cannot_read_my_job(self):
        token = self.token()
        job_id = self.prepare(token).data["job_id"]
        other, other_base = self.other_gallery()
        other_token = self.token(base=other_base)
        # my job id under THEIR gallery URL: not found (job is bound to its gallery)
        self.assertEqual(self.client.get(f"{other_base}download-jobs/{job_id}/", {"download_token": other_token}).status_code, 404)
        self.assertEqual(self.client.get(f"{other_base}download-jobs/{job_id}/", {"download_token": token}).status_code, 404)
        # their token under MY gallery: refused by the token's own gallery binding
        self.assertEqual(self.status_of(job_id, other_token).status_code, 401)

    def test_unknown_job_id_is_404(self):
        token = self.token()
        self.assertEqual(self.status_of("01a0f000-0000-7000-8000-000000000000", token).status_code, 404)


class SignedFileUrlTests(JobBase):
    def ready(self):
        token = self.token()
        job_id = self.prepare(token).data["job_id"]
        status_response = self.status_of(job_id, token)
        self.assertEqual(status_response.data["state"], "ready")
        return token, job_id, status_response.data["files"][0]["url"]

    def test_the_url_downloads_the_zip_as_an_attachment(self):
        _, _, url = self.ready()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="jobs-gallery-photo-download-1of1.zip"')
        with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(sorted(archive.namelist()), ["a1.jpg", "a2.jpg"])
            self.assertEqual(archive.read("a1.jpg"), b"MASTER:a1.jpg")

    def test_zip_is_stored_not_deflated(self):
        _, _, url = self.ready()
        with zipfile.ZipFile(io.BytesIO(b"".join(self.client.get(url).streaming_content))) as archive:
            self.assertTrue(all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist()))

    def test_the_url_expires(self):
        _, _, url = self.ready()
        with override_settings(DOWNLOAD_FILE_URL_TTL_SECONDS=-1):
            response = self.client.get(url)
        self.assertEqual((response.status_code, response.data["code"]), (403, "download_link_expired"))
        self.assertFalse(DownloadLog.objects.exists())

    def test_without_a_file_token_or_with_a_tampered_one_nothing_is_served(self):
        _, job_id, url = self.ready()
        bare = url.split("?")[0]
        self.assertEqual(self.client.get(bare).status_code, 403)
        tampered = url[:-3] + ("AAA" if not url.endswith("AAA") else "BBB")
        self.assertEqual(self.client.get(tampered).status_code, 403)
        self.assertFalse(DownloadLog.objects.exists())

    def test_the_token_is_bound_to_its_job_gallery_and_file_index(self):
        _, job_id, url = self.ready()
        file_token = url.split("file_token=")[1]
        # another job of the same gallery
        other_job = DownloadJob.objects.create(
            gallery=self.gallery, resolution="web", email="client@example.com", state="ready",
            files=DownloadJob.objects.get(pk=job_id).files, expires_at=timezone.now() + timedelta(hours=1))
        self.assertEqual(self.client.get(f"{self.base}download-jobs/{other_job.id}/files/0/?file_token={file_token}").status_code, 404)
        # a file index that doesn't exist
        self.assertEqual(self.client.get(f"{self.base}download-jobs/{job_id}/files/1/?file_token={file_token}").status_code, 404)
        # the same token on another gallery
        other, other_base = self.other_gallery()
        self.assertEqual(self.client.get(f"{other_base}download-jobs/{job_id}/files/0/?file_token={file_token}").status_code, 404)

    def test_changing_the_pin_invalidates_an_outstanding_url(self):
        _, _, url = self.ready()
        self.gallery.download_pin_hash = bcrypt.hashpw(b"9999", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["download_pin_hash"])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_disabling_downloads_blocks_an_outstanding_url(self):
        _, _, url = self.ready()
        self.gallery.allow_download = False
        self.gallery.save(update_fields=["allow_download"])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_protected_gallery_file_needs_the_unlock_session_too(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["is_password_protected", "password_hash"])
        session = ClientSession.objects.create(gallery=self.gallery, email="client@example.com")
        grant = self.client.post(f"{self.base}download-access/", {"email": "client@example.com", "pin": PIN},
                                 format="json", HTTP_AUTHORIZATION=f"Bearer {session.access_token}")
        token = grant.data["download_token"]
        job_id = self.prepare(token, token=session.access_token).data["job_id"]
        listed = self.status_of(job_id, token, token=session.access_token)
        url = listed.data["files"][0]["url"]
        self.assertEqual(self.client.get(url).status_code, 401)                       # link alone: no session
        self.assertEqual(self.client.get(f"{url}&token={session.access_token}").status_code, 200)

    def test_expired_job_is_gone(self):
        _, job_id, url = self.ready()
        DownloadJob.objects.filter(pk=job_id).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(url).status_code, 410)


class ReadyLinkLifetimeTests(JobBase):
    """A ready download keeps working until it expires (7 days) - the 1R.3 regression."""

    def ready(self):
        token = self.token()
        job_id = self.prepare(token).data["job_id"]
        job = DownloadJob.objects.get(pk=job_id)
        return token, job, self.status_of(job_id, token).data["files"][0]["url"]

    def test_a_ready_job_lives_for_7_days_and_its_stored_file_exists(self):
        _, job, _ = self.ready()
        lifetime = (job.expires_at - job.created_at).total_seconds()
        self.assertAlmostEqual(lifetime, 7 * 24 * 3600, delta=120)
        self.assertTrue(PrivateMediaStorage().exists(job.files[0]["storage_path"]))

    def test_the_link_downloads_repeatedly_not_just_once(self):
        _, _, url = self.ready()
        for _ in range(3):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertGreater(len(b"".join(response.streaming_content)), 100)

    def test_the_signed_link_is_still_good_6_days_later_and_dead_after_the_job_expires(self):
        _, job, url = self.ready()
        import time as _time
        now = _time.time()
        with mock.patch("django.core.signing.time.time", return_value=now + 6 * 24 * 3600):
            self.assertEqual(self.client.get(url).status_code, 200)
        DownloadJob.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(url).status_code, 410)

    def test_a_token_for_another_job_is_a_404_never_a_download(self):
        token, job, url = self.ready()
        other = DownloadJob.objects.create(
            gallery=self.gallery, resolution="web", email="client@example.com", state="ready",
            files=job.files, expires_at=timezone.now() + timedelta(hours=1))
        file_token = url.split("file_token=")[1]
        response = self.client.get(f"{self.base}download-jobs/{other.id}/files/0/?file_token={file_token}")
        self.assertEqual((response.status_code, response.data["code"]), (404, "download_not_found"))

    def test_expired_link_opened_in_a_browser_goes_to_a_friendly_page_not_raw_json(self):
        _, job, url = self.ready()
        DownloadJob.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.get(url, HTTP_ACCEPT="text/html,application/xhtml+xml")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith(f"/g/{self.owner.username}/{self.gallery.slug}/download?link=expired"))
        self.assertFalse(DownloadLog.objects.exists())
        # API callers still get the machine-readable error
        api = self.client.get(url)
        self.assertEqual((api.status_code, api.data["code"]), (410, "download_expired"))

    def test_an_expired_signed_link_is_friendly_in_a_browser_too(self):
        _, _, url = self.ready()
        with override_settings(DOWNLOAD_FILE_URL_TTL_SECONDS=-1):
            response = self.client.get(url, HTTP_ACCEPT="text/html")
        self.assertEqual(response.status_code, 302)
        self.assertIn("link=expired", response["Location"])

    def test_a_tampered_or_missing_token_is_still_refused_with_no_file(self):
        _, _, url = self.ready()
        for bad in (url.split("?")[0], url[:-3] + "AAA"):
            response = self.client.get(bad)
            self.assertEqual(response.status_code, 403)
            self.assertFalse(hasattr(response, "streaming_content"))

    def test_a_vanished_file_is_reported_as_unavailable_not_as_ready(self):
        token, job, url = self.ready()
        PrivateMediaStorage().delete(job.files[0]["storage_path"])
        listed = self.status_of(job.id, token)
        self.assertEqual((listed.data["state"], listed.data["code"]), ("failed", "file_missing"))
        self.assertEqual(listed.data["files"], [])
        self.assertIn("prepare it again", listed.data["error"])

    def test_the_file_endpoint_notices_a_vanished_file_and_stops_claiming_ready(self):
        _, job, url = self.ready()
        PrivateMediaStorage().delete(job.files[0]["storage_path"])
        response = self.client.get(url)
        self.assertEqual((response.status_code, response.data["code"]), (404, "file_unavailable"))
        self.assertEqual(DownloadJob.objects.get(pk=job.pk).state, "failed")
        browser = self.client.get(url, HTTP_ACCEPT="text/html")
        self.assertEqual(browser.status_code, 302)             # job is no longer ready -> friendly page, never a raw 404
        self.assertIn("link=expired", browser["Location"])

    def test_a_pin_change_after_the_link_was_issued_still_blocks_it(self):
        _, _, url = self.ready()
        self.gallery.download_pin_hash = bcrypt.hashpw(b"9999", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["download_pin_hash"])
        self.assertEqual(self.client.get(url).status_code, 403)


class TestsNeverTouchDevMediaTests(JobBase):
    def test_this_class_runs_in_a_throwaway_media_root(self):
        from django.conf import settings as dj
        self.assertIn("kyapture-test-media-", dj.MEDIA_ROOT)
        token = self.token()
        job = DownloadJob.objects.get(pk=self.prepare(token).data["job_id"])
        stored = PrivateMediaStorage().path(job.files[0]["storage_path"])
        self.assertIn("kyapture-test-media-", stored)


class NoOtherRouteToTheFileTests(JobBase):
    def test_the_old_direct_streaming_route_is_gone(self):
        token = self.token()
        response = self.client.get(f"{self.base}download-all/", {"download_token": token})
        self.assertEqual((response.status_code, response.data["code"]), (410, "download_requires_preparation"))
        self.assertFalse(DownloadLog.objects.exists())
        self.assertFalse(hasattr(response, "streaming_content"))

    def test_guessing_a_job_id_without_credentials_gets_nothing(self):
        token = self.token()
        job_id = self.prepare(token).data["job_id"]
        self.assertEqual(self.client.get(f"{self.base}download-jobs/{job_id}/").status_code, 401)
        self.assertEqual(self.client.get(f"{self.base}download-jobs/{job_id}/files/0/").status_code, 403)

    def test_stored_zip_is_not_under_a_public_media_url(self):
        token = self.token()
        job = DownloadJob.objects.get(pk=self.prepare(token).data["job_id"])
        path = job.files[0]["storage_path"]
        self.assertTrue(path.startswith("download_jobs/"))
        self.assertNotIn(path, str(self.status_of(job.id, token).data))


class FilenameTests(JobBase):
    def test_archive_filename_format(self):
        self.assertEqual(archive_filename(self.gallery), "jobs-gallery-photo-download-1of1.zip")
        self.assertEqual(archive_filename(self.gallery, 2, 3), "jobs-gallery-photo-download-2of3.zip")

    def test_set_and_gallery_downloads_share_the_format(self):
        token = self.token()
        for body in ({}, {"set_id": str(self.set_a.id)}):
            cache.clear()
            job_id = self.prepare(token, **body).data["job_id"]
            self.assertEqual(self.status_of(job_id, token).data["files"][0]["name"], "jobs-gallery-photo-download-1of1.zip")


class ActivityAndNotificationTests(JobBase):
    def test_one_activity_row_per_job_with_the_real_filename(self):
        token = self.token(email="buyer@example.com")
        response = request_zip(self.client, self.base, {"download_token": token, "set_id": str(self.set_a.id), "resolution": "web"})
        self.assertEqual(response.status_code, 200)
        log = DownloadLog.objects.get()
        self.assertEqual(
            (log.email, log.download_type, log.resolution, log.pin_verified, log.photo_set_id, log.filename),
            ("buyer@example.com", "gallery", "web", True, self.set_a.id, "jobs-gallery-photo-download-1of1.zip"))
        # the browser retrying / resuming the very same file seconds later is not a second download ...
        job = DownloadJob.objects.get()
        again = self.status_of(job.id, token)
        self.client.get(again.data["files"][0]["url"])
        self.assertEqual(DownloadLog.objects.count(), 1)
        self.assertEqual(DownloadJob.objects.get().download_log_id, DownloadLog.objects.get().id)
        # ... but a genuine "Download again" later is its own activity row
        DownloadLog.objects.update(created_at=timezone.now() - timedelta(minutes=5))
        self.client.get(self.status_of(job.id, token).data["files"][0]["url"])
        self.assertEqual(DownloadLog.objects.count(), 2)
        DownloadLog.objects.filter(created_at__lt=timezone.now() - timedelta(minutes=1)).delete()

        self.client.force_authenticate(user=self.owner)
        row = self.client.get(f"/api/v1/galleries/{self.gallery.slug}/download-logs/").data["results"][0]
        self.assertEqual(row["filename"], "jobs-gallery-photo-download-1of1.zip")
        self.assertEqual((row["email"], row["photo_set_name"], row["resolution"], row["pin_state"]),
                         ("buyer@example.com", "Ceremony", "web", "verified"))

    def test_the_retry_window_only_collapses_the_same_job(self):
        # Three DIFFERENT jobs started back-to-back are three rows: other email, other set, other size.
        a_token = self.token(email="a@example.com")
        b_token = self.token(email="b@example.com")
        for body in (
            {"download_token": a_token},
            {"download_token": b_token},                                          # other email
            {"download_token": a_token, "set_id": str(self.set_a.id)},            # other set
            {"download_token": a_token, "resolution": "web"},                     # other size
        ):
            cache.clear()                                                         # the 5/min PIN throttle is not under test
            request_zip(self.client, self.base, body)
        self.assertEqual(DownloadLog.objects.count(), 4)
        self.assertEqual(DownloadJob.objects.count(), 4)
        # ... while repeating one of them within the window is still a single download
        job = DownloadJob.objects.get(email="b@example.com")
        self.client.get(self.status_of(job.id, b_token).data["files"][0]["url"])
        self.assertEqual(DownloadLog.objects.count(), 4)

    def test_the_stored_filename_is_not_re_derived(self):
        token = self.token()
        request_zip(self.client, self.base, {"download_token": token})
        Gallery.objects.filter(pk=self.gallery.pk).update(slug="renamed-later")
        self.client.force_authenticate(user=self.owner)
        row = self.client.get("/api/v1/galleries/renamed-later/download-logs/").data["results"][0]
        self.assertEqual(row["filename"], "jobs-gallery-photo-download-1of1.zip")

    def test_single_photo_log_stores_the_real_attachment_name(self):
        token = self.token(email="buyer@example.com")
        response = self.client.get(f"{self.base}photo/{self.a1.id}/download/", {"download_token": token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DownloadLog.objects.get().filename, "a1.jpg")

    def test_a_refused_or_failed_job_never_writes_a_row(self):
        token = self.token()
        with mock.patch("apps.clients.views._resolve_zip_source", side_effect=RuntimeError("x")):
            self.prepare(token)
        self.assertFalse(DownloadLog.objects.exists())

    def test_notification_text_for_a_gallery_download(self):
        token = self.token(email="buyer@example.com")
        request_zip(self.client, self.base, {"download_token": token})
        self.assertEqual(Notification.objects.get(user=self.owner, kind="download").message,
                         "Gallery downloaded by buyer@example.com")

    def test_notification_text_for_a_photo_download(self):
        token = self.token(email="buyer@example.com")
        self.client.get(f"{self.base}photo/{self.a1.id}/download/", {"download_token": token})
        self.assertEqual(Notification.objects.get(user=self.owner, kind="download").message,
                         "Photo downloaded by buyer@example.com")

    def test_no_notification_until_the_file_is_actually_downloaded(self):
        token = self.token(email="buyer@example.com")
        self.prepare(token)                                      # prepared, not yet fetched
        self.assertFalse(Notification.objects.filter(kind="download").exists())


class CleanupTests(JobBase):
    def stored_path(self, job):
        return PrivateMediaStorage().path(job.files[0]["storage_path"])

    def test_purge_removes_expired_jobs_and_their_stored_zip_but_keeps_live_ones(self):
        token = self.token()
        expired = DownloadJob.objects.get(pk=self.prepare(token).data["job_id"])
        live = DownloadJob.objects.create(
            gallery=self.gallery, resolution="web", email="client@example.com", state="ready",
            files=[], expires_at=timezone.now() + timedelta(hours=1))
        path = self.stored_path(expired)
        import os
        self.assertTrue(os.path.exists(path))
        DownloadJob.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

        self.assertEqual(purge_expired_jobs(), 1)
        self.assertFalse(os.path.exists(path))
        self.assertFalse(os.path.exists(os.path.dirname(path)))           # no empty per-job directory left
        self.assertFalse(DownloadJob.objects.filter(pk=expired.pk).exists())
        self.assertTrue(DownloadJob.objects.filter(pk=live.pk).exists())

    def test_purge_removes_abandoned_unfinished_jobs(self):
        token = self.token()
        with mock.patch("apps.clients.views.prepare_download_job.delay"):
            job_id = self.prepare(token).data["job_id"]
        DownloadJob.objects.filter(pk=job_id).update(created_at=timezone.now() - timedelta(days=2))
        self.assertEqual(purge_expired_jobs(), 1)

    def test_purge_task_is_scheduled_daily(self):
        from config.celery import app
        entry = app.conf.beat_schedule["purge-expired-download-jobs"]
        self.assertEqual(entry["task"], "apps.clients.tasks.purge_expired_download_jobs")
        self.assertEqual((entry["schedule"]._orig_hour, entry["schedule"]._orig_minute), (3, 45))
        self.assertEqual(entry["schedule"]._orig_day_of_week, "*")        # every day, not weekly/hourly

    def test_failed_run_leaves_no_temp_zip_behind(self):
        token = self.token()
        import tempfile, glob, os
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.zip")))
        with mock.patch("apps.clients.views._resolve_zip_source", side_effect=RuntimeError("x")):
            self.prepare(token)
        self.assertEqual(set(glob.glob(os.path.join(tempfile.gettempdir(), "*.zip"))), before)

    def test_running_a_job_twice_is_harmless(self):
        token = self.token()
        job_id = self.prepare(token).data["job_id"]
        self.assertEqual(run_download_job(job_id), "ready")
        before = DownloadJob.objects.get(pk=job_id).files
        self.assertEqual(run_download_job(job_id), "ready")
        self.assertEqual(DownloadJob.objects.get(pk=job_id).files, before)


class ReadyEmailTests(JobBase):
    def test_the_visitor_is_emailed_a_link_back_to_the_download_page(self):
        token = self.token(email="buyer@example.com")
        self.prepare(token)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["buyer@example.com"])
        job = DownloadJob.objects.get()
        self.assertIn(f"/g/{self.owner.username}/{self.gallery.slug}/download/file/{job.id}?key=", message.body)
        self.assertNotIn("file_token", message.body)                 # the mail carries no credential

    def test_no_email_when_none_was_captured(self):
        self.gallery.download_pin_hash = None
        self.gallery.design_settings = {"downloads": {"require_email": False}}
        self.gallery.save(update_fields=["download_pin_hash", "design_settings"])
        response = request_zip(self.client, self.base)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(DownloadLog.objects.get().email)
