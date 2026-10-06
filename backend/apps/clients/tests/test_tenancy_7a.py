# backend/apps/clients/tests/test_tenancy_7a.py
"""
CHUNK 7-A (tenancy) - the public side.

  1. Favorites by typed email (SEC-02, debt rows 5 and 79): a visitor who types
     someone else's email can never read, rename, delete or add photos to that
     person's lists. A list belongs to the key that made it (the browser's
     client_uid, or the unlock token when no client_uid is sent); an email is a
     label for the photographer, never a credential. Kept from 6.4-B: the same
     device (same client_uid) sees its hearts on a return visit, also on a
     protected gallery with a new unlock token, and one email has only one
     default list.
  2. Share links never bypass the gallery password or the download PIN: the
     emailed ready link and the file links minted from it stop working when the
     photographer changes the password or the PIN.
  3. Gallery states: unpublished, expired, deactivated and password-protected
     galleries answer every public route without content; the public payload
     never carries an original/private storage path.
"""
from datetime import timedelta

import bcrypt
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status

from apps.clients.models import Favorite, FavoriteList
from apps.clients.tests.test_favorite_lists import FavBase
from apps.clients.tests.test_ready_link_protected_1r5e import ProtectedGalleryBase

VICTIM = 'victim@example.com'


class FavoritesByTypedEmailOpenGalleryTests(FavBase):
    """Open gallery: the victim hearted from their browser; the attacker only knows the email."""

    def setUp(self):
        super().setUp()
        self.v = self.visitor()
        self.heart(self.v, 'victim-uid', self.photos[0], email=VICTIM)
        self.heart(self.v, 'victim-uid', self.photos[1])
        self.victim_list = FavoriteList.objects.get(client_key='victim-uid')
        self.attacker = self.visitor()

    def victim_photos(self):
        return set(self.victim_list.favorites.values_list('media_asset_id', flat=True))

    def test_typed_email_does_not_reveal_the_victims_hearts(self):
        got = self.attacker.get(f'{self.base}favorites/', {'client_uid': 'attacker-uid', 'email': VICTIM})
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.data['favorited_ids'], [])

    def test_typed_email_does_not_list_the_victims_lists(self):
        got = self.attacker.get(f'{self.base}favorites/lists/', {'client_uid': 'attacker-uid', 'email': VICTIM})
        self.assertEqual((got.status_code, got.data['results']), (200, []))

    def test_typed_email_cannot_open_the_victims_list(self):
        got = self.attacker.get(
            f'{self.base}favorites/lists/{self.victim_list.id}/', {'client_uid': 'attacker-uid', 'email': VICTIM})
        self.assertEqual(got.status_code, 404)

    def test_typed_email_cannot_rename_the_victims_list(self):
        got = self.attacker.patch(
            f'{self.base}favorites/lists/{self.victim_list.id}/',
            {'client_uid': 'attacker-uid', 'email': VICTIM, 'name': 'pwned'}, format='json')
        self.assertEqual(got.status_code, 404)
        self.victim_list.refresh_from_db()
        self.assertEqual(self.victim_list.name, 'My Favorites')

    def test_typed_email_cannot_delete_the_victims_list(self):
        got = self.attacker.delete(
            f'{self.base}favorites/lists/{self.victim_list.id}/',
            {'client_uid': 'attacker-uid', 'email': VICTIM}, format='json')
        self.assertEqual(got.status_code, 404)
        self.assertTrue(FavoriteList.objects.filter(pk=self.victim_list.pk).exists())

    def test_typed_email_cannot_add_photos_to_the_victims_list(self):
        response = self.heart(self.attacker, 'attacker-uid', self.photos[3], email=VICTIM)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data['list_id'], str(self.victim_list.id))
        self.assertEqual(self.victim_photos(), {self.photos[0].id, self.photos[1].id})

    def test_typed_email_cannot_target_the_victims_list_by_id(self):
        response = self.heart(self.attacker, 'attacker-uid', self.photos[3], email=VICTIM, list_id=str(self.victim_list.id))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.victim_photos(), {self.photos[0].id, self.photos[1].id})

    def test_typed_email_cannot_remove_the_victims_hearts(self):
        response = self.attacker.delete(
            f'{self.base}favorites/',
            {'client_uid': 'attacker-uid', 'email': VICTIM, 'media_asset_id': str(self.photos[0].id)}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.victim_photos(), {self.photos[0].id, self.photos[1].id})

    def test_a_guest_list_given_the_victims_email_is_not_merged_into_the_victims_list(self):
        self.heart(self.attacker, 'attacker-uid', self.photos[3])                # attacker's guest list
        self.heart(self.attacker, 'attacker-uid', self.photos[4], email=VICTIM)  # then "gives" the email
        self.assertEqual(self.victim_photos(), {self.photos[0].id, self.photos[1].id})
        attacker_photos = set(Favorite.objects.filter(client_key='attacker-uid').values_list('media_asset_id', flat=True))
        self.assertEqual(attacker_photos, {self.photos[3].id, self.photos[4].id})

    def test_a_new_list_under_the_victims_email_does_not_see_the_victims_names(self):
        # a 409 "already have a list with that name" would confirm the victim's list exists
        response = self.attacker.post(
            f'{self.base}favorites/lists/', {'client_uid': 'attacker-uid', 'email': VICTIM, 'name': 'My Favorites'},
            format='json')
        self.assertEqual(response.status_code, 201, response.data)

    def test_one_email_still_has_only_one_default_list(self):
        self.heart(self.attacker, 'attacker-uid', self.photos[2], email=VICTIM)
        self.assertEqual(
            FavoriteList.objects.filter(gallery=self.gallery, email__iexact=VICTIM, is_default=True).count(), 1)

    def test_the_same_browser_still_sees_its_own_hearts(self):
        got = self.v.get(f'{self.base}favorites/', {'client_uid': 'victim-uid'})
        self.assertEqual(set(got.data['favorited_ids']), {str(self.photos[0].id), str(self.photos[1].id)})
        self.assertEqual(got.data['email'], VICTIM)

    def test_an_oversized_client_uid_is_a_400_not_a_500(self):
        # the heart POST already capped it (FavoriteToggleSerializer); creating a list did not
        response = self.visitor().post(
            f'{self.base}favorites/lists/', {'client_uid': 'x' * 129, 'name': 'Picks'}, format='json')
        self.assertEqual((response.status_code, response.data.get('code')), (400, 'client_uid_invalid'))
        self.assertEqual(self.visitor().get(f'{self.base}favorites/', {'client_uid': 'x' * 129}).status_code, 400)


