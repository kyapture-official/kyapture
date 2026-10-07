# backend/apps/clients/tests/test_favorite_lists.py
"""
TASK 1R.3 - visitor favorite lists + the photographer's Favorite Activity.

  - the heart stores the visitor's EMAIL and puts the photo in a default
    "My Favorites" list; the email is asked once and remembered server-side
  - lists: create / rename / delete / remove-a-photo / sort - a visitor only ever
    sees and edits their OWN lists, never another visitor's or another gallery's
  - the photographer sees real emails (Guest only when none), grouped by visitor,
    with lists, thumbnails, counts, created/updated; filter + sort
  - "<email> favorited N photos" notifications, per visitor
  - the backfill gives every pre-existing favorite a default list and keeps
    anonymous rows as Guest
  - download activity: real filenames + thumbnails, photo counts, no UUIDs
"""
import importlib
import uuid

import bcrypt
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from rest_framework.test import APITestCase

from apps.clients.models import ClientSession, DownloadLog, Favorite, FavoriteList
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.users.models import Notification

User = get_user_model()


def _asset(gallery, name, order=0):
    asset = MediaAsset(
        gallery=gallery, media_type='image', original_name=name, file_size=10, order=order,
        processing_status='ready', original_file=f'fl/{gallery.slug}/{name}',
        thumbnail_file=f'fl/{gallery.slug}/{name}.thumb.webp', display_file=f'fl/{gallery.slug}/{name}.d.webp',
        medium_file=f'fl/{gallery.slug}/{name}.m.webp',
    )
    asset.save()
    return asset


class FavBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username='favowner', email='favowner@kyapture.com', password='Sturdy-Pass-8842!')
        self.gallery = Gallery.objects.create(
            photographer=self.owner, title='Fav Gallery', slug='fav-gallery', is_published=True, is_active=True)
        self.photos = [_asset(self.gallery, f'photo-{i}.jpg', i) for i in range(5)]
        self.base = f'/api/v1/public/{self.owner.username}/{self.gallery.slug}/'
        self.activity = f'/api/v1/galleries/{self.gallery.slug}/favorites/'

    def visitor(self):
        return self.client_class()

    def heart(self, client, uid, asset, **extra):
        return client.post(f'{self.base}favorites/', {'media_asset_id': str(asset.id), 'client_uid': uid, **extra}, format='json')

    def unheart(self, client, uid, asset, **extra):
        return client.delete(f'{self.base}favorites/', {'media_asset_id': str(asset.id), 'client_uid': uid, **extra}, format='json')

    def lists(self, client, uid, **params):
        return client.get(f'{self.base}favorites/lists/', {'client_uid': uid, **params})

    def as_owner(self):
        self.client.force_authenticate(user=self.owner)
        return self.client


