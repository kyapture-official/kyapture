# backend/apps/clients/tests/test_security_7b.py
"""
CHUNK 7-B - the public download/view side.

  - Row 81 (SEC-04): failed download-PIN and gallery-password attempts are
    counted per gallery AND per client; a locked client or gallery gets a
    clear 429 (even for the right value), a success clears that client's
    count, and the photographer resets a gallery lock by changing the PIN or
    password (and is told about the lock in the bell).
  - Unlock tokens never survive a password change on ANY path (the gallery
    PATCH too), and never sit in the database in plaintext (row 89).
  - Row 84 (SEC-07): the video stream never falls back to the private original.
  - Row 99 (SEC-27): a client download needs a READY asset, and Web Size never
    falls back to the original.
  - Row 85 (SEC-09): public derivative URLs a visitor has seen stop working
    when the gallery gets a password, a new password, or is unpublished.
  - Row 83 (SEC-06): the dev /media/ server serves public derivatives only;
    a private file needs a signed, expiring URL (like S3).
"""
import hashlib
import importlib
import os
import time
from unittest import mock

import bcrypt
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import RequestFactory, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import SimpleRateThrottle

from apps.clients.models import ClientSession, FavoriteList
from apps.clients.tests.zip_flow import InlineDownloadJobsMixin
from apps.core.storage import PrivateMediaStorage, PublicMediaStorage
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet
from apps.users.models import Notification, User

PIN = '482193'
PASSWORD = 'gallery-pass-7b'
LOOSE = {'password_unlock': '10000/minute', 'public_gallery_browse': '10000/minute'}


def fast_hash(value):
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt(4)).decode()


class SecurityBase(InlineDownloadJobsMixin, APITestCase):
    """A published gallery with a password and a download PIN, two READY photos and one video."""
    username = 'sec7b'
    slug = 'sec-gallery'

    def setUp(self):
        cache.clear()
        # The per-IP throttles have their own tests; here they must not hide the lockout.
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, LOOSE)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.owner = User.objects.create_user(
            email=f'{self.username}@example.com', password='SecurePassword123!', username=self.username)
        self.gallery = Gallery.objects.create(
            photographer=self.owner, title='Security', slug=self.slug, is_published=True, is_active=True,
            allow_download=True, is_password_protected=True, password_hash=fast_hash(PASSWORD),
            download_pin_hash=fast_hash(PIN),
        )
        self.set = PhotoSet.objects.create(gallery=self.gallery, name='Main', order=1)
        self.photo = self.make_image('one.jpg')
        self.photo2 = self.make_image('two.jpg')
        self.base = f'/api/v1/public/{self.username}/{self.slug}/'

    def make_image(self, name, status_=MediaAsset.ProcessingStatus.READY, derivatives=True):
        asset = MediaAsset(gallery=self.gallery, media_type=MediaAsset.MediaType.IMAGE, original_name=name,
                           file_size=10, processing_status=status_, photo_set=self.set)
        asset.original_file.save(name, ContentFile(b'ORIGINAL-BYTES:' + name.encode()), save=False)
        asset.save()
        if derivatives:
            for field in ('display_file', 'medium_file', 'thumbnail_file'):
                getattr(asset, field).save(f'{name}.webp', ContentFile(f'{field}:{name}'.encode()), save=False)
            asset.download_file.save(f'{name}.master.jpg', ContentFile(b'MASTER:' + name.encode()), save=False)
            asset.save()
        return asset

    def make_video(self, with_playback):
        asset = MediaAsset(gallery=self.gallery, media_type=MediaAsset.MediaType.VIDEO, original_name='clip.mov',
                           file_size=10, photo_set=self.set,
                           processing_status=(MediaAsset.ProcessingStatus.READY if with_playback
                                              else MediaAsset.ProcessingStatus.PROCESSING))
        asset.original_file.save('clip.mov', ContentFile(b'ORIGINAL-VIDEO-BYTES'), save=False)
        asset.save()
        if with_playback:
            asset.playback_file.save('clip.mp4', ContentFile(b'PLAYBACK-BYTES'), save=False)
            asset.poster_image.save('clip.jpg', ContentFile(b'POSTER'), save=False)
            asset.save()
        return asset

    def visitor(self, ip):
        return APIClient(REMOTE_ADDR=ip)

    def unlock(self, client=None, password=PASSWORD):
        return (client or self.client).post(f'{self.base}unlock/', {'password': password}, format='json')

    def token(self, client=None):
        response = self.unlock(client)
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        return response.data['access_token']

    def pin(self, client, value, token):
        return client.post(f'{self.base}download-access/', {'pin': value, 'email': 'c@example.com'},
                           format='json', HTTP_AUTHORIZATION=f'Bearer {token}')