class FavoritesByTypedEmailProtectedGalleryTests(FavBase):
    """Protected gallery: the attacker also knows the gallery password."""

    def setUp(self):
        super().setUp()
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'pw', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])

    def unlock(self, email=None):
        cache.clear()
        body = {'password': 'pw', **({'email': email} if email else {})}
        response = self.client_class().post(f'{self.base}unlock/', body, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['access_token']

    def call(self, method, path, token, data=None, **kwargs):
        client = self.client_class()
        return getattr(client, method)(path, data or {}, HTTP_AUTHORIZATION=f'Bearer {token}', **kwargs)

    def heart_with(self, token, asset, **extra):
        return self.call('post', f'{self.base}favorites/', token, {'media_asset_id': str(asset.id), **extra}, format='json')

    def favorited(self, token, **params):
        response = self.call('get', f'{self.base}favorites/', token, params)
        self.assertEqual(response.status_code, 200, response.data)
        return set(response.data['favorited_ids'])

    def test_unlocking_with_the_victims_email_does_not_reveal_their_hearts(self):
        victim = self.unlock(email=VICTIM)
        self.heart_with(victim, self.photos[0], client_uid='victim-device')
        attacker = self.unlock(email=VICTIM)                    # the unlock email is typed, never verified
        self.assertEqual(self.favorited(attacker), set())
        self.assertEqual(self.favorited(attacker, client_uid='attacker-device'), set())
        lists = self.call('get', f'{self.base}favorites/lists/', attacker).data['results']
        self.assertEqual(lists, [])

    def test_a_claimed_email_param_does_not_reveal_their_hearts(self):
        victim = self.unlock(email=VICTIM)
        self.heart_with(victim, self.photos[0])                 # legacy client: no client_uid
        attacker = self.unlock()
        self.assertEqual(self.favorited(attacker, email=VICTIM), set())

    def test_the_same_device_sees_its_hearts_with_a_new_unlock_token(self):
        first = self.unlock(email=VICTIM)
        self.heart_with(first, self.photos[0], client_uid='victim-device')
        self.heart_with(first, self.photos[1], client_uid='victim-device')
        second = self.unlock()                                  # tab closed: new token, same browser storage
        self.assertNotEqual(first, second)
        self.assertEqual(self.favorited(second, client_uid='victim-device'), {str(self.photos[0].id), str(self.photos[1].id)})
        self.heart_with(second, self.photos[2], client_uid='victim-device')
        self.assertEqual(FavoriteList.objects.count(), 1)       # hearting again never makes a second list

    def test_the_device_id_alone_is_not_enough_without_an_unlock(self):
        token = self.unlock()
        self.heart_with(token, self.photos[0], client_uid='victim-device')
        response = self.client_class().get(f'{self.base}favorites/', {'client_uid': 'victim-device'})
        self.assertEqual(response.status_code, 401)

    def test_hearts_made_with_the_token_only_follow_the_device_once_both_are_sent(self):
        token = self.unlock(email=VICTIM)
        self.heart_with(token, self.photos[0])                   # made before the device id was sent
        self.assertEqual(self.favorited(token, client_uid='victim-device'), {str(self.photos[0].id)})
        later = self.unlock()
        self.assertEqual(self.favorited(later, client_uid='victim-device'), {str(self.photos[0].id)})
        self.assertEqual(FavoriteList.objects.get().email, VICTIM)


class ShareLinksNeverBypassGatesTests(ProtectedGalleryBase):
    """The emailed ready link (job key) and its file links after the photographer changes a gate."""

    def change_password(self):
        self.gallery.password_hash = bcrypt.hashpw(b'new-gallery-pass', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['password_hash'])

    def change_pin(self):
        self.gallery.download_pin_hash = bcrypt.hashpw(b'9876', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['download_pin_hash'])

    def test_the_ready_link_works_before_any_change(self):
        job, key = self.make_job()
        self.assertEqual(self.fresh().get(self.status_url(job), {'link_token': key}).status_code, 200)

    def test_the_ready_link_stops_after_a_password_change(self):
        job, key = self.make_job()
        self.change_password()
        response = self.fresh().get(self.status_url(job), {'link_token': key})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, getattr(response, 'data', None))

    def test_the_ready_link_stops_after_a_pin_change(self):
        job, key = self.make_job()
        self.change_pin()
        response = self.fresh().get(self.status_url(job), {'link_token': key})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, getattr(response, 'data', None))

    def test_a_minted_file_link_stops_after_a_password_change(self):
        job, key = self.make_job()
        file_url = self.fresh().get(self.status_url(job), {'link_token': key}).data['files'][0]['url']
        self.change_password()
        self.assertNotEqual(self.fresh().get(file_url).status_code, status.HTTP_200_OK)

    def test_turning_the_password_off_keeps_the_link_working(self):
        job, key = self.make_job()
        self.gallery.is_password_protected = False
        self.gallery.save(update_fields=['is_password_protected'])
        self.assertEqual(self.fresh().get(self.status_url(job), {'link_token': key}).status_code, 200)

    def test_an_expired_or_unpublished_gallery_refuses_the_link(self):
        job, key = self.make_job()
        for field, value in (('expires_at', timezone.now() - timedelta(minutes=1)), ('is_published', False)):
            original = getattr(self.gallery, field)
            setattr(self.gallery, field, value)
            self.gallery.save(update_fields=[field])
            self.assertEqual(self.fresh().get(self.status_url(job), {'link_token': key}).status_code, 404, field)
            setattr(self.gallery, field, original)
            self.gallery.save(update_fields=[field])