class HeartStoresEmailAndListTests(FavBase):
    def test_first_heart_creates_my_favorites_with_the_visitors_email(self):
        v = self.visitor()
        response = self.heart(v, 'uid-a', self.photos[0], email='Fan@Example.com', name='Fiona')
        self.assertEqual(response.status_code, 200, response.data)
        favorite_list = FavoriteList.objects.get()
        self.assertEqual((favorite_list.name, favorite_list.is_default, favorite_list.email, favorite_list.visitor_name),
                         ('My Favorites', True, 'Fan@Example.com', 'Fiona'))
        favorite = Favorite.objects.get()
        self.assertEqual((favorite.favorite_list_id, favorite.email), (favorite_list.id, 'Fan@Example.com'))
        self.assertEqual(response.data['list_id'], str(favorite_list.id))

    def test_the_email_is_remembered_so_later_hearts_need_not_resend_it(self):
        v = self.visitor()
        self.heart(v, 'uid-a', self.photos[0], email='fan@example.com')
        self.heart(v, 'uid-a', self.photos[1])                              # no email this time
        self.assertEqual(set(Favorite.objects.values_list('email', flat=True)), {'fan@example.com'})
        self.assertEqual(FavoriteList.objects.count(), 1)
        self.assertEqual(Favorite.objects.count(), 2)
        got = v.get(f'{self.base}favorites/', {'client_uid': 'uid-a'})
        self.assertEqual(got.data['email'], 'fan@example.com')              # the client can skip the prompt next time
        self.assertEqual(len(got.data['favorited_ids']), 2)

    def test_a_malformed_email_is_a_400_and_stores_nothing(self):
        for bad in ('nope', 'a@', ['a@b.co'], 42):
            response = self.heart(self.visitor(), 'uid-a', self.photos[0], email=bad)
            self.assertEqual((response.status_code, response.data['code']), (400, 'invalid_email'), bad)
        self.assertFalse(Favorite.objects.exists())

    def test_hearting_twice_is_idempotent(self):
        v = self.visitor()
        self.heart(v, 'uid-a', self.photos[0], email='fan@example.com')
        self.heart(v, 'uid-a', self.photos[0])
        self.assertEqual(Favorite.objects.count(), 1)

    def test_a_photo_from_another_gallery_cannot_be_hearted(self):
        other = Gallery.objects.create(photographer=self.owner, title='Other', slug='other-fav', is_published=True, is_active=True)
        foreign = _asset(other, 'x.jpg')
        response = self.heart(self.visitor(), 'uid-a', foreign, email='fan@example.com')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Favorite.objects.exists())

    def test_heart_off_removes_the_photo_from_all_the_visitors_lists(self):
        v = self.visitor()
        self.heart(v, 'uid-a', self.photos[0], email='fan@example.com')
        extra = v.post(f'{self.base}favorites/lists/', {'name': 'Best', 'client_uid': 'uid-a'}, format='json').data['id']
        self.heart(v, 'uid-a', self.photos[0], list_id=extra)
        self.assertEqual(Favorite.objects.count(), 2)
        response = self.unheart(v, 'uid-a', self.photos[0])
        self.assertEqual(response.data, {'favorited': False})
        self.assertEqual(Favorite.objects.count(), 0)

    def test_removing_from_one_list_keeps_it_in_the_others(self):
        v = self.visitor()
        self.heart(v, 'uid-a', self.photos[0], email='fan@example.com')
        best = v.post(f'{self.base}favorites/lists/', {'name': 'Best', 'client_uid': 'uid-a'}, format='json').data['id']
        self.heart(v, 'uid-a', self.photos[0], list_id=best)
        response = self.unheart(v, 'uid-a', self.photos[0], list_id=best)
        self.assertEqual(response.data, {'favorited': True})                # still in My Favorites -> heart stays red
        self.assertEqual(Favorite.objects.count(), 1)

    def test_protected_gallery_takes_the_email_from_the_unlock_session(self):
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'pw-pw-pw', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])
        session = ClientSession.objects.issue(gallery=self.gallery, email='session@example.com')
        auth = {'HTTP_AUTHORIZATION': f'Bearer {session.raw_token}'}
        response = self.visitor().post(f'{self.base}favorites/', {'media_asset_id': str(self.photos[0].id)}, format='json', **auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FavoriteList.objects.get().email, 'session@example.com')
        # without the unlock session, nothing
        self.assertEqual(self.visitor().post(f'{self.base}favorites/', {'media_asset_id': str(self.photos[0].id)}, format='json').status_code, 401)