class PinLockoutTests(SecurityBase):
    def setUp(self):
        super().setUp()
        self.v = self.visitor('192.0.2.10')
        self.t = self.token(self.v)

    def test_five_wrong_pins_lock_that_client_even_for_the_right_pin(self):
        codes = [self.pin(self.v, f'{100000 + i}', self.t).status_code for i in range(5)]
        self.assertEqual(codes, [401] * 5)
        locked = self.pin(self.v, PIN, self.t)
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.data['code'], 'too_many_attempts')
        self.assertIn('Try again in', locked.data['error'])
        self.assertTrue(int(locked['Retry-After']) > 0)

    def test_another_client_is_not_locked_by_someone_elses_guesses(self):
        for i in range(5):
            self.pin(self.v, f'{100000 + i}', self.t)
        other = self.visitor('192.0.2.11')
        self.assertEqual(self.pin(other, PIN, self.token(other)).status_code, 200)

    def test_a_success_clears_the_clients_count(self):
        for i in range(4):
            self.pin(self.v, f'{100000 + i}', self.t)
        self.assertEqual(self.pin(self.v, PIN, self.t).status_code, 200)
        codes = [self.pin(self.v, f'{200000 + i}', self.t).status_code for i in range(4)]
        self.assertEqual(codes, [401] * 4)
        self.assertEqual(self.pin(self.v, PIN, self.t).status_code, 200)

    def test_many_clients_guessing_lock_the_gallery_and_tell_the_photographer(self):
        guesses = 0
        for n in range(12):                        # 12 addresses x 5 guesses: never a per-client lock alone
            client = self.visitor(f'198.51.100.{n + 1}')
            token = self.token(client)
            for i in range(5):
                response = self.pin(client, f'{300000 + guesses}', token)
                guesses += 1
                if response.status_code == 429:
                    break
            if response.status_code == 429 and response.data['code'] == 'gallery_locked':
                break
        self.assertEqual(response.data['code'], 'gallery_locked')
        self.assertLessEqual(guesses, 51)
        fresh = self.visitor('203.0.113.200')
        locked = self.pin(fresh, PIN, self.token(fresh))
        self.assertEqual((locked.status_code, locked.data['code']), (429, 'gallery_locked'))
        self.assertIn('Contact', locked.data['error'])
        note = Notification.objects.get(user=self.owner, kind=Notification.Kind.SECURITY)
        self.assertIn('PIN', note.message)

    def test_changing_the_pin_is_the_safe_reset(self):
        for i in range(5):
            self.pin(self.v, f'{100000 + i}', self.t)
        self.assertEqual(self.pin(self.v, PIN, self.t).status_code, 429)
        self.client.force_authenticate(self.owner)
        changed = self.client.post(f'/api/v1/galleries/{self.slug}/set-download-pin/', {'pin': '777123'}, format='json')
        self.assertEqual(changed.status_code, 200)
        self.client.force_authenticate(None)
        self.assertEqual(self.pin(self.v, '777123', self.t).status_code, 200)


