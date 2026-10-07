# backend/apps/clients/tests/test_ready_link_protected_1r5e.py
"""
Task 1R.5-E -- the emailed "ready" link on a password-protected gallery.

The visitor passed the gallery password AND the PIN/email check when the job was
created, so the signed link (/download/file/{job}?key=...) and the file links
minted from it must work from the link alone -- in a fresh browser, with no
unlock session -- while exposing only that job's files. Nothing upstream relaxes:
creating a job still needs the unlock session plus the PIN/email, and a forged,
expired or other-gallery key is refused.
"""
import os
import re
from datetime import timedelta
from importlib import import_module
from unittest import mock

import bcrypt
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.clients.download_jobs import send_ready_email
from apps.clients.models import DownloadJob
from apps.clients.ready_email import deliver_ready_email
from apps.clients.tests.test_download_access_flow import PIN, _zip_entries, complete_email_code
from apps.clients.tests.test_download_pages_1r5b import JobBase
from apps.galleries.models import Gallery

APP = 'https://app.example.test'


class ProtectedGalleryBase(JobBase):
    def setUp(self):
        super().setUp()
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'gallerypass', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])
        cache.clear()
        unlock = self.client.post(f'{self.base}unlock/', {'password': 'gallerypass'}, format='json')
        self.assertEqual(unlock.status_code, 200, unlock.data)
        self.unlock_token = unlock.data['access_token']

    def make_job(self, email='client@example.com', **body):
        """The honest path: unlock session + PIN/email -> download-access -> prepare."""
        cache.clear()
        auth = {'HTTP_AUTHORIZATION': f'Bearer {self.unlock_token}'}
        access = complete_email_code(
            self.client, f'{self.base}download-access/', {'email': email, 'pin': PIN},
            self.client.post(f'{self.base}download-access/', {'email': email, 'pin': PIN}, format='json', **auth),
            **auth,
        )
        self.assertEqual(access.status_code, 200, access.data)
        response = self.client.post(
            f'{self.base}download/',
            {'download_token': access.data['download_token'], 'token': self.unlock_token, **body}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, getattr(response, 'data', None))
        return DownloadJob.objects.get(pk=response.data['job_id']), response.data['link_token']

    def fresh(self):
        """A brand-new browser: no cookies, no unlock session, no download token."""
        cache.clear()
        return APIClient()

    def status_url(self, job):
        return f'{self.base}download-jobs/{job.id}/'


class SignedLinkWorksWithoutUnlockTests(ProtectedGalleryBase):
    def test_ready_page_and_zip_open_from_the_key_alone(self):
        job, key = self.make_job()
        browser = self.fresh()
        ready = browser.get(self.status_url(job), {'link_token': key})
        self.assertEqual(ready.status_code, status.HTTP_200_OK, ready.data)
        self.assertEqual(ready.data['state'], 'ready')
        self.assertEqual(ready.data['files'][0]['name'], 'flow-gallery-photo-download-1of1.zip')
        zipped = browser.get(ready.data['files'][0]['url'])
        self.assertEqual(zipped.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_zip_entries(zipped)), 3)

    def test_the_response_exposes_only_the_jobs_files_and_a_header(self):
        job, key = self.make_job()
        ready = self.fresh().get(self.status_url(job), {'link_token': key})
        self.assertEqual(
            set(ready.data), {'state', 'files', 'expires_at', 'will_email', 'gallery_title', 'studio'})
        self.assertEqual(ready.data['gallery_title'], 'Flow')
        flat = repr(ready.data)
        for private in ('photos', 'photo_sets', 'allowed_emails', 'client@example.com', PIN):
            self.assertNotIn(private, flat)
        # the gallery itself is still locked for that same browser
        browser = self.fresh()
        self.assertTrue(browser.get(self.base).data.get('requires_password'))
        self.assertEqual(browser.get(f'{self.base}photos/').status_code, status.HTTP_401_UNAUTHORIZED)

    def test_without_the_key_or_a_session_the_job_is_still_locked(self):
        job, key = self.make_job()
        denied = self.fresh().get(self.status_url(job))
        self.assertEqual((denied.status_code, denied.data['code']), (401, 'session_required'))
        file_url = self.fresh().get(self.status_url(job), {'link_token': key}).data['files'][0]['url']
        denied_file = self.fresh().get(file_url.split('?')[0])
        self.assertEqual((denied_file.status_code, denied_file.data['code']), (401, 'session_required'))

    def test_the_emailed_link_carries_a_key_that_works(self):
        with override_settings(FRONTEND_URL=APP):
            job, _ = self.make_job(email='mailed@example.com')
        match = re.search(rf'/download/file/{job.id}\?key=(\S+)', mail.outbox[-1].body)
        self.assertIsNotNone(match)
        opened = self.fresh().get(self.status_url(job), {'link_token': match.group(1)})
        self.assertEqual(opened.status_code, 200, opened.data)


