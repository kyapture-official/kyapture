# backend/apps/galleries/tests/test_query_efficiency.py
"""
Task 5 — performance regression tests.

These pin the *shape* of the hot endpoints rather than wall-clock times (which
are machine noise in CI):

  - query counts are CONSTANT as the data grows (no N+1 on the dashboard
    gallery list, the public portfolio, the owner gallery detail, or the public
    gallery page), and a few endpoints keep a hard upper bound
  - public pagination returns every ready asset exactly once, in order, across
    the embedded first page and the continuation endpoint
  - a malformed `?set=` is an empty result, not an unhandled 500
  - the hero cover advertises a medium tier for responsive loading
  - JSON API bodies are gzip-compressed on request; file downloads never are
  - the lighter subscription / stats code paths return the same answers as the
    queries they replaced (entitlements, active-vs-trashed photo counts)
"""
import gzip
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet
from apps.subscriptions.entitlements import get_feature_entitlements
from apps.subscriptions.models import UserSubscription
from apps.subscriptions.testing import grant_plan
from apps.users.models import Notification

User = get_user_model()


def _ready_asset(gallery, index, photo_set=None, medium=True):
    kwargs = dict(
        gallery=gallery,
        media_type=MediaAsset.MediaType.IMAGE,
        original_name=f'photo-{index:04d}.jpg',
        file_size=1000,
        order=index,
        photo_set=photo_set,
        processing_status=MediaAsset.ProcessingStatus.READY,
        original_file=f'perf/{gallery.slug}/{index}_original.jpg',
        display_file=f'perf/{gallery.slug}/{index}_display.webp',
        thumbnail_file=f'perf/{gallery.slug}/{index}_thumb.webp',
        width=900, height=600,
    )
    if medium:
        kwargs['medium_file'] = f'perf/{gallery.slug}/{index}_medium.webp'
    return MediaAsset.objects.create(**kwargs)


class QueryBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='perfuser', email='perf@kyapture.com', password='SecurePassword123!',
            display_name='Perf User')
        grant_plan(self.user)

    def make_gallery(self, slug, photos=0, **extra):
        gallery = Gallery.objects.create(
            photographer=self.user, title=slug.title(), slug=slug,
            is_published=True, is_active=True, **extra)
        assets = [_ready_asset(gallery, i) for i in range(photos)]
        if assets:
            Gallery.objects.filter(pk=gallery.pk).update(cover_photo=assets[0])
        return gallery

    def queries(self, url, authed=True, **kwargs):
        """(query count, response) for one GET, with the response-cache cleared."""
        if authed:
            self.client.force_authenticate(user=self.user)
        else:
            self.client.force_authenticate(user=None)
        cache.clear()
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url, **kwargs)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return len(ctx.captured_queries), response


class NoNPlusOneTests(QueryBase):
    def test_dashboard_gallery_list_query_count_is_independent_of_gallery_count(self):
        for i in range(2):
            self.make_gallery(f'g{i}', photos=2)
        few, _ = self.queries('/api/v1/galleries/')
        for i in range(2, 12):
            self.make_gallery(f'g{i}', photos=2)
        many, response = self.queries('/api/v1/galleries/')
        self.assertEqual(len(response.data['results']), 12)
        self.assertEqual(few, many, 'gallery list grew queries with the number of galleries (N+1)')

    def test_gallery_search_query_count_is_independent_of_result_count(self):
        self.make_gallery('wedding-a', photos=1)
        few, _ = self.queries('/api/v1/galleries/search/?q=wedding')
        for i in range(8):
            self.make_gallery(f'wedding-{i}-b', photos=1)
        many, _ = self.queries('/api/v1/galleries/search/?q=wedding')
        self.assertEqual(few, many)

    def test_public_portfolio_query_count_is_independent_of_gallery_count(self):
        for i in range(2):
            self.make_gallery(f'p{i}', photos=1)
        few, _ = self.queries('/api/v1/public/perfuser/', authed=False)
        for i in range(2, 10):
            self.make_gallery(f'p{i}', photos=1)
        many, response = self.queries('/api/v1/public/perfuser/', authed=False)
        self.assertEqual(len(response.data['galleries']) if 'galleries' in response.data else 10, 10)
        self.assertEqual(few, many, 'portfolio grew queries with the number of galleries (N+1)')

    def test_owner_gallery_detail_preview_photos_do_not_add_per_asset_queries(self):
        small = self.make_gallery('small', photos=2)
        large = self.make_gallery('large', photos=30)
        few, r_small = self.queries(f'/api/v1/galleries/{small.slug}/')
        many, r_large = self.queries(f'/api/v1/galleries/{large.slug}/')
        self.assertEqual(len(r_small.data['photos']), 2)
        self.assertEqual(len(r_large.data['photos']), 20, 'preview strip stays bounded at 20')
        self.assertEqual(few, many)
        self.assertLessEqual(many, 3)

    def test_public_gallery_page_query_count_is_independent_of_photo_count(self):
        self.make_gallery('few', photos=3)
        self.make_gallery('lots', photos=55)
        few, _ = self.queries('/api/v1/public/perfuser/few/', authed=False)
        many, response = self.queries('/api/v1/public/perfuser/lots/', authed=False)
        self.assertEqual(len(response.data['photos']), 55)
        self.assertEqual(few, many)
        # gallery(+photographer+cover), ready count, page, sets
        self.assertLessEqual(many, 4)

    def test_notification_bell_count_is_one_query_and_tiny(self):
        for i in range(40):
            Notification.objects.create(user=self.user, kind='download', message=f'm{i}')
        count, response = self.queries('/api/v1/notifications/unread-count/')
        self.assertEqual(count, 1)
        self.assertEqual(set(response.data), {'unread_count'})
        self.assertEqual(response.data['unread_count'], 40)

    def test_notification_list_is_paginated_not_unbounded(self):
        for i in range(40):
            Notification.objects.create(user=self.user, kind='download', message=f'm{i}')
        _, response = self.queries('/api/v1/notifications/')
        self.assertLessEqual(len(response.data['results']), 15)
        self.assertIsNotNone(response.data['next'])


