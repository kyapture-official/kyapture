# backend/apps/galleries/tests/test_share_activity_notifications.py
"""
Task 4 — Share, Activity and the dashboard bell.

  SHARE          the canonical link carries no credential and can never bypass
                 a gallery's own gates (published / expiry / password / PIN)
  ACTIVITY       Download Activity + Favorite Activity are durable, owner-only,
                 tenant-isolated and carry useful metadata
  NOTIFICATIONS  the bell is derived from real events, separate from activity,
                 owner-only, coalesced, read-state persisted server-side
"""
import io
import uuid
from datetime import timedelta
from unittest import mock

import bcrypt
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.clients.models import ClientSession, DownloadLog, Favorite
from apps.clients.tests.zip_flow import InlineDownloadJobsMixin, request_zip
from apps.galleries.models import Gallery
from apps.photos import tasks as photo_tasks
from apps.photos.models import MediaAsset, PhotoSet
from apps.subscriptions.models import ManualPayment, SubscriptionPlan
from apps.users.models import Notification

User = get_user_model()


def _asset(gallery, name='a.jpg', media_type='image', photo_set=None, order=0):
    asset = MediaAsset(
        gallery=gallery, media_type=media_type, original_name=name, file_size=100, order=order,
        photo_set=photo_set, processing_status=MediaAsset.ProcessingStatus.READY,
    )
    asset.original_file.save(name, ContentFile(b'ORIGINAL:' + name.encode()), save=False)
    asset.save()
    if media_type == 'image':
        asset.download_file.save(f'{name}.master.jpg', ContentFile(b'MASTER:' + name.encode()), save=False)
        asset.thumbnail_file.save(f'{name}.t.webp', ContentFile(b'T'), save=False)
        asset.display_file.save(f'{name}.d.webp', ContentFile(b'D'), save=False)
        asset.save(update_fields=['download_file', 'thumbnail_file', 'display_file'])
    return asset


class Base(APITestCase):
    def make_user(self, name):
        return User.objects.create_user(email=f'{name}@kyapture.com', password='Sturdy-Pass-8842!',
                                        username=name, display_name=name.title())

    def setUp(self):
        cache.clear()
        self.owner = self.make_user('shareowner')
        self.other = self.make_user('sharestranger')
        self.gallery = Gallery.objects.create(photographer=self.owner, title='Spring Wedding', slug='spring-wedding',
                                              is_published=True, is_active=True, allow_download=True)
        self.base = f'/api/v1/public/{self.owner.username}/{self.gallery.slug}/'

    def public(self, url, **kwargs):
        return self.client_class().get(url, **kwargs)


