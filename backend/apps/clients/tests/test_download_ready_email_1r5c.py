# backend/apps/clients/tests/test_download_ready_email_1r5c.py
"""
Task 1R.5-C — the "your photos are ready for download" email.

  - sent exactly once per job, to the visitor's address, only when one was captured
  - From name = studio name, Reply-To = photographer, the agreed subject and copy
  - HTML + plain-text parts, dark-mode safe, absolute link on FRONTEND_URL
  - the link opens Page 4 (the ready page's key is bound to that one job)
  - hourly rate limits per recipient / IP / gallery, skipped silently
  - a send (or queue) failure never breaks the job
"""
import re
from datetime import timedelta
from email.utils import parseaddr
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from apps.clients.download_jobs import run_download_job
from apps.clients.models import DownloadJob
from apps.clients.ready_email import deliver_ready_email, requester_ip
from apps.clients.tests.test_download_pages_1r5b import JobBase

APP = 'https://app.kyapture.test'


def page4_url(message):
    return re.search(r'https?://\S+/download/file/[0-9a-f-]+#key=[\w:\-.]+', message.body).group(0)


@override_settings(FRONTEND_URL=APP)
class ReadyEmailContentTests(JobBase):
    def setUp(self):
        super().setUp()
        self.photographer.display_name = 'Herry Shop'
        self.photographer.save(update_fields=['display_name'])
        self.gallery.title = 'sari and ravi'
        self.gallery.save(update_fields=['title'])

    def sent(self, **kwargs):
        job, _ = self.prepare_job(email='buyer@example.com', **kwargs)
        self.assertEqual(len(mail.outbox), 1)
        return job, mail.outbox[0]

    def test_headers(self):
        job, message = self.sent()
        self.assertEqual(message.to, ['buyer@example.com'])
        self.assertEqual(message.subject, 'Your Photos for sari and ravi are ready for download')
        self.assertEqual(message.reply_to, [self.photographer.email])
        name, address = parseaddr(message.from_email)
        self.assertEqual(name, 'Herry Shop')                         # From name = studio name
        self.assertEqual(address, 'no-reply@kyapture.com')           # the platform's own sending address

    def test_studio_name_falls_back_to_the_username(self):
        self.photographer.display_name = ''
        self.photographer.save(update_fields=['display_name'])
        _, message = self.sent()
        self.assertEqual(parseaddr(message.from_email)[0], self.photographer.username)

    def test_plain_text_part_has_the_agreed_copy_and_link(self):
        job, message = self.sent()
        body = message.body
        for line in (
            'Download Ready',
            'Your photos for sari and ravi are ready for download.',
            'DOWNLOAD PHOTOS',
            'You can use this link to download them again at anytime during the next 7 days. '
            'After 7 days, you can visit the gallery to request a new download.',
            'Herry Shop',
            f'{APP}/g/{self.username}/{self.slug}',
            'Questions? Reply to this email.',
        ):
            self.assertIn(line, body)
        url = page4_url(message)
        self.assertTrue(url.startswith(f'{APP}/g/{self.username}/{self.slug}/download/file/{job.id}#key='))
        self.assertNotIn('localhost', body)

    def test_html_alternative_is_dark_mode_safe_and_links_the_same_page(self):
        job, message = self.sent()
        ((html, mimetype),) = message.alternatives
        self.assertEqual(mimetype, 'text/html')
        self.assertIn('Download Ready Notification', html)
        self.assertIn('Download Photos', html)
        self.assertIn('name="color-scheme" content="light dark"', html)
        self.assertIn('prefers-color-scheme: dark', html)
        self.assertIn(f'href="{page4_url(message).replace("&", "&amp;")}"', html)   # same link as the text part
        self.assertIn('during the next 7 days', html)
        self.assertNotIn('localhost', html)

    def test_content_is_escaped_and_headers_cannot_be_injected(self):
        self.gallery.title = '<script>alert(1)</script>\nBcc: evil@example.com'
        self.gallery.save(update_fields=['title'])
        self.photographer.display_name = 'Evil"\r\nBcc: x@example.com'
        self.photographer.save(update_fields=['display_name'])
        _, message = self.sent()
        html = message.alternatives[0][0]
        self.assertNotIn('<script>', html)
        self.assertNotIn('\n', message.subject)
        self.assertNotIn('\n', message.from_email)
        self.assertEqual(message.bcc, [])

    def test_the_link_opens_page_4_for_that_job_only(self):
        job, message = self.sent()
        key = page4_url(message).split('key=')[1]
        ready = self.status_by_key(job, key)
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.data['state'], 'ready')
        self.assertTrue(ready.data['files'])
        other, _ = self.prepare_job(email='other@example.com', resolution='web')
        self.assertNotEqual(other.id, job.id)
        self.assertNotEqual(self.status_by_key(other, key).status_code, 200)   # a key never opens another job