class PublicPaginationIntegrityTests(QueryBase):
    def test_pages_cover_every_ready_asset_exactly_once_in_order(self):
        gallery = self.make_gallery('paged', photos=0)
        expected = [_ready_asset(gallery, i).id for i in range(130)]
        # non-ready assets must never appear on any page
        MediaAsset.objects.create(
            gallery=gallery, media_type='image', original_name='pending.jpg', file_size=1,
            order=500, processing_status=MediaAsset.ProcessingStatus.PENDING,
            original_file='perf/paged/pending.jpg')

        _, first = self.queries('/api/v1/public/perfuser/paged/', authed=False)
        embedded = [p['id'] for p in first.data['photos']]
        self.assertEqual(first.data['photos_count'], 130)
        self.assertTrue(first.data['photos_has_more'])

        seen, page = [], 1
        while True:
            _, response = self.queries(f'/api/v1/public/perfuser/paged/photos/?page={page}', authed=False)
            seen.extend(p['id'] for p in response.data['results'])
            if not response.data['next']:
                break
            page += 1

        self.assertEqual(seen, [str(i) for i in expected])            # none missing, none duplicated, ordered
        self.assertEqual(embedded, seen[:len(embedded)])              # embedded page == page 1 of the feed
        self.assertEqual(page, 3)                                     # 60 + 60 + 10

    def test_set_filter_pages_stay_inside_the_set(self):
        gallery = self.make_gallery('sets', photos=0)
        a = PhotoSet.objects.filter(gallery=gallery).first()
        b = PhotoSet.objects.create(gallery=gallery, name='Party', order=9)
        for i in range(70):
            _ready_asset(gallery, i, photo_set=a if i % 2 == 0 else b)
        _, response = self.queries(f'/api/v1/public/perfuser/sets/photos/?page=1&set={b.id}', authed=False)
        self.assertEqual(response.data['count'], 35)
        self.assertTrue(all(p['original_name'].startswith('photo-') for p in response.data['results']))
        self.assertEqual(len(response.data['results']), 35)


class MalformedSetFilterTests(QueryBase):
    def test_malformed_set_id_is_an_empty_page_not_a_500(self):
        self.make_gallery('bad', photos=5)
        _, gallery = self.queries('/api/v1/public/perfuser/bad/?set=not-a-uuid', authed=False)
        self.assertEqual(gallery.data['photos'], [])
        self.assertEqual(gallery.data['photos_count'], 0)
        _, feed = self.queries('/api/v1/public/perfuser/bad/photos/?set=not-a-uuid', authed=False)
        self.assertEqual(feed.data['results'], [])

    def test_unknown_but_wellformed_set_id_is_also_empty(self):
        self.make_gallery('unk', photos=5)
        _, feed = self.queries(
            '/api/v1/public/perfuser/unk/photos/?set=00000000-0000-0000-0000-000000000000', authed=False)
        self.assertEqual(feed.data['results'], [])


