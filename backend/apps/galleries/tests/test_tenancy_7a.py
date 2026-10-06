# backend/apps/galleries/tests/test_tenancy_7a.py
"""
CHUNK 7-A (tenancy) - every owner endpoint that takes a slug or an id, called
with ANOTHER photographer's slug/id: by a second photographer, by a staff
account that does not own the data, and anonymously. Foreign objects answer
404 (not 403), so the response never confirms that they exist, and nothing
of the owner's data is read or changed.
"""
import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient, APITestCase

from apps.clients.models import DownloadLog, Favorite, FavoriteList
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet
from apps.users.models import Notification

User = get_user_model()
PASSWORD = 'Sturdy-Pass-8842!'


def _asset(gallery, name, photo_set=None):
    return MediaAsset.objects.create(
        gallery=gallery, photo_set=photo_set, media_type='image', original_name=name, file_size=10,
        processing_status='ready', original_file=f't7a/{gallery.slug}/{name}',
        thumbnail_file=f't7a/{gallery.slug}/{name}.thumb.webp', display_file=f't7a/{gallery.slug}/{name}.d.webp',
    )


class CrossAccountBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email='t7a-owner@kyapture.com', password=PASSWORD, username='t7aowner')
        self.gallery = Gallery.objects.create(
            photographer=self.owner, title='Owner Wedding', slug='wedding', is_active=True, is_published=True)
        self.set = PhotoSet.objects.create(gallery=self.gallery, name='Ceremony', order=1)
        self.set_count = PhotoSet.objects.filter(gallery=self.gallery).count()   # incl. any default set
        self.photo = _asset(self.gallery, 'owner-1.jpg', self.set)
        MediaAsset.objects.filter(pk=self.photo.pk).update(is_favorite=True)
        self.fav_list = FavoriteList.objects.create(gallery=self.gallery, client_key='k', email='c@example.com', is_default=True)
        Favorite.objects.create(gallery=self.gallery, media_asset=self.photo, client_key='k', favorite_list=self.fav_list)
        DownloadLog.objects.create(gallery=self.gallery, media_asset=self.photo, email='c@example.com')
        self.notification = Notification.objects.create(user=self.owner, kind='download', gallery=self.gallery, message='m')

        self.attacker = User.objects.create_user(email='t7a-attacker@kyapture.com', password=PASSWORD, username='t7aattacker')
        # the attacker owns a gallery with the SAME slug: slugs are per photographer, never global
        self.attacker_gallery = Gallery.objects.create(
            photographer=self.attacker, title='Attacker', slug='attacker-own', is_active=True)
        self.attacker_set = PhotoSet.objects.create(gallery=self.attacker_gallery, name='Mine', order=1)
        self.staff = User.objects.create_user(
            email='t7a-staff@kyapture.com', password=PASSWORD, username='t7astaff', is_staff=True, is_superuser=True)

    def as_user(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def foreign_calls(self):
        g, p, s, fl = self.gallery.slug, self.photo.id, self.set.id, self.fav_list.id
        return [
            ('get', f'/api/v1/galleries/{g}/', {}),
            ('patch', f'/api/v1/galleries/{g}/', {'title': 'pwned', 'is_published': False}),
            ('put', f'/api/v1/galleries/{g}/', {'title': 'pwned'}),
            ('delete', f'/api/v1/galleries/{g}/', {}),
            ('post', f'/api/v1/galleries/{g}/publish/', {}),
            ('post', f'/api/v1/galleries/{g}/set-password/', {'password': 'pwned-pass'}),
            ('post', f'/api/v1/galleries/{g}/set-download-pin/', {'pin': '1234'}),
            ('get', f'/api/v1/galleries/{g}/favorites/', {}),
            ('get', f'/api/v1/galleries/{g}/favorites/', {'list': str(fl)}),
            ('get', f'/api/v1/galleries/{g}/favorites/', {'group': 'visitor'}),
            ('get', f'/api/v1/galleries/{g}/download-logs/', {}),
            ('get', f'/api/v1/photos/{g}/', {}),
            ('post', f'/api/v1/photos/{g}/upload/', {}),
            ('post', f'/api/v1/photos/{g}/delete-bulk/', {'photo_ids': [str(p)]}),
            ('patch', f'/api/v1/photos/{g}/reorder/', {'ordered_ids': [str(p)]}),
            ('get', f'/api/v1/photos/{g}/status/', {'ids': str(p)}),
            ('patch', f'/api/v1/photos/{g}/move/', {'photo_ids': [str(p)], 'set_id': None}),
            ('patch', f'/api/v1/photos/{g}/sets/reorder/', {'ordered_ids': [str(s)]}),
            ('get', f'/api/v1/photos/{g}/sets/', {}),
            ('post', f'/api/v1/photos/{g}/sets/', {'name': 'pwned'}),
            ('patch', f'/api/v1/photos/{g}/sets/{s}/', {'name': 'pwned'}),
            ('delete', f'/api/v1/photos/{g}/sets/{s}/', {}),
            ('get', f'/api/v1/photos/photo/{p}/', {}),
            ('delete', f'/api/v1/photos/photo/{p}/', {}),
            ('put', f'/api/v1/photos/photo/{p}/favorite/', {'is_favorite': False}),
            ('post', f'/api/v1/notifications/{self.notification.id}/read/', {}),
        ]

    def call(self, client, method, url, body):
        if method == 'get':
            return client.get(url, body)
        return getattr(client, method)(url, body, format='json')

    def assert_owner_data_untouched(self):
        self.gallery.refresh_from_db()
        self.set.refresh_from_db()
        self.photo.refresh_from_db()
        self.notification.refresh_from_db()
        self.assertEqual((self.gallery.title, self.gallery.is_published, self.gallery.is_password_protected,
                          self.gallery.download_pin_hash or ''), ('Owner Wedding', True, False, ''))
        self.assertEqual((self.set.name, self.photo.photo_set_id, self.photo.is_favorite), ('Ceremony', self.set.id, True))
        self.assertEqual(PhotoSet.objects.filter(gallery=self.gallery).count(), self.set_count)
        self.assertFalse(self.notification.is_read)


class ForeignObjectTests(CrossAccountBase):
    def test_another_photographer_gets_404_on_every_owner_endpoint(self):
        client = self.as_user(self.attacker)
        for method, url, body in self.foreign_calls():
            response = self.call(client, method, url, body)
            self.assertEqual(response.status_code, 404, f'{method} {url}: {getattr(response, "data", "")}')
            self.assertNotIn(b'Owner Wedding', response.content, url)
        self.assert_owner_data_untouched()

    def test_staff_without_ownership_gets_404_on_every_owner_endpoint(self):
        client = self.as_user(self.staff)
        for method, url, body in self.foreign_calls():
            response = self.call(client, method, url, body)
            self.assertEqual(response.status_code, 404, f'{method} {url}')
        self.assert_owner_data_untouched()

    def test_anonymous_gets_401_on_every_owner_endpoint(self):
        client = self.as_user(None)
        for method, url, body in self.foreign_calls():
            self.assertEqual(self.call(client, method, url, body).status_code, 401, f'{method} {url}')
        self.assert_owner_data_untouched()

    def test_foreign_ids_inside_the_attackers_own_gallery_change_nothing(self):
        client = self.as_user(self.attacker)
        a = self.attacker_gallery.slug
        moved = client.patch(f'/api/v1/photos/{a}/move/', {'photo_ids': [str(self.photo.id)], 'set_id': str(self.attacker_set.id)}, format='json')
        self.assertEqual((moved.status_code, moved.data['updated_count']), (200, 0))
        self.assertEqual(client.patch(f'/api/v1/photos/{a}/move/', {'photo_ids': [str(self.photo.id)], 'set_id': str(self.set.id)},
                                      format='json').status_code, 404)
        deleted = client.post(f'/api/v1/photos/{a}/delete-bulk/', {'photo_ids': [str(self.photo.id)]}, format='json')
        self.assertEqual((deleted.status_code, deleted.data['deleted_count']), (200, 0))
        client.patch(f'/api/v1/photos/{a}/reorder/', {'ordered_ids': [str(self.photo.id)]}, format='json')
        self.assertEqual(client.patch(f'/api/v1/photos/{a}/sets/{self.set.id}/', {'name': 'x'}, format='json').status_code, 404)
        self.assertEqual(client.delete(f'/api/v1/photos/{a}/sets/{self.set.id}/').status_code, 404)
        status_rows = client.get(f'/api/v1/photos/{a}/status/', {'ids': str(self.photo.id)})
        self.assertEqual((status_rows.status_code, status_rows.data), (200, []))
        self.assertEqual(client.get(f'/api/v1/photos/{a}/', {'set': str(self.set.id)}).status_code, 404)
        self.assertEqual(client.post(f'/api/v1/photos/{a}/upload/', {'set_id': str(self.set.id)}).status_code, 404)
        cover = client.patch(f'/api/v1/galleries/{a}/', {'cover_photo': str(self.photo.id)}, format='json')
        self.assertEqual(cover.status_code, 400)
        cover = client.patch(f'/api/v1/galleries/{a}/', {'design_settings': {'coverPhoto': str(self.photo.id)}}, format='json')
        self.assertEqual(cover.status_code, 400)
        self.assertEqual(client.get(f'/api/v1/galleries/{a}/favorites/', {'list': str(self.fav_list.id)}).status_code, 404)
        self.assert_owner_data_untouched()
        self.assertTrue(MediaAsset.objects.filter(pk=self.photo.pk).exists())

    def test_listing_endpoints_show_only_the_callers_rows(self):
        client = self.as_user(self.attacker)
        flat = b''.join(client.get(url, params).content for url, params in (
            ('/api/v1/galleries/', {}), ('/api/v1/galleries/search/', {'q': 'Owner'}),
            ('/api/v1/galleries/dashboard/stats/', {}), ('/api/v1/photos/favorites/all/', {}),
            ('/api/v1/notifications/', {}), ('/api/v1/subscriptions/payments/', {}),
            ('/api/v1/subscriptions/my-subscription/', {}), ('/api/v1/auth/settings/', {}),
        ))
        for leak in (b'Owner Wedding', b'owner-1.jpg', str(self.photo.id).encode(), str(self.notification.id).encode(),
                     b't7a-owner@kyapture.com'):
            self.assertNotIn(leak, flat)

    def test_read_all_marks_only_the_callers_notifications(self):
        self.as_user(self.attacker).post('/api/v1/notifications/read-all/')
        self.notification.refresh_from_db()
        self.assertFalse(self.notification.is_read)

    def test_a_malformed_id_in_a_query_is_a_clean_answer_not_a_500(self):
        client = self.as_user(self.owner)
        g = self.gallery.slug
        for url, params in ((f'/api/v1/photos/{g}/status/', {'ids': 'not-a-uuid'}),
                            (f'/api/v1/photos/{g}/', {'set': 'not-a-uuid'}),
                            (f'/api/v1/galleries/{g}/favorites/', {'list': 'not-a-uuid'})):
            self.assertIn(client.get(url, params).status_code, (200, 400, 404), url)

    def test_a_random_id_is_the_same_404_as_a_foreign_one(self):
        client = self.as_user(self.attacker)
        for url in (f'/api/v1/photos/photo/{uuid.uuid4()}/', f'/api/v1/photos/photo/{self.photo.id}/'):
            response = client.get(url)
            self.assertEqual(response.status_code, 404)
        self.assertEqual(client.get(f'/api/v1/photos/photo/{uuid.uuid4()}/').data,
                         client.get(f'/api/v1/photos/photo/{self.photo.id}/').data)