class GalleryStatesTests(FavBase):
    """Every public route of an unavailable gallery is a 404 with no content; protected without a token is gated."""

    def routes(self):
        p = self.photos[0].id
        return [
            ('get', f'{self.base}', {}),
            ('get', f'{self.base}photos/', {}),
            ('get', f'{self.base}favorites/', {'client_uid': 'u'}),
            ('get', f'{self.base}favorites/lists/', {'client_uid': 'u'}),
            ('post', f'{self.base}unlock/', {'password': 'x'}),
            ('post', f'{self.base}download-access/', {'email': 'a@example.com'}),
            ('post', f'{self.base}download/', {'email': 'a@example.com'}),
            ('get', f'{self.base}photo/{p}/download/', {}),
            ('get', f'{self.base}video/{p}/stream/', {}),
        ]

    def assert_all_404(self, label):
        for method, path, data in self.routes():
            cache.clear()
            response = getattr(self.client_class(), method)(path, data, format='json') if method == 'post' \
                else self.client_class().get(path, data)
            self.assertEqual(response.status_code, 404, f'{label}: {method} {path}')
            self.assertNotIn(b'photo-0', response.content, f'{label}: {path}')

    def test_unpublished(self):
        Gallery = type(self.gallery)
        Gallery.objects.filter(pk=self.gallery.pk).update(is_published=False, allow_download=True)
        self.assert_all_404('unpublished')

    def test_expired(self):
        type(self.gallery).objects.filter(pk=self.gallery.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1), allow_download=True)
        self.assert_all_404('expired')

    def test_deactivated(self):
        type(self.gallery).objects.filter(pk=self.gallery.pk).update(is_active=False, allow_download=True)
        self.assert_all_404('deactivated')

    def test_another_photographers_username_with_this_slug(self):
        other = type(self.owner).objects.create_user(username='otherphoto', email='o@kyapture.com', password='Sturdy-Pass-8842!')
        response = self.client_class().get(f'/api/v1/public/{other.username}/{self.gallery.slug}/')
        self.assertEqual(response.status_code, 404)

    def test_password_protected_without_a_token_shows_only_the_gate(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'pw', bcrypt.gensalt()).decode()
        self.gallery.allow_download = True
        self.gallery.save()
        locked = self.client_class().get(self.base)
        self.assertEqual(set(locked.data), {'requires_password', 'title', 'branding_color'})
        for path, params in ((f'{self.base}photos/', {}), (f'{self.base}favorites/', {'client_uid': 'u'}),
                             (f'{self.base}photo/{self.photos[0].id}/download/', {}),
                             (f'{self.base}video/{self.photos[0].id}/stream/', {})):
            self.assertEqual(self.client_class().get(path, params).status_code, 401, path)
            self.assertEqual(self.client_class().get(path, {**params, 'token': 'forged'}).status_code, 401, path)

    def test_the_public_payload_never_carries_a_private_path(self):
        type(self.gallery).objects.filter(pk=self.gallery.pk).update(allow_download=True)
        body = self.client_class().get(self.base).content.decode()
        body += self.client_class().get(f'{self.base}photos/').content.decode()
        self.assertIn('photo-0.jpg.d.webp', body)            # the public display tier is there...
        for private in ('_original', 'fav-gallery/photo-0.jpg"', 'password_hash', 'download_pin_hash',
                        'client_key', 'allowed_emails'):              # ...the original's path is not
            self.assertNotIn(private, body, private)