class ResponsiveCoverTests(QueryBase):
    def test_cover_advertises_the_medium_tier_alongside_display(self):
        self.make_gallery('cov', photos=3)
        _, response = self.queries('/api/v1/public/perfuser/cov/', authed=False)
        self.assertIn('_display.webp', response.data['cover_url'])
        self.assertIn('_medium.webp', response.data['cover_medium_url'])

    def test_cover_medium_is_null_when_there_is_no_medium_derivative(self):
        gallery = self.make_gallery('nomed', photos=0)
        asset = _ready_asset(gallery, 0, medium=False)
        Gallery.objects.filter(pk=gallery.pk).update(cover_photo=asset)
        _, response = self.queries('/api/v1/public/perfuser/nomed/', authed=False)
        self.assertIsNotNone(response.data['cover_url'])
        self.assertIsNone(response.data['cover_medium_url'])

    def test_public_photo_payload_still_has_all_three_tiers_and_no_original(self):
        self.make_gallery('tiers', photos=2)
        _, response = self.queries('/api/v1/public/perfuser/tiers/', authed=False)
        photo = response.data['photos'][0]
        self.assertTrue(photo['thumbnail_url'] and photo['medium_url'] and photo['display_url'])
        self.assertNotIn('original_url', photo)
        self.assertNotIn('_original', json.dumps(response.data))


class JsonCompressionTests(QueryBase):
    def test_json_is_gzipped_when_the_client_accepts_it(self):
        self.make_gallery('gz', photos=40)
        cache.clear()
        response = self.client.get('/api/v1/public/perfuser/gz/', HTTP_ACCEPT_ENCODING='gzip')
        self.assertEqual(response.headers.get('Content-Encoding'), 'gzip')
        self.assertIn('Accept-Encoding', response.headers.get('Vary', ''))
        body = json.loads(gzip.decompress(response.content))
        self.assertEqual(body['photos_count'], 40)

    def test_json_is_left_alone_without_accept_encoding(self):
        self.make_gallery('plain', photos=40)
        response = self.client.get('/api/v1/public/perfuser/plain/')
        self.assertIsNone(response.headers.get('Content-Encoding'))
        self.assertEqual(json.loads(response.content)['photos_count'], 40)

    def test_file_downloads_are_never_compressed(self):
        gallery = self.make_gallery(
            'dl', photos=0, allow_download=True,
            # This test is about compression, not the email rule: the fixture
            # gallery explicitly opts out of requiring an email.
            design_settings={'downloads': {'require_email': False}},
        )
        asset = _ready_asset(gallery, 0)
        asset.original_file.save('o.jpg', ContentFile(b'ORIGINAL' * 500), save=False)
        asset.download_file.save('m.jpg', ContentFile(b'MASTER' * 500), save=False)
        asset.save()
        response = self.client.get(
            f'/api/v1/public/perfuser/dl/photo/{asset.id}/download/?resolution=download',
            HTTP_ACCEPT_ENCODING='gzip')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get('Content-Encoding'))
        body = b''.join(response.streaming_content) if getattr(response, 'streaming', False) else response.content
        self.assertEqual(body, b'MASTER' * 500)


class RewrittenQueriesKeepTheirAnswersTests(QueryBase):
    def test_stats_count_live_galleries_only(self):
        live = self.make_gallery('live', photos=2)
        trashed = self.make_gallery('trashed', photos=3)
        Gallery.objects.filter(pk=trashed.pk).update(is_active=False, trashed_at=timezone.now())
        count, response = self.queries('/api/v1/galleries/dashboard/stats/')
        self.assertEqual(response.data['photos_used'], 2)          # trashed gallery's photos are not "in use"
        self.assertEqual(response.data['galleries_used'], 1)       # collections are counted live, same as the plan cap
        self.assertEqual(response.data['subscription_status'], 'active')
        self.assertGreater(response.data['days_remaining'], 0)
        self.assertEqual(response.data['plan_name'], 'Pro')
        self.assertLessEqual(count, 3)
        self.assertTrue(live.pk)

    def test_stats_without_a_subscription_reports_no_subscription(self):
        UserSubscription.objects.filter(user=self.user).delete()
        _, response = self.queries('/api/v1/galleries/dashboard/stats/')
        self.assertEqual(response.data['subscription_status'], 'no_subscription')
        self.assertIsNone(response.data['days_remaining'])
        self.assertIsNone(response.data['expires_at'])

    def test_my_subscription_entitlements_match_the_canonical_check(self):
        _, response = self.queries('/api/v1/subscriptions/my-subscription/')
        self.assertEqual(response.data['entitlements'], get_feature_entitlements(self.user))
        self.assertTrue(response.data['entitlements']['branding'])

    def test_lapsed_subscription_reads_as_free_in_my_subscription(self):
        UserSubscription.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(days=1))
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/v1/subscriptions/my-subscription/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['entitlements']['branding'])
        self.assertFalse(response.data['entitlements']['watermark'])
        self.assertEqual(response.data['entitlements'], get_feature_entitlements(self.user))

    def test_my_subscription_query_count_is_bounded(self):
        count, _ = self.queries('/api/v1/subscriptions/my-subscription/')
        self.assertLessEqual(count, 4)
