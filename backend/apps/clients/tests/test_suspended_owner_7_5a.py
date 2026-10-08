# backend/apps/clients/tests/test_suspended_owner_7_5a.py
"""
CHUNK 7.5-A (debt row 131) - when an owner is suspended, their galleries stop being public.

Every public path answers a plain 404 for a suspended owner's gallery - the gallery payload, the
photo pages, unlock, favorites and favorite lists, video playback, single-photo downloads,
download access, preparing a ZIP, the job-status poll (by link key and by download token), the
ZIP file link and the portfolio - and every one of them works again after reactivation, with the
same links and keys the visitor already held (nothing is deleted by a suspension). One test per
path; the owner is suspended and reactivated through the real staff endpoints.
"""
from unittest import mock

import bcrypt
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.clients.download_jobs import run_download_job
from apps.clients.models import ClientSession, DownloadJob
from apps.clients.ready_email import deliver_ready_email
from apps.clients.tests.test_download_pages_1r5b import JobBase
from apps.photos.models import MediaAsset
from apps.users.models import User

STAFF_PASSWORD = 'Sturdy-Pass-8842!'


def release(response):
    """Reads a streamed file response to its end, which closes the file (response.close() would also close the DB connection)."""
    if getattr(response, 'streaming', False):
        b''.join(response.streaming_content)


def describe(response):
    """Failure text for a response, JSON or streamed."""
    if getattr(response, 'streaming', False):
        release(response)
        return f'streamed {response.status_code}'
    return getattr(response, 'data', None) or response.content[:200]