class VisitorListManagementTests(FavBase):
    def setUp(self):
        super().setUp()
        self.v = self.visitor()
        self.heart(self.v, 'uid-a', self.photos[0], email='fan@example.com')

    def test_lists_endpoint_returns_summaries_with_thumbnail_count_and_dates(self):
        self.heart(self.v, 'uid-a', self.photos[1])
        (row,) = self.lists(self.v, 'uid-a').data['results']
        self.assertEqual((row['name'], row['photo_count'], row['is_default']), ('My Favorites', 2, True))
        self.assertIn('photo-1.jpg.thumb.webp', row['thumbnail_url'])         # cover = the latest favorite
        self.assertTrue(row['created_at'] and row['updated_at'])
        self.assertNotIn('client_key', row)
        self.assertNotIn('uid-a', str(row))

    def test_create_rename_and_delete_a_list(self):
        created = self.v.post(f'{self.base}favorites/lists/', {'name': '  Album   picks ', 'client_uid': 'uid-a'}, format='json')
        self.assertEqual((created.status_code, created.data['name'], created.data['is_default']), (201, 'Album picks', False))
        list_id = created.data['id']
        renamed = self.v.patch(f'{self.base}favorites/lists/{list_id}/', {'name': 'Final', 'client_uid': 'uid-a'}, format='json')
        self.assertEqual((renamed.status_code, renamed.data['name']), (200, 'Final'))
        deleted = self.v.delete(f'{self.base}favorites/lists/{list_id}/', {'client_uid': 'uid-a'}, format='json')
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(FavoriteList.objects.filter(pk=list_id).exists())

    def test_deleting_a_list_deletes_its_favorites_but_not_the_photos(self):
        default_id = FavoriteList.objects.get().id
        self.v.delete(f'{self.base}favorites/lists/{default_id}/', {'client_uid': 'uid-a'}, format='json')
        self.assertEqual(Favorite.objects.count(), 0)
        self.assertEqual(MediaAsset.objects.filter(gallery=self.gallery).count(), 5)
        # the next heart simply makes a fresh default list
        self.heart(self.v, 'uid-a', self.photos[2])
        self.assertEqual(FavoriteList.objects.get().name, 'My Favorites')

    def test_list_names_are_validated_and_unique_per_visitor(self):
        url = f'{self.base}favorites/lists/'
        for bad in ('', '   ', 'x' * 81, None, 7):
            self.assertEqual(self.v.post(url, {'name': bad, 'client_uid': 'uid-a'}, format='json').status_code, 400, bad)
        self.assertEqual(self.v.post(url, {'name': 'my favorites', 'client_uid': 'uid-a'}, format='json').status_code, 409)
        # a DIFFERENT visitor may use the same name
        self.assertEqual(self.visitor().post(url, {'name': 'My Favorites', 'client_uid': 'uid-b'}, format='json').status_code, 201)

    def test_a_visitor_is_capped_at_20_lists(self):
        url = f'{self.base}favorites/lists/'
        for i in range(19):
            self.assertEqual(self.v.post(url, {'name': f'L{i}', 'client_uid': 'uid-a'}, format='json').status_code, 201)
        self.assertEqual(self.v.post(url, {'name': 'one too many', 'client_uid': 'uid-a'}, format='json').data['code'], 'too_many_lists')

    def test_list_photos_sorted_newest_or_oldest_with_real_filenames(self):
        self.heart(self.v, 'uid-a', self.photos[1]); self.heart(self.v, 'uid-a', self.photos[2])
        list_id = FavoriteList.objects.get().id
        newest = self.v.get(f'{self.base}favorites/lists/{list_id}/', {'client_uid': 'uid-a'})
        self.assertEqual([p['original_name'] for p in newest.data['results']], ['photo-2.jpg', 'photo-1.jpg', 'photo-0.jpg'])
        oldest = self.v.get(f'{self.base}favorites/lists/{list_id}/', {'client_uid': 'uid-a', 'sort': 'oldest'})
        self.assertEqual([p['original_name'] for p in oldest.data['results']], ['photo-0.jpg', 'photo-1.jpg', 'photo-2.jpg'])
        self.assertEqual(newest.data['list']['photo_count'], 3)
        self.assertTrue(all(p['thumbnail_url'] for p in newest.data['results']))
        self.assertNotIn('original_url', newest.data['results'][0])           # still no raw original

    def test_lists_sort_newest_oldest(self):
        for name in ('Second', 'Third'):
            self.v.post(f'{self.base}favorites/lists/', {'name': name, 'client_uid': 'uid-a'}, format='json')
        self.assertEqual([r['name'] for r in self.lists(self.v, 'uid-a', sort='newest').data['results']], ['Third', 'Second', 'My Favorites'])
        self.assertEqual([r['name'] for r in self.lists(self.v, 'uid-a', sort='oldest').data['results']], ['My Favorites', 'Second', 'Third'])