class RefusedKeysTests(ProtectedGalleryBase):
    def test_forged_and_empty_keys_read_as_not_found(self):
        job, key = self.make_job()
        for bad in ('', 'garbage', key[:-3] + 'abc'):
            denied = self.fresh().get(self.status_url(job), {'link_token': bad})
            self.assertEqual((denied.status_code, denied.data['code']), (404, 'download_not_found'), bad)

    def test_another_jobs_key_is_refused(self):
        job_a, key_a = self.make_job(resolution='download')
        job_b, key_b = self.make_job(resolution='web', email='other@example.com')
        denied = self.fresh().get(self.status_url(job_b), {'link_token': key_a})
        self.assertEqual((denied.status_code, denied.data['code']), (404, 'download_not_found'))
        self.assertEqual(self.fresh().get(self.status_url(job_b), {'link_token': key_b}).status_code, 200)

    def test_another_galleries_key_is_refused(self):
        job, key = self.make_job()
        other = Gallery.objects.create(
            photographer=self.photographer, title='Other', slug='other-gallery', is_published=True,
            is_active=True, allow_download=True, is_password_protected=True,
            password_hash=bcrypt.hashpw(b'x', bcrypt.gensalt()).decode(),
        )
        moved = DownloadJob.objects.create(
            gallery=other, resolution=job.resolution, email=job.email, state='ready',
            files=job.files, expires_at=job.expires_at,
        )
        denied = self.fresh().get(
            f'/api/v1/public/{self.username}/other-gallery/download-jobs/{moved.id}/', {'link_token': key})
        self.assertEqual((denied.status_code, denied.data['code']), (404, 'download_not_found'))

    def test_a_forged_or_other_job_file_link_is_refused(self):
        job, key = self.make_job()
        other_job, _ = self.make_job(resolution='web', email='other@example.com')
        url = self.fresh().get(self.status_url(job), {'link_token': key}).data['files'][0]['url']
        file_token = url.split('file_token=')[1]
        forged = self.fresh().get(f'{self.base}download-jobs/{job.id}/files/0/', {'file_token': file_token[:-3] + 'abc'})
        self.assertEqual((forged.status_code, forged.data['code']), (404, 'download_not_found'))
        crossed = self.fresh().get(f'{self.base}download-jobs/{other_job.id}/files/0/', {'file_token': file_token})
        self.assertEqual((crossed.status_code, crossed.data['code']), (404, 'download_not_found'))

    def test_a_browser_sent_a_dead_link_lands_on_the_friendly_expired_page(self):
        job, _ = self.make_job()
        bad = self.fresh().get(
            f'{self.base}download-jobs/{job.id}/files/0/', {'file_token': 'garbage'}, HTTP_ACCEPT='text/html')
        self.assertEqual(bad.status_code, 302)
        self.assertTrue(bad['Location'].endswith(f'/g/{self.username}/{self.slug}/download?link=expired'))

    def test_an_expired_file_link_and_an_expired_job(self):
        job, key = self.make_job()
        url = self.fresh().get(self.status_url(job), {'link_token': key}).data['files'][0]['url']
        with override_settings(DOWNLOAD_FILE_URL_TTL_SECONDS=-1):
            gone = self.fresh().get(url)
        self.assertEqual((gone.status_code, gone.data['code']), (403, 'download_link_expired'))
        DownloadJob.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        expired = self.fresh().get(self.status_url(job), {'link_token': key})
        self.assertEqual((expired.data['state'], expired.data['code']), ('failed', 'download_expired'))
        self.assertEqual(self.fresh().get(url).status_code, status.HTTP_410_GONE)

    def test_downloads_switched_off_still_refuses_the_key(self):
        job, key = self.make_job()
        Gallery.objects.filter(pk=self.gallery.pk).update(allow_download=False)
        denied = self.fresh().get(self.status_url(job), {'link_token': key})
        self.assertEqual((denied.status_code, denied.data['code']), (403, 'downloads_disabled'))