class GalleryPasswordSettingsTests(Base):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.owner)
        self.url = f'/api/v1/galleries/{self.gallery.slug}/set-password/'

    def test_owner_can_enable_then_remove_password_protection(self):
        enabled = self.client.post(self.url, {'password': 'gallery-secret'}, format='json')
        self.assertEqual(enabled.status_code, status.HTTP_200_OK, enabled.data)
        self.assertEqual(enabled.data['has_password'], True)
        self.gallery.refresh_from_db()
        self.assertTrue(self.gallery.is_password_protected)
        self.assertTrue(self.gallery.password_hash)

        removed = self.client.post(self.url, {'password': None}, format='json')
        self.assertEqual(removed.status_code, status.HTTP_200_OK, removed.data)
        self.gallery.refresh_from_db()
        self.assertFalse(self.gallery.is_password_protected)
        self.assertIsNone(self.gallery.password_hash)

    def test_malformed_password_is_a_clean_400(self):
        response = self.client.post(self.url, {'password': ['not', 'a', 'string']}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid_password')


# ═══════════════════════════════════════════════════════════════════════════
# SHARE
# ═══════════════════════════════════════════════════════════════════════════
class ShareUrlTests(Base):
    @override_settings(FRONTEND_URL='https://app.kyapture.com')
    def test_public_payload_carries_the_canonical_share_url(self):
        response = self.public(self.base)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['share_url'], 'https://app.kyapture.com/g/shareowner/spring-wedding')

    @override_settings(FRONTEND_URL='https://app.kyapture.com')
    def test_owner_payload_has_the_same_canonical_url(self):
        self.client.force_authenticate(user=self.owner)
        data = self.client.get(f'/api/v1/galleries/{self.gallery.slug}/').data
        self.assertEqual(data['share_url'], 'https://app.kyapture.com/g/shareowner/spring-wedding')

    @override_settings(FRONTEND_URL='https://app.kyapture.com')
    def test_share_url_never_depends_on_the_request_host(self):
        response = self.client_class().get(self.base, HTTP_HOST='localhost:8000')
        self.assertTrue(response.data['share_url'].startswith('https://app.kyapture.com/'))
        self.assertNotIn('localhost', response.data['share_url'])

    def test_share_url_has_no_query_fragment_or_credentials(self):
        url = self.public(self.base).data['share_url']
        for forbidden in ('?', '#', 'token', 'pin', 'key=', 'signature', 'X-Amz', '@'):
            self.assertNotIn(forbidden, url)
        self.assertTrue(url.endswith(f'/g/{self.owner.username}/{self.gallery.slug}'))

    def test_share_url_never_embeds_a_session_token_even_after_unlocking(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'secret-pass', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])
        client = self.client_class()
        token = client.post(f'{self.base}unlock/', {'password': 'secret-pass'}, format='json').data['access_token']
        payload = client.get(self.base, HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(payload.status_code, 200)
        self.assertNotIn(token, str(payload.data['share_url']))
        self.assertNotIn(token, str(payload.data))        # the token never rides back inside the gallery payload

    def test_share_url_is_not_built_from_download_or_pin_state(self):
        self.gallery.download_pin_hash = bcrypt.hashpw(b'4821', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['download_pin_hash'])
        self.assertNotIn('4821', str(self.public(self.base).data))


class SharedLinkDoesNotBypassProtectionTests(Base):
    """The shared link IS the normal gallery URL, so it meets every normal gate."""

    def share_path(self):
        return self.public(self.base).data['share_url'] if self.gallery.is_published else None

    def test_password_protected_gallery_still_shows_the_gate(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'secret-pass', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])
        _asset(self.gallery)
        response = self.public(self.base)                      # a stranger opening the shared link
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['requires_password'])
        self.assertNotIn('photos', response.data)
        self.assertNotIn('share_url', response.data)           # nothing about the gallery is handed out pre-unlock
        self.assertNotIn('Spring', str(response.data.get('description', '')))

    def test_manipulating_the_protected_link_does_not_open_it(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'secret-pass', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])
        asset = _asset(self.gallery)
        for query in ('?token=garbage', '?token=', '?unlocked=1', '?password=secret-pass', '?share=1'):
            response = self.public(f'{self.base}{query}')
            self.assertNotIn('photos', response.data, query)
        for suffix in ('photos/', f'photo/{asset.id}/download/'):
            self.assertIn(self.public(f'{self.base}{suffix}').status_code, (401, 403), suffix)
        self.assertEqual(self.public(f'{self.base}photos/?token=garbage').status_code, 401)

    def test_wrong_password_never_yields_a_token(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'secret-pass', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])
        response = self.client_class().post(f'{self.base}unlock/', {'password': 'wrong'}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('access_token', response.data)

    def test_unpublished_gallery_is_not_reachable_through_its_link(self):
        self.gallery.is_published = False
        self.gallery.save(update_fields=['is_published'])
        _asset(self.gallery)
        for suffix in ('', 'photos/', 'favorites/?client_uid=x'):
            self.assertEqual(self.public(f'{self.base}{suffix}').status_code, 404, suffix)

    def test_expired_gallery_is_not_reachable_through_its_link(self):
        self.gallery.expires_at = timezone.now() - timedelta(days=1)
        self.gallery.save(update_fields=['expires_at'])
        self.assertEqual(self.public(self.base).status_code, 404)
        self.assertEqual(self.public(f'{self.base}photos/').status_code, 404)

    def test_the_owner_can_see_the_link_of_a_draft_but_clients_cannot_open_it(self):
        self.gallery.is_published = False
        self.gallery.save(update_fields=['is_published'])
        self.client.force_authenticate(user=self.owner)
        self.assertIn('share_url', self.client.get(f'/api/v1/galleries/{self.gallery.slug}/').data)
        self.assertEqual(self.public(self.base).status_code, 404)

    def test_download_pin_is_not_bypassed_by_having_the_link(self):
        self.gallery.download_pin_hash = bcrypt.hashpw(b'4821', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['download_pin_hash'])
        asset = _asset(self.gallery)
        opened = self.public(self.base)
        self.assertEqual(opened.status_code, 200)                  # browsing is open ...
        self.assertTrue(opened.data['has_download_pin'])
        denied = self.public(f'{self.base}photo/{asset.id}/download/')   # ... downloading still needs the PIN
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(self.client_class().post(f'{self.base}download/', {}, format='json').status_code, 401)
        self.assertFalse(DownloadLog.objects.exists())

    def test_a_shared_link_to_someone_elses_gallery_name_is_a_plain_404(self):
        self.assertEqual(self.public(f'/api/v1/public/{self.other.username}/spring-wedding/').status_code, 404)
        self.assertEqual(self.public(f'/api/v1/public/{self.owner.username}/{uuid.uuid4()}/').status_code, 404)


# ═══════════════════════════════════════════════════════════════════════════
# DOWNLOAD ACTIVITY
# ═══════════════════════════════════════════════════════════════════════════
class DownloadActivityTests(InlineDownloadJobsMixin, Base):
    def setUp(self):
        super().setUp()
        self.gallery.design_settings = {'downloads': {'require_email': False}}
        self.gallery.save(update_fields=['design_settings'])
        self.set_a = PhotoSet.objects.create(gallery=self.gallery, name='Ceremony', order=1)
        self.photo = _asset(self.gallery, 'ring.jpg', photo_set=self.set_a)
        self.video = _asset(self.gallery, 'vows.mp4', media_type='video')
        self.logs = f'/api/v1/galleries/{self.gallery.slug}/download-logs/'

    def as_owner(self):
        self.client.force_authenticate(user=self.owner)
        return self.client

    def test_successful_single_photo_download_creates_exactly_one_log_with_metadata(self):
        response = self.public(f'{self.base}photo/{self.photo.id}/download/', data={'resolution': 'web'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DownloadLog.objects.count(), 1)
        row = self.as_owner().get(self.logs).data['results'][0]
        self.assertEqual(row['download_type'], 'photo')
        self.assertEqual(row['media_asset_name'], 'ring.jpg')
        self.assertEqual(row['scope'], 'Single photo')
        self.assertEqual(row['resolution'], 'web')
        self.assertEqual(row['photo_set_name'], 'Ceremony')            # the photo's set, not blank
        self.assertEqual(row['pin_state'], 'not_required')
        self.assertTrue(row['created_at'])

    def test_successful_single_video_download_is_logged_as_a_video(self):
        self.assertEqual(self.public(f'{self.base}photo/{self.video.id}/download/').status_code, 200)
        row = self.as_owner().get(self.logs).data['results'][0]
        self.assertEqual((row['download_type'], row['scope'], row['media_asset_name']),
                         ('video', 'Single video', 'vows.mp4'))

    def test_successful_gallery_zip_is_logged_with_scope(self):
        self.assertEqual(request_zip(self.client_class(), self.base).status_code, 200)
        self.assertEqual(request_zip(self.client_class(), self.base, {'set_id': str(self.set_a.id)}).status_code, 200)
        rows = {r['scope']: r for r in self.as_owner().get(self.logs).data['results']}
        self.assertEqual(set(rows), {'Entire gallery', 'Set: Ceremony'})
        self.assertIsNone(rows['Entire gallery']['media_asset_name'])
        self.assertEqual(rows['Set: Ceremony']['photo_set_name'], 'Ceremony')

    def test_pin_state_and_email_are_recorded_for_pin_galleries(self):
        self.gallery.download_pin_hash = bcrypt.hashpw(b'4821', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['download_pin_hash'])
        token = self.client_class().post(f'{self.base}download-access/',
                                         {'email': 'buyer@example.com', 'pin': '4821'}, format='json').data['download_token']
        self.public(f'{self.base}photo/{self.photo.id}/download/', data={'download_token': token})
        row = self.as_owner().get(self.logs).data['results'][0]
        self.assertEqual((row['email'], row['pin_state'], row['pin_verified']), ('buyer@example.com', 'verified', True))

    def test_failed_or_unauthorized_downloads_never_log_a_success(self):
        self.gallery.download_pin_hash = bcrypt.hashpw(b'4821', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['download_pin_hash'])
        self.public(f'{self.base}photo/{self.photo.id}/download/')                      # no PIN
        self.public(f'{self.base}photo/{self.photo.id}/download/', data={'pin': '0000'})  # wrong PIN
        request_zip(self.client_class(), self.base)
        self.public(f'{self.base}photo/{uuid.uuid4()}/download/', data={'pin': '4821'})  # unknown asset
        self.gallery.allow_download = False
        self.gallery.save(update_fields=['allow_download'])
        self.public(f'{self.base}photo/{self.photo.id}/download/', data={'pin': '4821'})  # downloads disabled
        self.assertEqual(DownloadLog.objects.count(), 0)

    def test_each_genuine_download_is_one_row_and_a_refused_retry_adds_none(self):
        self.public(f'{self.base}photo/{self.photo.id}/download/')
        self.public(f'{self.base}photo/{self.photo.id}/download/')       # a second real download
        self.assertEqual(DownloadLog.objects.count(), 2)
        self.gallery.allow_download = False
        self.gallery.save(update_fields=['allow_download'])
        self.public(f'{self.base}photo/{self.photo.id}/download/')        # refused
        self.assertEqual(DownloadLog.objects.count(), 2)

    def test_type_tabs_filter_and_counts(self):
        DownloadLog.objects.create(gallery=self.gallery, download_type='gallery', email='a@example.com')
        DownloadLog.objects.create(gallery=self.gallery, download_type='photo', media_asset=self.photo)
        DownloadLog.objects.create(gallery=self.gallery, download_type='photo', media_asset=self.photo)
        DownloadLog.objects.create(gallery=self.gallery, download_type='video', media_asset=self.video)
        client = self.as_owner()
        for kind, expected in (('gallery', 1), ('photo', 2), ('video', 1)):
            response = client.get(self.logs, {'type': kind})
            self.assertEqual(response.data['count'], expected, kind)
            self.assertTrue(all(r['download_type'] == kind for r in response.data['results']))
        self.assertEqual(client.get(self.logs).data['count'], 4)
        self.assertEqual(client.get(self.logs, {'type': 'photo'}).data['counts'], {'gallery': 1, 'photo': 2, 'video': 1})

    def test_unknown_type_is_a_clear_400(self):
        response = self.as_owner().get(self.logs, {'type': 'zip; DROP TABLE'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'invalid_type')

    def test_owner_only_and_tenant_isolated(self):
        DownloadLog.objects.create(gallery=self.gallery, email='private@example.com', download_type='gallery')
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.get(self.logs).status_code, 404)                          # wrong owner
        self.assertEqual(self.client.get(f'/api/v1/galleries/{uuid.uuid4()}/download-logs/').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/galleries/not-a-real-slug/download-logs/').status_code, 404)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.logs).status_code, 401)                          # unauthenticated
        self.assertNotIn('private@example.com', str(self.public(self.base).data))               # never public

    def test_a_foreign_owners_logs_never_appear_in_my_gallery_view(self):
        theirs = Gallery.objects.create(photographer=self.other, title='Theirs', slug='theirs', is_published=True, is_active=True)
        DownloadLog.objects.create(gallery=theirs, email='theirs@example.com', download_type='gallery')
        DownloadLog.objects.create(gallery=self.gallery, email='mine@example.com', download_type='gallery')
        emails = [r['email'] for r in self.as_owner().get(self.logs).data['results']]
        self.assertEqual(emails, ['mine@example.com'])

    def test_error_bodies_never_leak_internals(self):
        self.client.force_authenticate(user=self.other)
        body = str(self.client.get(self.logs).data)
        self.assertNotIn('Traceback', body)
        self.assertNotIn('DoesNotExist', body)

    def test_the_list_is_paginated_and_query_count_does_not_grow_with_rows(self):
        def run(rows):
            DownloadLog.objects.all().delete()
            for _ in range(rows):
                DownloadLog.objects.create(gallery=self.gallery, download_type='photo', media_asset=self.photo)
            client = self.as_owner()
            from django.db import connection
            from django.test.utils import CaptureQueriesContext
            with CaptureQueriesContext(connection) as queries:
                response = client.get(self.logs, {'type': 'photo'})
            return len(queries), response
        few, _ = run(3)
        many, response = run(25)
        self.assertEqual(few, many)                                            # no N+1
        self.assertEqual(len(response.data['results']), 20)                    # one bounded page
        self.assertIsNotNone(response.data['next'])


# ═══════════════════════════════════════════════════════════════════════════
# FAVORITE ACTIVITY
# ═══════════════════════════════════════════════════════════════════════════
class FavoriteActivityTests(Base):
    def setUp(self):
        super().setUp()
        self.photos = [_asset(self.gallery, f'p{i}.jpg', order=i) for i in range(4)]
        self.activity = f'/api/v1/galleries/{self.gallery.slug}/favorites/'

    def favorite(self, client_uid, asset):
        return self.client_class().post(f'{self.base}favorites/', {'media_asset_id': str(asset.id), 'client_uid': client_uid}, format='json')

    def as_owner(self):
        self.client.force_authenticate(user=self.owner)
        return self.client

    def test_lists_group_each_clients_favorites_with_counts_and_timestamps(self):
        for asset in self.photos[:3]:
            self.assertEqual(self.favorite('client-one', asset).status_code, 200)
        self.favorite('client-two', self.photos[0])
        response = self.as_owner().get(self.activity, {'group': 'client'})
        self.assertEqual(response.status_code, 200)
        rows = response.data['results']
        self.assertEqual(sorted(r['photo_count'] for r in rows), [1, 3])
        for row in rows:
            self.assertTrue(row['created_at'] and row['updated_at'])
            self.assertLessEqual(row['created_at'], row['updated_at'])
            self.assertEqual(set(row), {'id', 'name', 'email', 'visitor_name', 'photo_count', 'thumbnail_url', 'created_at', 'updated_at'})
            self.assertEqual(row['name'], 'My Favorites')

    def test_favoriting_more_updates_the_list_and_unfavoriting_shrinks_it(self):
        self.favorite('client-one', self.photos[0])
        first = self.as_owner().get(self.activity, {'group': 'client'}).data['results'][0]
        self.favorite('client-one', self.photos[1])
        second = self.as_owner().get(self.activity, {'group': 'client'}).data['results'][0]
        self.assertEqual((first['id'], first['photo_count'], second['photo_count']), (second['id'], 1, 2))
        self.assertGreaterEqual(second['updated_at'], first['updated_at'])
        self.assertEqual(second['created_at'], first['created_at'])
        self.client_class().delete(f'{self.base}favorites/', {'media_asset_id': str(self.photos[1].id), 'client_uid': 'client-one'}, format='json')
        self.assertEqual(self.as_owner().get(self.activity, {'group': 'client'}).data['results'][0]['photo_count'], 1)

    def test_the_same_client_can_revisit_and_see_their_list(self):
        self.favorite('client-one', self.photos[0])
        self.favorite('client-one', self.photos[2])
        revisit = self.client_class().get(f'{self.base}favorites/', {'client_uid': 'client-one'})
        self.assertEqual(sorted(revisit.data['favorited_ids']), sorted([str(self.photos[0].id), str(self.photos[2].id)]))
        stranger = self.client_class().get(f'{self.base}favorites/', {'client_uid': 'someone-else'})
        self.assertEqual(stranger.data['favorited_ids'], [])

    def test_list_detail_shows_that_lists_photos_only(self):
        self.favorite('client-one', self.photos[0]); self.favorite('client-one', self.photos[1])
        self.favorite('client-two', self.photos[2])
        rows = self.as_owner().get(self.activity, {'group': 'client'}).data['results']
        big = next(r for r in rows if r['photo_count'] == 2)
        detail = self.as_owner().get(self.activity, {'list': big['id']})
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(sorted(r['original_name'] for r in detail.data['results']), ['p0.jpg', 'p1.jpg'])

    def test_email_from_an_unlocked_session_is_shown_on_the_list(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'pw-pw-pw', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])
        session = ClientSession.objects.issue(gallery=self.gallery, email='fan@example.com')
        client = self.client_class()
        client.post(f'{self.base}favorites/', {'media_asset_id': str(self.photos[0].id)}, format='json',
                    HTTP_AUTHORIZATION=f'Bearer {session.raw_token}')
        row = self.as_owner().get(self.activity, {'group': 'client'}).data['results'][0]
        self.assertEqual(row['email'], 'fan@example.com')

    def test_a_session_token_is_never_exposed_through_activity(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'pw-pw-pw', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])
        session = ClientSession.objects.issue(gallery=self.gallery, email='fan@example.com')
        self.client_class().post(f'{self.base}favorites/', {'media_asset_id': str(self.photos[0].id)}, format='json',
                                 HTTP_AUTHORIZATION=f'Bearer {session.raw_token}')
        owner = self.as_owner()
        for params in ({'group': 'client'}, {}, {'list': self.as_owner().get(self.activity, {'group': 'client'}).data['results'][0]['id']}):
            body = str(owner.get(self.activity, params).data)
            self.assertNotIn(session.raw_token, body)
            self.assertNotIn(session.access_token, body)
            self.assertNotIn('client_key', body)

    def test_cross_tenant_and_foreign_ids_are_rejected(self):
        self.favorite('client-one', self.photos[0])
        list_id = self.as_owner().get(self.activity, {'group': 'client'}).data['results'][0]['id']

        self.client.force_authenticate(user=self.other)                                         # wrong owner
        self.assertEqual(self.client.get(self.activity, {'group': 'client'}).status_code, 404)
        self.assertEqual(self.client.get(self.activity, {'list': list_id}).status_code, 404)

        theirs = Gallery.objects.create(photographer=self.other, title='Theirs', slug='theirs', is_published=True, is_active=True)
        their_activity = f'/api/v1/galleries/{theirs.slug}/favorites/'
        self.assertEqual(self.client.get(their_activity, {'list': list_id}).status_code, 404)    # my list id on THEIR gallery
        self.assertEqual(self.client.get(their_activity, {'group': 'client'}).data['count'], 0)

        owner = self.as_owner()
        for bad in (str(uuid.uuid4()), 'x' * 24, '', '../etc/passwd', 'a' * 500):
            expected = 404 if bad else 200
            self.assertEqual(owner.get(self.activity, {'list': bad}).status_code, expected, bad)

        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.activity).status_code, 401)

    def test_public_endpoints_never_expose_favorite_activity(self):
        self.favorite('client-one', self.photos[0])
        self.assertIn(self.client_class().get(self.activity).status_code, (401, 403, 404))
        self.assertNotIn('client-one', str(self.public(self.base).data))

    def test_no_n_plus_one_on_the_grouped_view(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def measure(clients):
            Favorite.objects.all().delete()
            for i in range(clients):
                self.favorite(f'c{i}', self.photos[i % 4])
            owner = self.as_owner()
            with CaptureQueriesContext(connection) as queries:
                owner.get(self.activity, {'group': 'client'})
            return len(queries)
        self.assertEqual(measure(2), measure(15))


# ═══════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS (the bell)
# ═══════════════════════════════════════════════════════════════════════════
class NotificationEventTests(Base):
    def setUp(self):
        super().setUp()
        self.gallery.design_settings = {'downloads': {'require_email': False}}
        self.gallery.save(update_fields=['design_settings'])
        self.asset = _asset(self.gallery, 'one.jpg')

    def mine(self, user=None, **filters):
        return Notification.objects.filter(user=user or self.owner, **filters)

    def test_a_real_download_creates_one_notification_for_the_owner_only(self):
        self.public(f'{self.base}photo/{self.asset.id}/download/')
        note = self.mine().get()
        self.assertEqual(note.kind, 'download')
        self.assertEqual(note.message, 'Photo downloaded by a client')
        self.assertFalse(note.is_read)
        self.assertEqual(self.mine(self.other).count(), 0)
        self.assertEqual(DownloadLog.objects.count(), 1)             # the durable record exists independently

    def test_each_download_gets_its_own_notification_naming_who_downloaded(self):
        # Download text names the client, so downloads are not rolled up into "N downloads".
        for _ in range(3):
            DownloadLog.objects.create(gallery=self.gallery, download_type='photo', media_asset=self.asset, email='buyer@example.com')
        notes = self.mine(kind='download')
        self.assertEqual(notes.count(), 3)
        self.assertEqual({n.message for n in notes}, {'Photo downloaded by buyer@example.com'})
        self.assertEqual(DownloadLog.objects.count(), 3)

    def test_after_reading_a_new_event_creates_a_fresh_notification(self):
        DownloadLog.objects.create(gallery=self.gallery, download_type='photo', media_asset=self.asset)
        self.mine().update(is_read=True)
        DownloadLog.objects.create(gallery=self.gallery, download_type='photo', media_asset=self.asset)
        self.assertEqual(self.mine().count(), 2)
        self.assertEqual(self.mine(is_read=False).count(), 1)

    def test_different_galleries_do_not_coalesce_together(self):
        other_gallery = Gallery.objects.create(photographer=self.owner, title='Second', slug='second', is_published=True, is_active=True)
        DownloadLog.objects.create(gallery=self.gallery, download_type='gallery')
        DownloadLog.objects.create(gallery=other_gallery, download_type='gallery')
        self.assertEqual(self.mine().count(), 2)

    def test_favorite_event(self):
        Favorite.objects.create(gallery=self.gallery, media_asset=self.asset, client_key='k1', email='fan@example.com')
        note = self.mine().get()
        self.assertEqual(note.kind, 'favorite')
        self.assertIn('fan@example.com', note.message)

    def test_bell_notifications_do_not_depend_on_email_preferences(self):
        self.assertFalse(self.owner.notify_downloads)                 # email alert is off (default) ...
        DownloadLog.objects.create(gallery=self.gallery, download_type='photo', media_asset=self.asset)
        self.assertEqual(self.mine().count(), 1)                       # ... the in-app bell still records it

    def test_payment_events(self):
        staff = User.objects.create_user(email='staff@kyapture.com', password='Sturdy-Pass-8842!', username='staffer', is_staff=True)
        plan = SubscriptionPlan.objects.get(key='pro')
        for action, fragment in (('approve', 'approved'), ('reject', 'could not be approved')):
            payment = ManualPayment(user=self.owner, plan=plan, amount=plan.price)
            payment.payment_proof.save('p.png', ContentFile(b'x'), save=False)
            payment.save()
            self.client.force_authenticate(user=staff)
            response = self.client.post(f'/api/v1/subscriptions/payments/{payment.id}/review/', {'action': action}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertIn(fragment, self.mine(kind='payment').first().message)
        self.assertEqual(self.mine(kind='payment').count(), 2)
        self.assertEqual(self.mine(User.objects.get(username='staffer')).count(), 0)

    def test_publishing_creates_a_notification_only_on_the_draft_to_published_transition(self):
        self.gallery.is_published = False
        self.gallery.save(update_fields=['is_published'])
        self.client.force_authenticate(user=self.owner)
        url = f'/api/v1/galleries/{self.gallery.slug}/publish/'
        self.assertEqual(self.client.post(url, {'is_published': True}, format='json').status_code, 200)
        self.assertEqual(self.mine(kind='published').count(), 1)
        self.client.post(url, {'is_published': True}, format='json')            # already published -> nothing new
        self.client.post(url, {'is_published': False}, format='json')           # unpublishing -> nothing
        self.assertEqual(self.mine(kind='published').count(), 1)
        self.client.patch(f'/api/v1/galleries/{self.gallery.slug}/', {'is_published': True}, format='json')
        self.assertEqual(self.mine(kind='published').count(), 2)                # the PATCH path fires too

    def test_publish_rejects_non_boolean_values_instead_of_storing_them_as_true(self):
        self.client.force_authenticate(user=self.owner)
        url = f'/api/v1/galleries/{self.gallery.slug}/publish/'
        self.gallery.is_published = False
        self.gallery.save(update_fields=['is_published'])
        response = self.client.post(url, {'is_published': 'false'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.gallery.refresh_from_db()
        self.assertFalse(self.gallery.is_published)

    def _png(self):
        out = io.BytesIO()
        Image.new('RGB', (200, 120), (10, 80, 60)).save(out, format='JPEG')
        return out.getvalue()

    def test_media_processing_completion_creates_a_coalesced_notification(self):
        for name in ('x.jpg', 'y.jpg'):
            asset = MediaAsset(gallery=self.gallery, media_type='image', original_name=name, file_size=10,
                               processing_status=MediaAsset.ProcessingStatus.PENDING)
            asset.original_file.save(name, ContentFile(self._png()), save=False)
            asset.save()
            photo_tasks.process_photo_asset(asset.id)
        note = self.mine(kind='processing_done').get()
        self.assertEqual(note.count, 2)
        self.assertIn('2 items finished processing', note.message)

    def test_processing_failure_notifies_only_once_retries_are_exhausted(self):
        asset = MediaAsset(gallery=self.gallery, media_type='image', original_name='bad.jpg', file_size=10,
                           processing_status=MediaAsset.ProcessingStatus.PENDING)
        asset.original_file.save('bad.jpg', ContentFile(b'not an image'), save=False)
        asset.save()
        with self.assertRaises(Exception):
            photo_tasks.process_photo_asset(asset.id)                # first failure: a retry may still fix it
        self.assertEqual(self.mine(kind='processing_failed').count(), 0)
        asset.refresh_from_db()
        asset.processing_status = MediaAsset.ProcessingStatus.PENDING
        asset.save(update_fields=['processing_status'])
        photo_tasks.process_photo_asset.push_request(retries=photo_tasks.process_photo_asset.max_retries)
        try:
            with self.assertRaises(Exception):
                photo_tasks.process_photo_asset(asset.id)
        finally:
            photo_tasks.process_photo_asset.pop_request()
        self.assertEqual(self.mine(kind='processing_failed').count(), 1)

    def test_a_bell_failure_never_breaks_the_event_that_caused_it(self):
        with mock.patch('apps.users.notification_service.Notification.objects.create', side_effect=RuntimeError('db hiccup')):
            with self.assertLogs('apps.users.notification_service', level='ERROR'):
                response = self.public(f'{self.base}photo/{self.asset.id}/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DownloadLog.objects.count(), 1)

    def test_no_notification_is_invented_for_failed_downloads(self):
        self.gallery.allow_download = False
        self.gallery.save(update_fields=['allow_download'])
        self.public(f'{self.base}photo/{self.asset.id}/download/')
        self.assertEqual(self.mine().count(), 0)


class NotificationApiTests(Base):
    URL = '/api/v1/notifications/'

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.owner)
        self.n1 = Notification.objects.create(user=self.owner, kind='download', gallery=self.gallery, message='one')
        self.n2 = Notification.objects.create(user=self.owner, kind='favorite', gallery=self.gallery, message='two')
        self.n3 = Notification.objects.create(user=self.owner, kind='payment', message='three')
        self.theirs = Notification.objects.create(user=self.other, kind='payment', message='not mine')

    def test_list_is_owner_only_newest_first_with_unread_count_and_links(self):
        data = self.client.get(self.URL).data
        self.assertEqual([r['message'] for r in data['results']], ['three', 'two', 'one'])
        self.assertEqual(data['unread_count'], 3)
        links = {r['message']: r['link'] for r in data['results']}
        self.assertEqual(links['one'], f'/dashboard/galleries/{self.gallery.slug}/activities?tab=downloads')
        self.assertEqual(links['two'], f'/dashboard/galleries/{self.gallery.slug}/activities?tab=favorites')
        self.assertEqual(links['three'], '/dashboard/billing')
        self.assertNotIn('not mine', str(data))
        for row in data['results']:
            self.assertEqual(set(row), {'id', 'kind', 'message', 'count', 'is_read', 'timestamp', 'created_at', 'link', 'gallery_slug'})

    def test_unread_count_endpoint_is_lightweight_and_correct(self):
        with self.assertNumQueries(1):                                  # a single indexed COUNT
            data = self.client.get(f'{self.URL}unread-count/').data
        self.assertEqual(data, {'unread_count': 3})

    def test_mark_read_persists_server_side_and_is_idempotent(self):
        first = self.client.post(f'{self.URL}{self.n1.id}/read/')
        self.assertEqual((first.status_code, first.data['unread_count']), (200, 2))
        self.assertEqual(self.client.post(f'{self.URL}{self.n1.id}/read/').data['unread_count'], 2)
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read and self.n1.read_at)
        fresh = self.client_class(); fresh.force_authenticate(user=self.owner)         # "after a refresh"
        rows = {r['message']: r['is_read'] for r in fresh.get(self.URL).data['results']}
        self.assertEqual(rows, {'one': True, 'two': False, 'three': False})
        self.assertEqual([r['message'] for r in fresh.get(self.URL, {'unread': '1'}).data['results']], ['three', 'two'])

    def test_mark_all_read_only_touches_the_callers_rows(self):
        response = self.client.post(f'{self.URL}read-all/')
        self.assertEqual((response.data['marked'], response.data['unread_count']), (3, 0))
        self.theirs.refresh_from_db()
        self.assertFalse(self.theirs.is_read)

    def test_foreign_and_random_ids_are_404_and_change_nothing(self):
        for target in (self.theirs.id, uuid.uuid4()):
            response = self.client.post(f'{self.URL}{target}/read/')
            self.assertEqual(response.status_code, 404, target)
            self.assertEqual(response.data['code'], 'not_found')
        self.theirs.refresh_from_db()
        self.assertFalse(self.theirs.is_read)

    def test_unauthenticated_access_is_refused_everywhere(self):
        self.client.force_authenticate(user=None)
        for method, url in (('get', self.URL), ('get', f'{self.URL}unread-count/'), ('post', f'{self.URL}read-all/'),
                            ('post', f'{self.URL}{self.n1.id}/read/')):
            self.assertEqual(getattr(self.client, method)(url).status_code, 401, url)

    def test_empty_state(self):
        self.client.force_authenticate(user=self.make_user('freshuser'))
        data = self.client.get(self.URL).data
        self.assertEqual((data['results'], data['unread_count'], data['count']), ([], 0, 0))

    def test_pagination_is_bounded_and_there_is_no_n_plus_one(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def measure(extra):
            Notification.objects.filter(user=self.owner).delete()
            for i in range(extra):
                Notification.objects.create(user=self.owner, kind='download', gallery=self.gallery, message=f'm{i}')
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(self.URL)
            return len(queries), response
        few, _ = measure(3)
        many, response = measure(40)
        self.assertEqual(few, many)
        self.assertEqual(len(response.data['results']), 15)
        self.assertIsNotNone(response.data['next'])
        self.assertLessEqual(len(self.client.get(self.URL, {'page_size': 500}).data['results']), 50)

    def test_purge_task_removes_only_old_rows(self):
        old_read = Notification.objects.create(user=self.owner, kind='download', message='old read', is_read=True)
        old_unread = Notification.objects.create(user=self.owner, kind='download', message='old unread')
        Notification.objects.filter(pk=old_read.pk).update(updated_at=timezone.now() - timedelta(days=31))
        Notification.objects.filter(pk=old_unread.pk).update(updated_at=timezone.now() - timedelta(days=31))
        from apps.users.tasks import purge_old_notifications
        self.assertEqual(purge_old_notifications(), 1)
        self.assertTrue(Notification.objects.filter(pk=old_unread.pk).exists())      # unread survives 30 days
        self.assertFalse(Notification.objects.filter(pk=old_read.pk).exists())
        Notification.objects.filter(pk=old_unread.pk).update(updated_at=timezone.now() - timedelta(days=91))
        self.assertEqual(purge_old_notifications(), 1)