class VisitorsOnlySeeTheirOwnTests(FavBase):
    def setUp(self):
        super().setUp()
        self.a = self.visitor(); self.b = self.visitor()
        self.heart(self.a, 'uid-a', self.photos[0], email='a@example.com')
        self.heart(self.b, 'uid-b', self.photos[1], email='b@example.com')
        self.list_a = FavoriteList.objects.get(email='a@example.com')

    def test_each_visitor_lists_only_their_own(self):
        self.assertEqual([r['id'] for r in self.lists(self.a, 'uid-a').data['results']], [str(self.list_a.id)])
        self.assertEqual(len(self.lists(self.b, 'uid-b').data['results']), 1)
        self.assertNotIn(str(self.list_a.id), str(self.lists(self.b, 'uid-b').data))
        self.assertEqual(self.lists(self.visitor(), 'uid-nobody').data['results'], [])

    def test_another_visitors_list_cannot_be_read_renamed_or_deleted_or_added_to(self):
        url = f'{self.base}favorites/lists/{self.list_a.id}/'
        self.assertEqual(self.b.get(url, {'client_uid': 'uid-b'}).status_code, 404)
        self.assertEqual(self.b.patch(url, {'name': 'hijack', 'client_uid': 'uid-b'}, format='json').status_code, 404)
        self.assertEqual(self.b.delete(url, {'client_uid': 'uid-b'}, format='json').status_code, 404)
        self.assertEqual(self.heart(self.b, 'uid-b', self.photos[2], list_id=str(self.list_a.id)).status_code, 404)
        self.assertEqual(self.unheart(self.b, 'uid-b', self.photos[0], list_id=str(self.list_a.id)).status_code, 404)
        self.list_a.refresh_from_db()
        self.assertEqual((self.list_a.name, self.list_a.favorites.count()), ('My Favorites', 1))

    def test_a_list_id_from_another_gallery_is_a_404_even_for_its_owner(self):
        other = Gallery.objects.create(photographer=self.owner, title='Other', slug='other-fav', is_published=True, is_active=True)
        other_base = f'/api/v1/public/{self.owner.username}/{other.slug}/'
        r = self.a.get(f'{other_base}favorites/lists/{self.list_a.id}/', {'client_uid': 'uid-a'})
        self.assertEqual(r.status_code, 404)

    def test_malformed_and_unknown_list_ids_never_500(self):
        for bad in ('not-a-uuid', str(uuid.uuid4())):
            self.assertEqual(self.a.get(f'{self.base}favorites/lists/{bad}/', {'client_uid': 'uid-a'}).status_code, 404, bad)

    def test_client_uid_is_required(self):
        self.assertEqual(self.visitor().get(f'{self.base}favorites/lists/').status_code, 400)

    def test_the_visitors_credential_is_never_in_any_response(self):
        blob = str(self.lists(self.a, 'uid-a').data) + str(self.a.get(f'{self.base}favorites/', {'client_uid': 'uid-a'}).data)
        self.assertNotIn('uid-a', blob)