class NothingUpstreamIsRelaxedTests(ProtectedGalleryBase):
    def test_both_gates_are_asked_when_both_are_on(self):
        # the password first, on gallery entry
        self.assertTrue(self.fresh().get(self.base).data.get('requires_password'))
        opened = self.client.get(self.base, HTTP_AUTHORIZATION=f'Bearer {self.unlock_token}')
        self.assertTrue(opened.data['has_download_pin'])
        # the PIN second, at download: an unlock session alone does not start a job
        prepared = self.client.post(f'{self.base}download/', {'token': self.unlock_token}, format='json')
        self.assertEqual((prepared.status_code, prepared.data['code']), (401, 'download_access_required'))
        wrong_pin = self.client.post(
            f'{self.base}download-access/', {'email': 'c@example.com', 'pin': '0000'}, format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.unlock_token}')
        self.assertEqual(wrong_pin.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_job_creation_still_needs_the_unlock_session(self):
        access = self.client.post(
            f'{self.base}download-access/', {'email': 'c@example.com', 'pin': PIN}, format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.unlock_token}')
        no_session = self.fresh().post(
            f'{self.base}download/', {'download_token': access.data['download_token']}, format='json')
        self.assertEqual(no_session.status_code, status.HTTP_401_UNAUTHORIZED)
        no_access_either = self.fresh().post(
            f'{self.base}download-access/', {'email': 'c@example.com', 'pin': PIN}, format='json')
        self.assertEqual((no_access_either.status_code, no_access_either.data['code']), (401, 'session_required'))
        self.assertEqual(DownloadJob.objects.count(), 0)

    def test_a_key_does_not_create_jobs(self):
        _, key = self.make_job()
        before = DownloadJob.objects.count()
        denied = self.fresh().post(f'{self.base}download/', {'link_token': key}, format='json')
        self.assertEqual(denied.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(DownloadJob.objects.count(), before)

    def test_a_removed_contact_loses_the_file_link(self):
        design = {'downloads': {'restrict_contacts': True, 'allowed_emails': ['client@example.com']}}
        Gallery.objects.filter(pk=self.gallery.pk).update(design_settings=design)
        job, key = self.make_job()
        url = self.fresh().get(self.status_url(job), {'link_token': key}).data['files'][0]['url']
        design['downloads']['allowed_emails'] = ['someone-else@example.com']
        Gallery.objects.filter(pk=self.gallery.pk).update(design_settings=design)
        self.assertGreaterEqual(self.fresh().get(url).status_code, 400)


@override_settings(FRONTEND_URL=APP, DOWNLOAD_READY_EMAIL_LIMIT_PER_EMAIL=1)
class ReadyEmailLoggingTests(JobBase):
    LOGGER = 'apps.clients'

    def new_job(self, **fields):
        fields.setdefault('email', 'log@example.com')
        fields.setdefault('state', DownloadJob.State.READY)
        return DownloadJob.objects.create(gallery=self.gallery, **fields)

    def test_queued_then_sent(self):
        with self.assertLogs(self.LOGGER, level='INFO') as logs:
            job, _ = self.prepare_job(email='queued@example.com')
        text = '\n'.join(logs.output)
        self.assertIn(f'job {job.id}: queued', text)
        self.assertIn(f'job {job.id}: sent', text)

    def test_skipped_no_email(self):
        job = self.new_job(email='')
        with self.assertLogs(self.LOGGER, level='INFO') as logs:
            self.assertFalse(send_ready_email(job))
            self.assertFalse(deliver_ready_email(job.id))
        self.assertEqual(sum('skipped (no email)' in line for line in logs.output), 2)

    def test_skipped_already_sent(self):
        job = self.new_job(ready_email_sent_at=timezone.now())
        with self.assertLogs(self.LOGGER, level='INFO') as logs:
            self.assertFalse(deliver_ready_email(job.id))
        self.assertIn(f'job {job.id}: skipped (already sent)', logs.output[0])

    def test_skipped_rate_limit_names_the_limit(self):
        self.new_job(ready_email_sent_at=timezone.now())
        job = self.new_job()
        with self.assertLogs(self.LOGGER, level='INFO') as logs:
            self.assertFalse(deliver_ready_email(job.id))
        self.assertIn(f'job {job.id}: skipped (email rate limit)', logs.output[0])
        self.assertEqual(mail.outbox, [])

    def test_skipped_job_not_ready_or_missing(self):
        job = self.new_job(state=DownloadJob.State.PREPARING)
        with self.assertLogs(self.LOGGER, level='INFO') as logs:
            self.assertFalse(deliver_ready_email(job.id))
            self.assertFalse(deliver_ready_email('00000000-0000-0000-0000-000000000000'))
        self.assertIn('skipped (job not ready)', logs.output[0])
        self.assertIn('skipped (job not found)', logs.output[1])

    def test_failed_send_and_failed_queue(self):
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=OSError('SMTP down')):
            with self.assertLogs(self.LOGGER, level='INFO') as logs:
                job, _ = self.prepare_job(email='down@example.com')
        self.assertIn(f'job {job.id}: failed', '\n'.join(logs.output))
        job2 = self.new_job(email='queue@example.com')
        with mock.patch('apps.clients.tasks.send_download_ready_email.delay', side_effect=ConnectionError('redis')):
            with self.assertLogs(self.LOGGER, level='INFO') as logs:
                self.assertFalse(send_ready_email(job2))
        self.assertIn(f'job {job2.id}: failed (could not queue)', logs.output[0])


class DevelopmentEmailLimitsTests(JobBase):
    def test_development_loosens_the_limits_and_production_keeps_the_defaults(self):
        base = import_module('config.settings.base')
        development = import_module('config.settings.development')
        self.assertEqual(development.DOWNLOAD_READY_EMAIL_LIMIT_PER_EMAIL, 50)
        self.assertEqual(base.DOWNLOAD_READY_EMAIL_LIMIT_PER_EMAIL, 5)
        self.assertEqual(base.DOWNLOAD_READY_EMAIL_LIMIT_PER_IP, 10)
        self.assertEqual(base.DOWNLOAD_READY_EMAIL_LIMIT_PER_GALLERY, 30)
        # production.py cannot be imported here (it refuses to load without S3 secrets): read its source.
        with open(os.path.join(os.path.dirname(development.__file__), 'production.py'), encoding='utf-8') as handle:
            self.assertNotIn('DOWNLOAD_READY_EMAIL_LIMIT', handle.read())