class PasswordLockoutTests(SecurityBase):
    def test_five_wrong_passwords_lock_that_client(self):
        v = self.visitor('192.0.2.20')
        codes = [self.unlock(v, f'wrong-{i}').status_code for i in range(5)]
        self.assertEqual(codes, [401] * 5)
        locked = self.unlock(v)
        self.assertEqual((locked.status_code, locked.data['code']), (429, 'too_many_attempts'))
        self.assertFalse(ClientSession.objects.filter(gallery=self.gallery, ip_address='192.0.2.20').exists())

    def test_a_new_password_is_the_safe_reset(self):
        v = self.visitor('192.0.2.21')
        for i in range(5):
            self.unlock(v, f'wrong-{i}')
        self.client.force_authenticate(self.owner)
        self.client.post(f'/api/v1/galleries/{self.slug}/set-password/', {'password': 'brand-new-pass'}, format='json')
        self.client.force_authenticate(None)
        self.assertEqual(self.unlock(v, 'brand-new-pass').status_code, 200)


class UnlockTokenLifecycleTests(SecurityBase):
    def gallery_with(self, token):
        return self.client.get(self.base, HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_a_password_change_through_the_gallery_patch_ends_old_tokens(self):
        token = self.token()
        self.assertEqual(self.gallery_with(token).status_code, 200)
        owner = APIClient()
        owner.force_authenticate(self.owner)
        patched = owner.patch(f'/api/v1/galleries/{self.slug}/', {'password': 'another-pass-1'}, format='json')
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual(self.gallery_with(token).status_code, 401)

    def test_turning_protection_off_and_on_through_the_patch_ends_old_tokens(self):
        token = self.token()
        owner = APIClient()
        owner.force_authenticate(self.owner)
        owner.patch(f'/api/v1/galleries/{self.slug}/', {'is_password_protected': False}, format='json')
        owner.patch(f'/api/v1/galleries/{self.slug}/', {'is_password_protected': True, 'password': 'pass-again'},
                    format='json')
        self.assertEqual(self.gallery_with(token).status_code, 401)

    def test_the_set_password_endpoint_ends_old_tokens(self):
        token = self.token()
        self.client.force_authenticate(self.owner)
        self.client.post(f'/api/v1/galleries/{self.slug}/set-password/', {'password': 'rotated-pass'}, format='json')
        self.client.force_authenticate(None)
        for path in ('', 'photos/'):
            self.assertEqual(self.client.get(f'{self.base}{path}', HTTP_AUTHORIZATION=f'Bearer {token}').status_code, 401)

    def test_a_pin_change_ends_issued_download_tokens(self):
        token = self.token()
        grant = self.pin(self.client, PIN, token).data['download_token']
        url = f'{self.base}photo/{self.photo.id}/download/'
        self.assertEqual(self.client.get(url, {'token': token, 'download_token': grant, 'check': '1'}).status_code, 200)
        self.client.force_authenticate(self.owner)
        self.client.post(f'/api/v1/galleries/{self.slug}/set-download-pin/', {'pin': '555444'}, format='json')
        self.client.force_authenticate(None)
        denied = self.client.get(url, {'token': token, 'download_token': grant, 'check': '1'})
        self.assertEqual((denied.status_code, denied.data['code']), (401, 'download_access_expired'))

    def test_the_token_is_not_stored_in_plaintext(self):
        token = self.token()
        stored = ClientSession.objects.get(gallery=self.gallery).access_token
        self.assertNotEqual(stored, token)
        self.assertEqual(stored, hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(self.gallery_with(token).status_code, 200)
        # The stored value itself is not a working token.
        self.assertEqual(self.gallery_with(stored).status_code, 401)

    def test_favorites_made_with_a_token_are_not_keyed_by_the_plaintext_token(self):
        token = self.token()
        hearted = self.client.post(f'{self.base}favorites/', {'media_asset_id': str(self.photo.id)}, format='json',
                                   HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(hearted.status_code, 200, hearted.data)
        self.assertFalse(FavoriteList.objects.filter(client_key=token).exists())
        listed = self.client.get(f'{self.base}favorites/', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(listed.data['favorited_ids'], [str(self.photo.id)])

    def test_existing_plaintext_rows_are_hashed_by_the_migration(self):
        migration = importlib.import_module('apps.clients.migrations.0013_hash_unlock_tokens')
        raw = 'a' * 64
        session = ClientSession.objects.create(gallery=self.gallery)
        ClientSession.objects.filter(pk=session.pk).update(access_token=raw)
        FavoriteList.objects.create(gallery=self.gallery, client_key=raw, name='Mine')
        from django.apps import apps as global_apps
        migration.hash_existing_tokens(global_apps, None)
        self.assertEqual(ClientSession.objects.get(pk=session.pk).access_token, hashlib.sha256(raw.encode()).hexdigest())
        self.assertTrue(FavoriteList.objects.filter(client_key=hashlib.sha256(raw.encode()).hexdigest()).exists())
        self.assertEqual(self.gallery_with(raw).status_code, 200)     # the visitor's browser keeps working


class VideoStreamTests(SecurityBase):
    def test_a_video_still_processing_never_streams_the_original(self):
        video = self.make_video(with_playback=False)
        token = self.token()
        response = self.client.get(f'{self.base}video/{video.id}/stream/', {'token': token})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'video_processing')
        body = b''.join(response.streaming_content) if response.streaming else response.content
        self.assertNotIn(b'ORIGINAL-VIDEO-BYTES', body)
        self.assertNotIn(video.original_file.name.encode(), body)

    def test_a_ready_video_streams_the_playback_copy(self):
        video = self.make_video(with_playback=True)
        token = self.token()
        response = self.client.get(f'{self.base}video/{video.id}/stream/', {'token': token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'PLAYBACK-BYTES')


class ReadyOnlyDownloadTests(SecurityBase):
    def setUp(self):
        super().setUp()
        self.gallery.is_password_protected = False
        self.gallery.download_pin_hash = None
        self.gallery.save()

    def get(self, asset, resolution):
        # A cold Web Size would wait for the websize worker: report "nothing cached" instead.
        with mock.patch('apps.clients.views.request_cached', return_value=None):
            return self.client.get(f'{self.base}photo/{asset.id}/download/', {'resolution': resolution,
                                                                             'download_token': self.grant()})

    def grant(self):
        return self.client.post(f'{self.base}download-access/', {'email': 'c@example.com'},
                                format='json').data['download_token']

    def test_a_photo_that_is_not_ready_is_not_downloadable(self):
        pending = self.make_image('pending.jpg', status_=MediaAsset.ProcessingStatus.PENDING)
        for resolution in ('web', 'download'):
            self.assertEqual(self.get(pending, resolution).status_code, 404)

    def test_web_size_never_falls_back_to_the_original(self):
        bare = self.make_image('bare.jpg', derivatives=False)
        response = self.get(bare, 'web')
        self.assertNotEqual(response.status_code, 200)
        body = b''.join(response.streaming_content) if getattr(response, 'streaming', False) else response.content
        self.assertNotIn(b'ORIGINAL-BYTES', body)


class PublicUrlRotationTests(SecurityBase):
    """Row 85: URLs a visitor saw stop working once the gallery is closed to them."""

    def setUp(self):
        super().setUp()
        self.gallery.is_password_protected = False
        self.gallery.password_hash = None
        self.gallery.save()
        self.video = self.make_video(with_playback=True)
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)
        # The move is a Celery task queued after commit: run it inline here.
        from apps.photos.tasks import rotate_public_media
        patcher = mock.patch('apps.photos.tasks.rotate_public_media.delay',
                             side_effect=lambda gallery_id: rotate_public_media(gallery_id))
        patcher.start()
        self.addCleanup(patcher.stop)

    def as_owner(self, method, url, data):
        with self.captureOnCommitCallbacks(execute=True):
            return getattr(self.owner_client, method)(url, data, format='json')

    def seen_names(self):
        names = []
        for asset in MediaAsset.objects.filter(gallery=self.gallery):
            for field in ('display_file', 'medium_file', 'thumbnail_file', 'poster_image', 'playback_file'):
                name = getattr(asset, field).name
                if name:
                    names.append(name)
        return names

    def assert_rotated(self, before):
        storage = PublicMediaStorage()
        after = self.seen_names()
        self.assertEqual(len(after), len(before))
        for old in before:
            self.assertFalse(storage.exists(old), f'{old} still served')
            self.assertNotIn(old, after)
        for new in after:
            self.assertTrue(storage.exists(new))
        self.gallery.refresh_from_db()
        self.assertTrue(self.gallery.media_token)
        self.assertTrue(all(self.gallery.media_token in name for name in after))

    def test_adding_a_password_moves_every_public_file(self):
        before = self.seen_names()
        response = self.as_owner('post', f'/api/v1/galleries/{self.slug}/set-password/', {'password': 'now-locked'})
        self.assertEqual(response.status_code, 200)
        self.assert_rotated(before)

    def test_unpublishing_moves_every_public_file(self):
        before = self.seen_names()
        response = self.as_owner('post', f'/api/v1/galleries/{self.slug}/publish/', {'is_published': False})
        self.assertEqual(response.status_code, 200)
        self.assert_rotated(before)

    def test_a_password_set_through_the_gallery_patch_moves_every_public_file(self):
        before = self.seen_names()
        response = self.as_owner('patch', f'/api/v1/galleries/{self.slug}/',
                              {'is_password_protected': True, 'password': 'patched-pass'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_rotated(before)

    def test_the_new_urls_are_what_an_unlocked_visitor_gets(self):
        before = self.seen_names()
        self.as_owner('post', f'/api/v1/galleries/{self.slug}/set-password/', {'password': 'now-locked'})
        token = self.unlock(password='now-locked').data['access_token']
        payload = self.client.get(self.base, HTTP_AUTHORIZATION=f'Bearer {token}')
        text = repr(payload.data)
        for old in before:
            self.assertNotIn(old, text)
        self.assertIn(self.gallery.__class__.objects.get(pk=self.gallery.pk).media_token, text)

    def test_a_harmless_edit_moves_nothing(self):
        before = self.seen_names()
        self.as_owner('patch', f'/api/v1/galleries/{self.slug}/', {'title': 'Renamed'})
        self.assertEqual(self.seen_names(), before)


class DevMediaServingTests(SecurityBase):
    """Row 83: the DEBUG /media/ route is not a back door to private files."""

    def serve(self, url):
        """Status code the DEBUG route answers (a raised Http404 is Django's 404 page)."""
        from django.http import Http404
        from apps.core.media import serve_media
        path, _, query = url.partition('?')
        request = RequestFactory().get(path, dict(p.split('=', 1) for p in query.split('&') if p))
        try:
            return serve_media(request, path[len('/media/'):])
        except Http404:
            return mock.Mock(status_code=404)

    def test_a_public_derivative_is_served(self):
        response = self.serve(PublicMediaStorage().url(self.photo.display_file.name))
        self.assertEqual(response.status_code, 200)

    def test_an_original_without_a_signature_is_not_served(self):
        response = self.serve('/media/' + self.photo.original_file.name)
        self.assertEqual(response.status_code, 404)

    def test_a_download_master_and_a_guessed_original_are_not_served(self):
        guessed = self.photo.display_file.name.replace('_display.webp', '_original.jpg')
        for name in (self.photo.download_file.name, guessed):
            self.assertEqual(self.serve('/media/' + name).status_code, 404)

    def test_the_signed_url_the_owner_gets_works_and_a_tampered_one_does_not(self):
        url = self.photo.original_file.url
        self.assertIn('sig=', url)
        self.assertEqual(self.serve(url).status_code, 200)
        other = self.photo2.original_file.name
        forged = '/media/' + other + '?' + url.split('?', 1)[1]
        self.assertEqual(self.serve(forged).status_code, 404)

    def test_a_signed_url_expires(self):
        url = self.photo.original_file.url
        with mock.patch('django.core.signing.time.time', return_value=time.time() + 2 * 3600):
            self.assertEqual(self.serve(url).status_code, 404)


class ContactAllowListTests(SecurityBase):
    """Row 80 (SEC-03): an allowed contact proves the address (emailed one-time code) before a download token."""

    def setUp(self):
        super().setUp()
        from django.core import mail
        self.outbox = mail.outbox
        self.gallery.is_password_protected = False
        self.gallery.password_hash = None
        self.gallery.design_settings = {'downloads': {'restrict_contacts': True, 'allowed_emails': ['vip@example.com']},
                                        'privacy': {'pin_limit': 10}}
        self.gallery.save()

    def ask(self, email, pin=PIN, code=None, client=None):
        body = {'email': email, 'pin': pin}
        if code is not None:
            body['email_code'] = code
        return (client or self.client).post(f'{self.base}download-access/', body, format='json')

    def sent_code(self):
        import re
        self.assertTrue(self.outbox, 'no code email was sent')
        return re.search(r'\b(\d{6})\b', self.outbox[-1].body).group(1)

    def test_typing_an_allowed_email_alone_gives_no_token(self):
        response = self.ask('vip@example.com')
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['code'], 'email_verification_required')
        self.assertNotIn('download_token', response.data)
        self.assertEqual(self.outbox[-1].to, ['vip@example.com'])
        self.assertNotIn(self.sent_code(), repr(response.data))

    def test_the_emailed_code_earns_the_token(self):
        self.ask('vip@example.com')
        granted = self.ask('vip@example.com', code=self.sent_code())
        self.assertEqual(granted.status_code, 200, granted.data)
        self.assertTrue(granted.data['download_token'])

    def test_a_wrong_code_is_refused_and_five_end_it(self):
        self.ask('vip@example.com')
        code = self.sent_code()
        wrong = self.ask('vip@example.com', code='000000' if code != '000000' else '111111')
        self.assertEqual((wrong.status_code, wrong.data['code']), (401, 'invalid_email_code'))
        for _ in range(4):
            self.ask('vip@example.com', code='999999' if code != '999999' else '888888')
        # 7F: five wrong codes also lock this client (429); from another address the
        # right code still fails, because the code itself is used up.
        self.assertEqual(self.ask('vip@example.com', code=code).status_code, 429)
        self.assertEqual(self.ask('vip@example.com', code=code, client=self.visitor('192.0.2.77')).status_code, 401)

    def test_a_code_is_bound_to_its_address(self):
        self.gallery.design_settings['downloads']['allowed_emails'] = ['vip@example.com', 'other@example.com']
        self.gallery.save()
        self.ask('vip@example.com')
        code = self.sent_code()
        self.assertEqual(self.ask('other@example.com', code=code).status_code, 401)

    def test_an_address_not_on_the_list_gets_no_email(self):
        response = self.ask('stranger@example.com')
        self.assertEqual((response.status_code, response.data['code']), (403, 'email_not_authorized'))
        self.assertEqual(self.outbox, [])

    def test_the_pin_use_is_counted_once_for_the_two_steps(self):
        self.ask('vip@example.com')
        self.ask('vip@example.com', code=self.sent_code())
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.design_settings['privacy']['pin_use_count'], 1)

    def test_codes_cannot_be_requested_without_end(self):
        codes = [self.ask('vip@example.com').status_code for _ in range(4)]
        self.assertEqual(codes[:3], [202] * 3)
        self.assertEqual(codes[3], 429)
        self.assertEqual(len(self.outbox), 3)


class FileLinkLifetimeTests(SecurityBase):
    """A ZIP file link is minted fresh on every status poll and clicked at once: it lives an hour, not a week."""

    def test_a_file_link_lives_one_hour(self):
        from django.conf import settings
        from apps.clients.download_access import download_file_url_ttl
        self.assertEqual(download_file_url_ttl(), 3600)
        self.assertEqual(settings.DOWNLOAD_JOB_TTL_SECONDS, 7 * 24 * 3600)     # the job and its emailed link: still a week