@override_settings(FRONTEND_URL=APP)
class ReadyEmailOnceTests(JobBase):
    def test_exactly_one_email_per_job_even_when_run_again(self):
        job, _ = self.prepare_job(email='once@example.com')
        self.assertEqual(len(mail.outbox), 1)
        run_download_job(job.id)
        self.assertFalse(deliver_ready_email(job.id))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(DownloadJob.objects.get(pk=job.pk).ready_email_sent_at)

    def test_a_reused_identical_request_sends_nothing_more(self):
        self.prepare_job(email='reuse@example.com')
        self.prepare_job(email='reuse@example.com')
        self.assertEqual(len(mail.outbox), 1)

    def test_no_email_without_a_recipient_or_before_ready(self):
        job, _ = self.prepare_job(email='x@example.com')
        mail.outbox.clear()
        DownloadJob.objects.filter(pk=job.pk).update(ready_email_sent_at=None, email=None)
        self.assertFalse(deliver_ready_email(job.id))
        DownloadJob.objects.filter(pk=job.pk).update(email='x@example.com', state=DownloadJob.State.PREPARING)
        self.assertFalse(deliver_ready_email(job.id))
        self.assertEqual(mail.outbox, [])

    def test_a_failed_job_sends_no_ready_email(self):
        token = self.token(email='fail@example.com')
        with mock.patch('apps.clients.views._resolve_zip_source', side_effect=RuntimeError('x')):
            self.client.post(f'{self.base}download/', {'download_token': token}, format='json')
        self.assertEqual(DownloadJob.objects.get().state, DownloadJob.State.FAILED)
        self.assertEqual(mail.outbox, [])

    def test_the_requesting_ip_is_stored_and_a_bogus_one_is_ignored(self):
        token = self.token(email='ip@example.com')
        response = self.client.post(f'{self.base}download/', {'download_token': token}, format='json',
                                    REMOTE_ADDR='203.0.113.9')
        self.assertEqual(DownloadJob.objects.get(pk=response.data['job_id']).requester_ip, '203.0.113.9')
        self.assertIsNone(requester_ip(mock.Mock(META={'REMOTE_ADDR': 'not-an-ip'})))


@override_settings(FRONTEND_URL=APP, DOWNLOAD_READY_EMAIL_LIMIT_PER_EMAIL=2,
                   DOWNLOAD_READY_EMAIL_LIMIT_PER_IP=3, DOWNLOAD_READY_EMAIL_LIMIT_PER_GALLERY=4)
class ReadyEmailRateLimitTests(JobBase):
    def stamp(self, count, **fields):
        for _ in range(count):
            DownloadJob.objects.create(
                gallery=self.gallery, state=DownloadJob.State.READY, ready_email_sent_at=timezone.now(), **fields)

    def run_new_job(self, email='new@example.com', ip='198.51.100.1'):
        job = DownloadJob.objects.create(
            gallery=self.gallery, state=DownloadJob.State.READY, email=email, requester_ip=ip)
        return deliver_ready_email(job.id), job

    def test_per_recipient_limit(self):
        self.stamp(2, email='Spam@Example.com')                      # case-insensitive
        sent, _ = self.run_new_job(email='spam@example.com')
        self.assertFalse(sent)
        self.assertEqual(mail.outbox, [])
        self.assertTrue(self.run_new_job(email='someone-else@example.com')[0])

    def test_per_ip_limit(self):
        self.stamp(3, email='a@example.com', requester_ip='198.51.100.1')
        self.assertFalse(self.run_new_job(email='b@example.com', ip='198.51.100.1')[0])
        self.assertTrue(self.run_new_job(email='b@example.com', ip='198.51.100.2')[0])

    def test_per_gallery_limit(self):
        self.stamp(4)
        self.assertFalse(self.run_new_job(email='c@example.com', ip='198.51.100.3')[0])

    def test_a_limited_job_is_untouched_and_the_window_expires(self):
        self.stamp(2, email='spam@example.com')
        sent, job = self.run_new_job(email='spam@example.com')
        self.assertFalse(sent)
        job.refresh_from_db()
        self.assertEqual(job.state, DownloadJob.State.READY)
        self.assertIsNone(job.ready_email_sent_at)
        DownloadJob.objects.exclude(pk=job.pk).update(ready_email_sent_at=timezone.now() - timedelta(hours=2))
        self.assertTrue(deliver_ready_email(job.id))

    def test_the_visitor_cannot_tell_a_limited_address_from_a_normal_one(self):
        self.stamp(2, email='spam@example.com')
        limited, normal = (self.prepare_job(email=e)[1] for e in ('spam@example.com', 'fine@example.com'))
        self.assertEqual(limited.status_code, normal.status_code)
        self.assertEqual(set(limited.data), set(normal.data))
        self.assertEqual(len(mail.outbox), 1)                        # only the normal one was mailed


@override_settings(FRONTEND_URL=APP)
class ReadyEmailFailureTests(JobBase):
    def test_a_send_failure_does_not_fail_the_job_and_is_logged(self):
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=OSError('SMTP down')):
            with self.assertLogs('apps.clients.ready_email', level='ERROR') as logs:
                job, response = self.prepare_job(email='down@example.com')
        self.assertIn(str(job.id), logs.output[0])
        self.assertEqual(response.status_code, 202)
        job.refresh_from_db()
        self.assertEqual(job.state, DownloadJob.State.READY)
        self.assertTrue(job.files)
        self.assertIsNone(job.ready_email_sent_at)                   # not recorded as sent
        self.assertEqual(self.status_by_key(job, response.data['link_token']).status_code, 200)

    def test_a_queue_failure_does_not_fail_the_job(self):
        with mock.patch('apps.clients.tasks.send_download_ready_email.delay', side_effect=ConnectionError('redis')):
            job, _ = self.prepare_job(email='queue@example.com')
        self.assertEqual(job.state, DownloadJob.State.READY)
        self.assertEqual(mail.outbox, [])

    def test_an_unusable_app_url_sends_nothing_and_does_not_raise(self):
        with override_settings(FRONTEND_URL='not-a-url'):
            job, _ = self.prepare_job(email='badurl@example.com')
        self.assertEqual(job.state, DownloadJob.State.READY)
        self.assertEqual(mail.outbox, [])