class PhotographerFavoriteActivityTests(FavBase):
    def test_visitors_are_grouped_by_email_with_their_lists_counts_and_thumbnails(self):
        d1, d2 = self.visitor(), self.visitor()                       # the same person on two devices
        self.heart(d1, 'phone', self.photos[0], email='fan@example.com')
        self.heart(d1, 'phone', self.photos[1])
        self.heart(d2, 'laptop', self.photos[2], email='FAN@example.com')
        self.heart(self.visitor(), 'other', self.photos[3], email='other@example.com', name='Olive')
        data = self.as_owner().get(self.activity, {'group': 'visitor'}).data
        by_email = {(g['email'] or 'guest').lower(): g for g in data['results']}
        self.assertEqual(set(by_email), {'fan@example.com', 'other@example.com', 'guest'})
        fan = by_email['fan@example.com']
        # 7-A: a typed email no longer joins two browsers (debt row 129). The phone's list
        # keeps the email (one email = one default list); the laptop's own list is a Guest.
        self.assertEqual((fan['total_photos'], fan['list_count']), (2, 1))
        self.assertEqual([l['photo_count'] for l in fan['lists']], [2])
        self.assertEqual(by_email['guest']['total_photos'], 1)
        self.assertTrue(all(l['thumbnail_url'] and l['created_at'] and l['updated_at'] for l in fan['lists']))
        self.assertEqual(by_email['other@example.com']['name'], 'Olive')
        self.assertNotIn('client_key', str(data))
        self.assertNotIn('phone', str(data))

    def test_guest_only_when_there_is_truly_no_email_and_it_does_not_crash(self):
        self.heart(self.visitor(), 'anon-1', self.photos[0])
        self.heart(self.visitor(), 'anon-2', self.photos[1])
        self.heart(self.visitor(), 'named', self.photos[2], email='real@example.com')
        data = self.as_owner().get(self.activity, {'group': 'visitor'}).data
        self.assertEqual(data['count'], 3)                                # each anonymous browser is its own Guest
        guests = [g for g in data['results'] if g['email'] is None]
        self.assertEqual(len(guests), 2)
        self.assertEqual(self.as_owner().get(self.activity, {'group': 'client'}).status_code, 200)

    def test_filter_by_email_and_sorting(self):
        self.heart(self.visitor(), 'u1', self.photos[0], email='zed@example.com')
        self.heart(self.visitor(), 'u2', self.photos[1], email='amy@example.com')
        owner = self.as_owner()
        filtered = owner.get(self.activity, {'group': 'visitor', 'email': 'amy'}).data['results']
        self.assertEqual([g['email'] for g in filtered], ['amy@example.com'])
        by_email = owner.get(self.activity, {'group': 'visitor', 'sort': 'email'}).data['results']
        self.assertEqual([g['email'] for g in by_email], ['amy@example.com', 'zed@example.com'])
        newest = owner.get(self.activity, {'group': 'visitor', 'sort': 'newest'}).data['results']
        self.assertEqual(newest[0]['email'], 'amy@example.com')
        oldest = owner.get(self.activity, {'group': 'visitor', 'sort': 'oldest'}).data['results']
        self.assertEqual(oldest[0]['email'], 'zed@example.com')

    def test_a_lists_photos_show_real_filenames_and_the_visitors_email(self):
        v = self.visitor()
        self.heart(v, 'u1', self.photos[0], email='fan@example.com'); self.heart(v, 'u1', self.photos[1])
        list_id = self.as_owner().get(self.activity, {'group': 'visitor'}).data['results'][0]['lists'][0]['id']
        detail = self.as_owner().get(self.activity, {'list': list_id}).data
        self.assertEqual(sorted(r['original_name'] for r in detail['results']), ['photo-0.jpg', 'photo-1.jpg'])
        self.assertTrue(all(r['email'] == 'fan@example.com' and r['thumbnail_url'] for r in detail['results']))

    def test_only_the_owner_sees_it_and_ids_are_tenant_scoped(self):
        self.heart(self.visitor(), 'u1', self.photos[0], email='fan@example.com')
        list_id = FavoriteList.objects.get().id
        self.assertEqual(self.client_class().get(self.activity, {'group': 'visitor'}).status_code, 401)
        stranger = User.objects.create_user(username='stranger', email='s@kyapture.com', password='Sturdy-Pass-8842!')
        theirs = Gallery.objects.create(photographer=stranger, title='Theirs', slug='theirs-fav', is_published=True, is_active=True)
        self.client.force_authenticate(user=stranger)
        self.assertEqual(self.client.get(f'/api/v1/galleries/{theirs.slug}/favorites/', {'list': str(list_id)}).status_code, 404)
        self.assertEqual(self.client.get(self.activity, {'group': 'visitor'}).status_code, 404)   # not their gallery
        self.client.force_authenticate(user=self.owner)
        for bad in ('not-a-uuid', str(uuid.uuid4())):
            self.assertEqual(self.client.get(self.activity, {'list': bad}).status_code, 404, bad)

    def test_activity_query_count_does_not_grow_with_the_number_of_visitors(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def count():
            self.client.force_authenticate(user=self.owner)
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(self.activity, {'group': 'visitor'})
            return len(ctx.captured_queries)
        self.heart(self.visitor(), 'u0', self.photos[0], email='v0@example.com')
        few = count()
        for i in range(1, 8):
            self.heart(self.visitor(), f'u{i}', self.photos[i % 5], email=f'v{i}@example.com')
        self.assertEqual(count(), few)


class FavoriteNotificationTests(FavBase):
    def notes(self):
        return list(Notification.objects.filter(user=self.owner, kind='favorite').order_by('created_at'))

    def test_text_names_the_visitor_and_the_count(self):
        v = self.visitor()
        self.heart(v, 'u1', self.photos[0], email='fan@example.com')
        self.assertEqual([n.message for n in self.notes()], ['fan@example.com favorited 1 photo'])
        self.heart(v, 'u1', self.photos[1]); self.heart(v, 'u1', self.photos[2])
        notes = self.notes()
        self.assertEqual([n.message for n in notes], ['fan@example.com favorited 3 photos'])
        self.assertEqual(notes[0].count, 3)

    def test_another_visitor_never_merges_into_it(self):
        self.heart(self.visitor(), 'u1', self.photos[0], email='a@example.com')
        self.heart(self.visitor(), 'u2', self.photos[1], email='b@example.com')
        self.assertEqual(sorted(n.message for n in self.notes()),
                         ['a@example.com favorited 1 photo', 'b@example.com favorited 1 photo'])

    def test_a_guest_is_called_a_guest_and_re_hearting_a_photo_adds_no_count(self):
        v = self.visitor()
        self.heart(v, 'g1', self.photos[0])
        self.heart(v, 'g1', self.photos[0])
        self.assertEqual([n.message for n in self.notes()], ['A guest favorited 1 photo'])


class BackfillTests(FavBase):
    def run_backfill(self):
        migration = importlib.import_module('apps.clients.migrations.0008_favorite_lists_and_download_counts')
        migration.backfill_default_lists(django_apps, None)

    def legacy(self, client_key, asset, email=None):
        return Favorite.objects.create(gallery=self.gallery, media_asset=asset, client_key=client_key, email=email)

    def test_existing_favorites_get_a_default_list_and_anonymous_rows_stay_guest(self):
        self.legacy('old-1', self.photos[0], 'old@example.com'); self.legacy('old-1', self.photos[1])
        self.legacy('anon', self.photos[2])
        session = ClientSession.objects.create(gallery=self.gallery, email='viasession@example.com')
        self.legacy(session.access_token, self.photos[3])
        self.run_backfill()
        lists = {fl.client_key: fl for fl in FavoriteList.objects.all()}
        self.assertEqual(len(lists), 3)
        self.assertEqual(lists['old-1'].email, 'old@example.com')
        self.assertIsNone(lists['anon'].email)                                   # Guest, not invented
        self.assertEqual(lists[session.access_token].email, 'viasession@example.com')
        self.assertTrue(all(fl.name == 'My Favorites' and fl.is_default for fl in lists.values()))
        self.assertFalse(Favorite.objects.filter(favorite_list__isnull=True).exists())
        self.assertEqual(Favorite.objects.get(media_asset=self.photos[1]).email, 'old@example.com')   # email back-filled on its rows

    def test_backfill_is_idempotent(self):
        self.legacy('old-1', self.photos[0], 'old@example.com')
        self.run_backfill(); self.run_backfill()
        self.assertEqual(FavoriteList.objects.count(), 1)

    def test_backfilled_guest_rows_show_in_the_photographers_activity_without_crashing(self):
        self.legacy('anon', self.photos[0])
        self.run_backfill()
        data = self.as_owner().get(self.activity, {'group': 'visitor'}).data
        self.assertEqual([(g['email'], g['total_photos']) for g in data['results']], [(None, 1)])
        self.assertEqual(self.as_owner().get(self.activity).status_code, 200)         # per-photo listing too

    def test_a_backfilled_visitor_can_keep_using_their_list(self):
        self.legacy('old-1', self.photos[0], 'old@example.com')
        self.run_backfill()
        v = self.visitor()
        self.assertEqual(self.lists(v, 'old-1').data['results'][0]['photo_count'], 1)
        self.heart(v, 'old-1', self.photos[1])
        self.assertEqual(FavoriteList.objects.count(), 1)                          # joined the existing default list
        self.assertEqual(Favorite.objects.filter(client_key='old-1').count(), 2)


class DownloadActivityRowsTests(FavBase):
    def test_single_photo_rows_carry_the_real_filename_and_thumbnail_never_a_uuid(self):
        asset = self.photos[0]
        DownloadLog.objects.create(gallery=self.gallery, media_asset=asset, download_type='photo', email='buyer@example.com',
                                   resolution='download', filename='photo-0.jpg')
        row = self.as_owner().get(f'/api/v1/galleries/{self.gallery.slug}/download-logs/').data['results'][0]
        self.assertEqual((row['filename'], row['media_asset_name'], row['email']), ('photo-0.jpg', 'photo-0.jpg', 'buyer@example.com'))
        self.assertIn('photo-0.jpg.thumb.webp', row['thumbnail_url'])
        self.assertNotRegex(row['filename'], r'[0-9a-f]{8}-[0-9a-f]{4}-')

    def test_legacy_rows_without_a_stored_filename_fall_back_to_the_photos_name(self):
        DownloadLog.objects.create(gallery=self.gallery, media_asset=self.photos[1], download_type='photo')
        row = self.as_owner().get(f'/api/v1/galleries/{self.gallery.slug}/download-logs/').data['results'][0]
        self.assertEqual(row['filename'], 'photo-1.jpg')
        self.assertIsNone(row['email'])

    def test_gallery_rows_carry_size_photo_count_zip_name_and_time(self):
        DownloadLog.objects.create(gallery=self.gallery, download_type='gallery', email='buyer@example.com', resolution='web',
                                   filename='fav-gallery-photo-download-1of1.zip', photo_count=5)
        row = self.as_owner().get(f'/api/v1/galleries/{self.gallery.slug}/download-logs/').data['results'][0]
        self.assertEqual((row['resolution'], row['photo_count'], row['filename'], row['thumbnail_url']),
                         ('web', 5, 'fav-gallery-photo-download-1of1.zip', None))
        self.assertTrue(row['created_at'])
