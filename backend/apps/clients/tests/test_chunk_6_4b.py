# backend/apps/clients/tests/test_chunk_6_4b.py
"""
CHUNK 6.4-B - four QA issues.

  1. one visitor email = ONE default "My Favorites" list per gallery (get-or-create,
     DB unique constraint, data migration that merges existing duplicates)
  2. a download of several sets records and shows its set names in Download Activity
  3. a multi-part ZIP is ONE bell notification per download job ("N files")
  4. a returning visitor (email remembered / on their unlock session) sees every
     favorited photo filled and hearting again never makes a second list; a guest
     list is merged into the email list once the same browser gives an email
"""
import importlib

import bcrypt
from django.apps import apps as django_apps
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.clients.models import ClientSession, DownloadJob, DownloadLog, Favorite, FavoriteList
from apps.clients.tests.test_download_jobs import JobBase, _asset as _file_asset
from apps.clients.tests.test_favorite_lists import FavBase
from apps.clients.tests.zip_flow import request_zip
from apps.photos.models import PhotoSet
from apps.users.models import Notification

EMAIL = 'krishal@example.com'


class OneListPerEmailTests(FavBase):
    def default_lists(self, email=EMAIL):
        return FavoriteList.objects.filter(gallery=self.gallery, email__iexact=email, is_default=True)

    def test_same_email_from_two_browsers_is_one_default_list(self):            # repro: was 2 lists
        self.heart(self.visitor(), 'browser-a', self.photos[0], email=EMAIL)
        self.heart(self.visitor(), 'browser-b', self.photos[1], email=EMAIL)
        self.assertEqual(self.default_lists().count(), 1)
        self.assertEqual(Favorite.objects.filter(favorite_list=self.default_lists().get()).count(), 2)

    def test_the_email_is_matched_case_insensitively(self):
        self.heart(self.visitor(), 'browser-a', self.photos[0], email='Fan@Example.com')
        self.heart(self.visitor(), 'browser-b', self.photos[1], email='fan@example.COM')
        self.assertEqual(FavoriteList.objects.count(), 1)

    def test_the_same_photo_from_two_browsers_is_stored_once(self):
        self.heart(self.visitor(), 'browser-a', self.photos[0], email=EMAIL)
        self.heart(self.visitor(), 'browser-b', self.photos[0], email=EMAIL)
        self.assertEqual(Favorite.objects.count(), 1)

    def test_another_gallery_or_another_email_gets_its_own_list(self):
        other = type(self.gallery).objects.create(
            photographer=self.owner, title='Other', slug='other-fav-2', is_published=True, is_active=True)
        self.heart(self.visitor(), 'a', self.photos[0], email=EMAIL)
        self.heart(self.visitor(), 'b', self.photos[0], email='someone@else.com')
        FavoriteList.objects.create(gallery=other, client_key='c', email=EMAIL, is_default=True)
        self.assertEqual(FavoriteList.objects.count(), 3)

    def test_the_database_refuses_a_second_default_list_for_one_email(self):
        FavoriteList.objects.create(gallery=self.gallery, client_key='a', email=EMAIL, is_default=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FavoriteList.objects.create(gallery=self.gallery, client_key='b', email=EMAIL.upper(), is_default=True)

    def test_a_guest_list_is_merged_into_the_email_list_when_the_browser_gives_an_email(self):
        v = self.visitor()
        self.heart(v, 'guest-browser', self.photos[0])                          # a guest list, no email
        self.heart(v, 'guest-browser', self.photos[1])
        self.heart(self.visitor(), 'other', self.photos[1], email=EMAIL)          # the email already has a list
        self.heart(v, 'guest-browser', self.photos[2], email=EMAIL)               # same browser now gives it
        favorite_list = self.default_lists().get()
        self.assertEqual(FavoriteList.objects.count(), 1)                        # the guest list is gone, not duplicated
        self.assertEqual(
            set(favorite_list.favorites.values_list('media_asset_id', flat=True)),
            {self.photos[0].id, self.photos[1].id, self.photos[2].id})
        self.assertEqual(favorite_list.favorites.count(), 3)                     # photo 1 was in both: kept once

    def test_a_guest_list_simply_gains_the_email_when_none_exists_yet(self):
        v = self.visitor()
        self.heart(v, 'g', self.photos[0])
        self.heart(v, 'g', self.photos[1], email=EMAIL)
        favorite_list = FavoriteList.objects.get()
        self.assertEqual((favorite_list.email, favorite_list.favorites.count()), (EMAIL, 2))


class ReturningVisitorTests(FavBase):
    """A protected gallery hands out a NEW unlock token on every visit - the old key is gone."""

    def setUp(self):
        super().setUp()
        self.gallery.is_password_protected = True
        self.gallery.password_hash = bcrypt.hashpw(b'pw', bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=['is_password_protected', 'password_hash'])

    def unlock(self, email=EMAIL):
        cache.clear()
        body = {'password': 'pw'}
        if email:
            body['email'] = email
        response = self.client_class().post(f'{self.base}unlock/', body, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['access_token']

    def auth(self, token):
        return {'HTTP_AUTHORIZATION': f'Bearer {token}'}

    def heart_with(self, token, asset, **extra):
        return self.client_class().post(
            f'{self.base}favorites/', {'media_asset_id': str(asset.id), **extra}, format='json', **self.auth(token))

    def favorited(self, token, **params):
        response = self.client_class().get(f'{self.base}favorites/', params, **self.auth(token))
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_a_return_visit_with_a_new_token_shows_every_heart_filled(self):   # repro: was empty
        first = self.unlock()
        self.heart_with(first, self.photos[0]); self.heart_with(first, self.photos[1])
        second = self.unlock()                                                  # tab closed, unlocked again
        self.assertNotEqual(first, second)
        data = self.favorited(second)
        self.assertEqual(set(data['favorited_ids']), {str(self.photos[0].id), str(self.photos[1].id)})
        self.assertEqual(data['email'], EMAIL)

    def test_hearting_again_on_the_return_visit_never_creates_a_second_list(self):
        first = self.unlock()
        self.heart_with(first, self.photos[0])
        second = self.unlock()
        self.heart_with(second, self.photos[2])
        self.assertEqual(FavoriteList.objects.count(), 1)
        self.assertEqual(Favorite.objects.count(), 2)

    def test_un_hearting_on_the_return_visit_removes_the_photo(self):
        first = self.unlock()
        self.heart_with(first, self.photos[0])
        second = self.unlock()
        response = self.client_class().delete(
            f'{self.base}favorites/', {'media_asset_id': str(self.photos[0].id)}, format='json', **self.auth(second))
        self.assertEqual((response.status_code, response.data['favorited']), (200, False))
        self.assertEqual(Favorite.objects.count(), 0)

    def test_the_visitors_list_screen_also_sees_the_earlier_visit(self):
        first = self.unlock()
        self.heart_with(first, self.photos[0])
        second = self.unlock()
        lists = self.client_class().get(f'{self.base}favorites/lists/', **self.auth(second)).data['results']
        self.assertEqual([(l['name'], l['photo_count']) for l in lists], [('My Favorites', 1)])

    def test_a_remembered_email_alone_restores_the_hearts(self):
        first = self.unlock()                                                    # email on the session
        self.heart_with(first, self.photos[0])
        anonymous_unlock = self.unlock(email=None)                               # unlocked without typing an email
        self.assertEqual(self.favorited(anonymous_unlock)['favorited_ids'], [])
        data = self.favorited(anonymous_unlock, email=EMAIL)                     # the browser remembered it
        self.assertEqual(data['favorited_ids'], [str(self.photos[0].id)])

    def test_another_email_never_sees_the_list(self):
        first = self.unlock()
        self.heart_with(first, self.photos[0])
        stranger = self.unlock(email='stranger@example.com')
        self.assertEqual(self.favorited(stranger)['favorited_ids'], [])

    def test_open_gallery_return_with_a_new_browser_id_and_the_remembered_email(self):
        self.gallery.is_password_protected = False
        self.gallery.save(update_fields=['is_password_protected'])
        v = self.visitor()
        self.heart(v, 'old-uid', self.photos[0], email=EMAIL)
        got = v.get(f'{self.base}favorites/', {'client_uid': 'new-uid', 'email': EMAIL})
        self.assertEqual(got.data['favorited_ids'], [str(self.photos[0].id)])
        self.assertEqual(v.get(f'{self.base}favorites/', {'client_uid': 'new-uid'}).data['favorited_ids'], [])


class MergeDuplicateListsMigrationTests(FavBase):
    """The data migration run on a COPY of duplicate data (the constraint is lifted to build it)."""

    def migration(self):
        return importlib.import_module('apps.clients.migrations.0010_merge_duplicate_favorite_lists')

    def lift_constraint(self):
        constraint = next(c for c in FavoriteList._meta.constraints if c.name == 'unique_default_list_per_gallery_email')
        with connection.schema_editor() as editor:
            editor.remove_constraint(FavoriteList, constraint)
        return constraint

    def restore_constraint(self, constraint):
        with connection.cursor() as cursor:
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')       # settle the merge's FK trigger events first
        with connection.schema_editor() as editor:
            editor.add_constraint(FavoriteList, constraint)

    def duplicate(self, key, email, photos, name='', at=None):
        favorite_list = FavoriteList.objects.create(
            gallery=self.gallery, client_key=key, email=email, is_default=True, visitor_name=name)
        for photo in photos:
            Favorite.objects.create(
                gallery=self.gallery, media_asset=photo, client_key=key, email=email, favorite_list=favorite_list)
        return favorite_list

    def test_duplicates_are_merged_into_the_oldest_and_the_empty_one_is_deleted(self):
        constraint = self.lift_constraint()
        try:
            oldest = self.duplicate('k1', 'Krishal@Example.com', [self.photos[0]], name='Krishal')
            newer = self.duplicate('k2', 'krishal@example.com', [self.photos[0], self.photos[1]])   # photo 0 is in both
            newest = self.duplicate('k3', 'KRISHAL@example.com', [self.photos[2]])
            lone = self.duplicate('k4', 'solo@example.com', [self.photos[3]])
            guest = FavoriteList.objects.create(gallery=self.gallery, client_key='g', is_default=True)
            Favorite.objects.create(gallery=self.gallery, media_asset=self.photos[4], client_key='g', favorite_list=guest)

            self.migration().merge_duplicate_default_lists(django_apps, None)

            self.assertFalse(FavoriteList.objects.filter(pk__in=[newer.pk, newest.pk]).exists())
            merged = FavoriteList.objects.get(pk=oldest.pk)
            self.assertEqual(
                set(merged.favorites.values_list('media_asset_id', flat=True)),
                {self.photos[0].id, self.photos[1].id, self.photos[2].id})
            self.assertEqual(merged.favorites.count(), 3)                         # no duplicate rows
            self.assertEqual(Favorite.objects.filter(favorite_list__isnull=True).count(), 0)
            self.assertEqual(merged.visitor_name, 'Krishal')
            # untouched: another email, and the guest list (no email)
            self.assertEqual(FavoriteList.objects.get(pk=lone.pk).favorites.count(), 1)
            self.assertEqual(FavoriteList.objects.get(pk=guest.pk).favorites.count(), 1)
            self.assertEqual(FavoriteList.objects.count(), 3)
            self.migration().merge_duplicate_default_lists(django_apps, None)     # idempotent
            self.assertEqual(FavoriteList.objects.count(), 3)
        finally:
            self.restore_constraint(constraint)                                    # succeeds only if no duplicate is left

    def test_the_merged_list_shows_once_in_the_photographers_activity(self):
        constraint = self.lift_constraint()
        try:
            self.duplicate('k1', EMAIL, [self.photos[0]])
            self.duplicate('k2', EMAIL, [self.photos[1], self.photos[2]])
            self.migration().merge_duplicate_default_lists(django_apps, None)
        finally:
            self.restore_constraint(constraint)
        data = self.as_owner().get(self.activity, {'group': 'visitor'}).data['results']
        self.assertEqual([(g['email'], g['list_count'], g['total_photos']) for g in data], [(EMAIL, 1, 3)])


class SetNamesTests(JobBase):
    with_pin = False

    def setUp(self):
        super().setUp()
        self.set_b = PhotoSet.objects.create(gallery=self.gallery, name='Reception', order=2)
        self.b1 = _file_asset(self.gallery, 'b1.jpg', self.set_b, 3)

    def rows(self):
        self.client.force_authenticate(user=self.owner)
        return self.client.get(f'/api/v1/galleries/{self.gallery.slug}/download-logs/').data['results']

    def test_a_whole_gallery_download_records_every_set_it_contains(self):       # repro: no set name
        self.assertEqual(request_zip(self.client, self.base, {'email': 'c@example.com'}).status_code, 200)
        log = DownloadLog.objects.get()
        self.assertEqual(log.set_names, ['Ceremony', 'Reception'])
        row = self.rows()[0]
        self.assertEqual(row['set_names'], ['Ceremony', 'Reception'])
        self.assertEqual(row['photo_set_name'], 'Ceremony, Reception')

    def test_a_selection_across_sets_names_only_the_sets_chosen(self):
        body = {'email': 'c@example.com', 'asset_ids': [str(self.a1.id), str(self.b1.id)]}
        request_zip(self.client, self.base, body)
        self.assertEqual(DownloadLog.objects.get().set_names, ['Ceremony', 'Reception'])

    def test_a_single_set_download_keeps_its_one_name(self):
        request_zip(self.client, self.base, {'email': 'c@example.com', 'set_id': str(self.set_b.id)})
        row = self.rows()[0]
        self.assertEqual((row['photo_set_name'], row['set_names']), ('Reception', ['Reception']))

    def test_the_stored_names_survive_a_set_being_renamed_later(self):
        request_zip(self.client, self.base, {'email': 'c@example.com'})
        PhotoSet.objects.filter(pk=self.set_b.pk).update(name='Party')
        self.assertEqual(self.rows()[0]['set_names'], ['Ceremony', 'Reception'])


class OneNotificationPerJobTests(JobBase):
    with_pin = False

    def setUp(self):
        super().setUp()
        self.b1 = _file_asset(self.gallery, 'b1.jpg', self.set_a, 3)              # 3 photos -> 3 parts at a 20 byte limit

    def notes(self):
        return list(Notification.objects.filter(user=self.owner, kind='download'))

    def ready(self, token):
        job_id = self.prepare(token).data['job_id']
        return DownloadJob.objects.get(pk=job_id), self.status_of(job_id, token).data

    @override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=20)
    def test_three_parts_are_one_notification_saying_3_files(self):             # repro: 3 notifications
        token = self.token(email='buyer@example.com')
        job, ready = self.ready(token)
        self.assertEqual(len(ready['files']), 3)
        for entry in ready['files']:
            self.assertEqual(self.client.get(entry['url']).status_code, 200)
        self.assertEqual(DownloadLog.objects.count(), 3)                        # activity rows stay per part
        notes = self.notes()
        self.assertEqual(len(notes), 1)
        self.assertEqual((notes[0].count, notes[0].message), (3, 'Gallery downloaded by buyer@example.com · 3 files'))

    @override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=20)
    def test_the_first_part_alone_reads_like_any_single_download(self):
        token = self.token(email='buyer@example.com')
        _, ready = self.ready(token)
        self.client.get(ready['files'][0]['url'])
        self.assertEqual([n.message for n in self.notes()], ['Gallery downloaded by buyer@example.com'])

    @override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=20)
    def test_a_later_part_marks_the_notification_unread_again(self):
        token = self.token(email='buyer@example.com')
        _, ready = self.ready(token)
        self.client.get(ready['files'][0]['url'])
        Notification.objects.update(is_read=True)
        self.client.get(ready['files'][1]['url'])
        note = Notification.objects.get(kind='download')
        self.assertEqual((note.is_read, note.count), (False, 2))

    @override_settings(DOWNLOAD_ZIP_PART_MAX_BYTES=20)
    def test_two_separate_jobs_stay_two_notifications(self):
        token = self.token(email='buyer@example.com')
        _, first = self.ready(token)
        self.client.get(first['files'][0]['url'])
        cache.clear()
        other = self.prepare(token, resolution='web').data['job_id']              # another size = another job
        self.client.get(self.status_of(other, token).data['files'][0]['url'])
        self.assertEqual(len(self.notes()), 2)

    def test_a_single_part_job_is_unchanged(self):
        token = self.token(email='buyer@example.com')
        request_zip(self.client, self.base, {'download_token': token})
        self.assertEqual([(n.count, n.message) for n in self.notes()], [(1, 'Gallery downloaded by buyer@example.com')])

    def test_a_single_photo_download_is_still_its_own_notification(self):
        token = self.token(email='buyer@example.com')
        self.client.get(f'{self.base}photo/{self.a1.id}/download/', {'download_token': token})
        self.client.get(f'{self.base}photo/{self.a2.id}/download/', {'download_token': token})
        self.assertEqual(len(self.notes()), 2)