class SuspendedOwnerBase(JobBase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            email='suspender@example.com', username='suspender', password=STAFF_PASSWORD, is_staff=True)
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(user=self.staff)
        self.visitor = self.client

    def set_owner(self, active):
        action = 'reactivate' if active else 'suspend'
        response = self.staff_client.post(
            f'/api/v1/staff/users/{self.photographer.pk}/{action}/', {'reason': 'QA 7.5-A'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def prove(self, call, ok=(200,), closed=(404,)):
        """`call()` works, the owner is suspended and it is a 404, the owner is reactivated and it works again."""
        def attempt():
            cache.clear()              # the shared 5/min unlock throttle is not what is being tested
            return call()

        first = attempt()
        release(first)
        self.assertIn(first.status_code, ok, f'before: {describe(first)}')
        self.set_owner(False)
        gone = attempt()
        self.assertIn(gone.status_code, closed, f'suspended: {describe(gone)}')
        self.assertEqual(gone.status_code, 404)
        self.assertNotIn(b'flow-gallery-photo-download', gone.content)
        self.set_owner(True)
        again = attempt()
        release(again)
        self.assertIn(again.status_code, ok, f'reactivated: {describe(again)}')


class PublicPathsOf404ForASuspendedOwnerTests(SuspendedOwnerBase):
    def test_the_gallery_payload(self):
        self.prove(lambda: self.visitor.get(self.base))

    def test_the_photo_pages(self):
        self.prove(lambda: self.visitor.get(f'{self.base}photos/'))

    def test_unlock(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'gallerypass', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])
        self.prove(lambda: self.visitor.post(f'{self.base}unlock/', {'password': 'gallerypass'}, format='json'))

    def test_an_unlock_session_the_visitor_already_holds_stops_working_and_then_resumes(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'gallerypass', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])
        session = ClientSession.objects.issue(gallery=self.gallery)
        token = session.raw_token
        auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        self.prove(lambda: self.visitor.get(self.base, **auth))
        self.prove(lambda: self.visitor.get(f'{self.base}photos/', **auth))

    def test_favorites(self):
        photo = self.a1
        self.prove(lambda: self.visitor.get(f'{self.base}favorites/', {'client_uid': 'u1'}))
        self.prove(lambda: self.visitor.post(
            f'{self.base}favorites/', {'media_asset_id': str(photo.id), 'client_uid': 'u1'}, format='json'))
        self.prove(lambda: self.visitor.delete(
            f'{self.base}favorites/', {'media_asset_id': str(photo.id), 'client_uid': 'u1'}, format='json'))

    def test_favorite_lists_and_a_single_list(self):
        self.visitor.post(f'{self.base}favorites/', {'media_asset_id': str(self.a1.id), 'client_uid': 'u2'}, format='json')
        listing = self.visitor.get(f'{self.base}favorites/lists/', {'client_uid': 'u2'})
        list_id = listing.data['results'][0]['id']
        self.prove(lambda: self.visitor.get(f'{self.base}favorites/lists/', {'client_uid': 'u2'}))
        names = iter(f'Mine {n}' for n in range(10))
        self.prove(lambda: self.visitor.post(
            f'{self.base}favorites/lists/', {'name': next(names), 'client_uid': 'u2'}, format='json'), ok=(200, 201))
        self.prove(lambda: self.visitor.get(f'{self.base}favorites/lists/{list_id}/', {'client_uid': 'u2'}))

    def test_video_playback(self):
        video = MediaAsset(
            gallery=self.gallery, media_type=MediaAsset.MediaType.VIDEO, original_name='v.mp4', file_size=10,
            processing_status=MediaAsset.ProcessingStatus.READY)
        video.original_file.save('v.mp4', ContentFile(b'ORIGINAL'), save=False)
        video.playback_file.save('v.playback.mp4', ContentFile(b'PLAYBACK'), save=False)
        video.save()
        self.prove(lambda: self.visitor.get(f'{self.base}video/{video.id}/stream/'), ok=(200, 302))

    def test_a_single_photo_download(self):
        token = self.token()
        self.prove(lambda: self.visitor.get(self.photo_url(self.a1), {'download_token': token, 'resolution': 'web'}))

    def test_download_access(self):
        self.prove(lambda: self.visitor.post(self.access_url, {'email': 'c@example.com', 'pin': '1234'}, format='json'),
                   ok=(200, 202, 400, 401, 403, 429))

    def test_preparing_a_zip(self):
        token = self.token()
        self.prove(lambda: self.visitor.post(
            f'{self.base}download/', {'download_token': token, 'email': 'prep@example.com'}, format='json'), ok=(202,))

    def test_the_job_status_poll_by_download_token(self):
        job, _ = self.prepare_job()
        token = self.token()
        self.prove(lambda: self.visitor.get(f'{self.base}download-jobs/{job.id}/', {'download_token': token}))

    def test_the_zip_ready_link_status_poll_by_link_key(self):
        job, response = self.prepare_job()
        key = response.data['link_token']
        self.prove(lambda: self.status_by_key(job, key))

    def test_the_zip_file_link(self):
        job, response = self.prepare_job()
        url = self.status_by_key(job, response.data['link_token']).data['files'][0]['url']
        self.prove(lambda: self.visitor.get(url))

    def test_the_portfolio(self):
        self.prove(lambda: self.visitor.get(f'/api/v1/public/{self.username}/'))

    def test_the_gallery_is_not_in_the_portfolio_listing_while_suspended(self):
        self.set_owner(False)
        self.assertEqual(self.visitor.get(f'/api/v1/public/{self.username}/').status_code, 404)

    def test_other_photographers_galleries_stay_public(self):
        other = User.objects.create_user(email='neighbour@example.com', username='neighbour', password=STAFF_PASSWORD)
        from apps.galleries.models import Gallery
        Gallery.objects.create(photographer=other, title='Open', slug='open-gal', is_published=True)
        self.set_owner(False)
        self.assertEqual(self.visitor.get('/api/v1/public/neighbour/open-gal/').status_code, 200)

    def test_a_download_the_visitor_asked_for_before_the_suspension_is_not_built_after_it(self):
        token = self.token()
        with mock.patch('apps.clients.views.prepare_download_job.delay'):         # queued, not yet run
            queued = self.visitor.post(
                f'{self.base}download/', {'download_token': token, 'email': 'late@example.com'}, format='json')
        self.assertEqual(queued.status_code, 202, queued.data)
        job = DownloadJob.objects.get(pk=queued.data['job_id'])
        self.assertEqual(job.state, DownloadJob.State.PREPARING)
        self.set_owner(False)
        run_download_job(job.pk)
        job.refresh_from_db()
        self.assertEqual((job.state, job.error_code, job.files), (DownloadJob.State.FAILED, 'owner_unavailable', []))

    def test_the_ready_email_is_not_sent_for_a_suspended_owner_and_is_after_reactivation(self):
        job, _ = self.prepare_job(email='ready@example.com')
        DownloadJob.objects.filter(pk=job.pk).update(ready_email_sent_at=None)
        mail.outbox = []
        self.set_owner(False)
        self.assertFalse(deliver_ready_email(job.pk))
        self.assertEqual(mail.outbox, [])
        self.set_owner(True)
        self.assertTrue(deliver_ready_email(job.pk))
        self.assertEqual(len(mail.outbox), 1)

    def test_a_suspension_deletes_nothing_the_visitor_or_the_owner_holds(self):
        job, response = self.prepare_job()
        assets, jobs = MediaAsset.objects.filter(gallery=self.gallery).count(), DownloadJob.objects.count()
        self.set_owner(False)
        self.assertEqual(MediaAsset.objects.filter(gallery=self.gallery).count(), assets)
        self.assertEqual(DownloadJob.objects.count(), jobs)
        self.set_owner(True)
        ready = self.status_by_key(job, response.data['link_token'])
        self.assertEqual(ready.status_code, status.HTTP_200_OK)
