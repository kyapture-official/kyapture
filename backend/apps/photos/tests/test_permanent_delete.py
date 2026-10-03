# backend/apps/photos/tests/test_permanent_delete.py
"""
TASK 5.1 - permanent deletes, cover rules, photographer favorites, purge_orphans.

  COVER      the first photo to reach READY becomes the cover; a manual cover is
             never overwritten; concurrent / retried assignment is idempotent;
             deleting the cover falls back to the next READY photo, else none;
             the heart (favorite) never touches the cover
  DELETE     photo / bulk / set / collection delete removes the DB rows AND every
             storage object (original, Download Master, derivatives, video files,
             prepared ZIPs), after commit, via an idempotent task; quota drops
  SAFETY     owner-only, foreign / malformed ids are 404, a rolled-back delete
             loses no file, a failed purge is retried and logged
  ORPHANS    purge_orphans lists by default and deletes only with --delete
"""
import io
import os
import shutil
import tempfile
import threading
import time
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from apps.clients.models import DownloadJob, DownloadLog, Favorite, FavoriteList
from apps.core.storage import PrivateMediaStorage
from apps.core.utils import get_user_subscription_metrics
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet
from apps.photos.purge import ASSET_FILE_FIELDS, ensure_cover, purge_assets, run_purge
from apps.photos.tasks import _auto_assign_cover_if_missing, purge_storage_objects

User = get_user_model()


class TempMediaMixin:
    """A throwaway MEDIA_ROOT, and the purge task run inline (no broker needed)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp(prefix='kyapture-test-media-')
        cls.addClassCleanup(shutil.rmtree, cls.media_root, True)
        cls.enterClassContext(override_settings(MEDIA_ROOT=cls.media_root))
        patcher = mock.patch(
            'apps.photos.tasks.purge_storage_objects.delay',
            side_effect=lambda refs, prefixes=None: run_purge(refs, prefixes or []),
        )
        patcher.start()
        cls.addClassCleanup(patcher.stop)


def make_asset(gallery, name='p.jpg', *, order=1, ready=True, video=False, photo_set=None):
    asset = MediaAsset(
        gallery=gallery, media_type='video' if video else 'image', original_name=name, file_size=1000,
        order=order, photo_set=photo_set,
        processing_status=MediaAsset.ProcessingStatus.READY if ready else MediaAsset.ProcessingStatus.PENDING,
    )
    asset.original_file.save(name, ContentFile(b'ORIGINAL' * 20), save=False)
    if video:
        asset.poster_image.save('poster.jpg', ContentFile(b'POSTER'), save=False)
        asset.playback_file.save('play.mp4', ContentFile(b'PLAY'), save=False)
        asset.preview_file.save('prev.webm', ContentFile(b'PREV'), save=False)
    else:
        asset.download_file.save('m.jpg', ContentFile(b'MASTER'), save=False)
        asset.display_file.save('d.webp', ContentFile(b'D'), save=False)
        asset.medium_file.save('m.webp', ContentFile(b'M'), save=False)
        asset.thumbnail_file.save('t.webp', ContentFile(b'T'), save=False)
    asset.save()
    return asset


def paths_of(asset):
    return [getattr(asset, f).path for f in ASSET_FILE_FIELDS if getattr(asset, f)]


class Base(TempMediaMixin, APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='pdowner', email='pd@kyapture.com', password='Sturdy-Pass-8842!')
        self.other = User.objects.create_user(username='pdother', email='pdo@kyapture.com', password='Sturdy-Pass-8842!')
        self.gallery = Gallery.objects.create(photographer=self.user, title='Mine', slug='mine-pd', is_published=True)
        self.client.force_authenticate(user=self.user)

    def delete(self, url, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.delete(url, **kwargs)

    def post(self, url, data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, data, format='json')


# ─────────────────────────────── COVER ───────────────────────────────────────
class DefaultCoverTests(Base):
    def test_the_first_photo_to_reach_ready_becomes_the_cover(self):
        first = make_asset(self.gallery, 'a.jpg', order=1)
        _auto_assign_cover_if_missing(first)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, first.id)

    def test_a_second_upload_never_replaces_it(self):
        first, second = make_asset(self.gallery, 'a.jpg', order=1), make_asset(self.gallery, 'b.jpg', order=2)
        _auto_assign_cover_if_missing(first)
        _auto_assign_cover_if_missing(second)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, first.id)

    def test_a_manually_chosen_cover_is_never_overwritten(self):
        chosen, newcomer = make_asset(self.gallery, 'c.jpg', order=2), make_asset(self.gallery, 'n.jpg', order=1)
        Gallery.objects.filter(pk=self.gallery.pk).update(cover_photo=chosen)
        _auto_assign_cover_if_missing(newcomer)
        ensure_cover(self.gallery.pk)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, chosen.id)

    def test_assignment_is_idempotent_under_celery_retries(self):
        asset = make_asset(self.gallery)
        for _ in range(4):
            _auto_assign_cover_if_missing(asset)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, asset.id)

    def test_pending_photos_do_not_get_chosen_by_the_fallback(self):
        pending = make_asset(self.gallery, 'p.jpg', order=1, ready=False)
        ensure_cover(self.gallery.pk)
        self.gallery.refresh_from_db()
        self.assertIsNone(self.gallery.cover_photo_id)
        self.assertIsNotNone(pending)

    def test_deleting_the_cover_falls_back_to_the_next_ready_photo(self):
        cover = make_asset(self.gallery, 'a.jpg', order=1)
        make_asset(self.gallery, 'skip.jpg', order=2, ready=False)
        nxt = make_asset(self.gallery, 'c.jpg', order=3)
        Gallery.objects.filter(pk=self.gallery.pk).update(cover_photo=cover)
        self.assertEqual(self.delete(f'/api/v1/photos/photo/{cover.id}/').status_code, 200)
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, nxt.id)

    def test_deleting_the_last_ready_photo_leaves_no_cover(self):
        only = make_asset(self.gallery, 'a.jpg')
        Gallery.objects.filter(pk=self.gallery.pk).update(cover_photo=only)
        self.delete(f'/api/v1/photos/photo/{only.id}/')
        self.gallery.refresh_from_db()
        self.assertIsNone(self.gallery.cover_photo_id)

    def test_deleting_a_non_cover_photo_keeps_the_cover(self):
        cover, other = make_asset(self.gallery, 'a.jpg', order=1), make_asset(self.gallery, 'b.jpg', order=2)
        Gallery.objects.filter(pk=self.gallery.pk).update(cover_photo=cover)
        self.delete(f'/api/v1/photos/photo/{other.id}/')
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, cover.id)

    def test_bulk_delete_of_the_cover_also_falls_back(self):
        a, b, c = (make_asset(self.gallery, f'{n}.jpg', order=i) for i, n in enumerate('abc', 1))
        Gallery.objects.filter(pk=self.gallery.pk).update(cover_photo=a)
        self.post(f'/api/v1/photos/{self.gallery.slug}/delete-bulk/', {'photo_ids': [str(a.id), str(b.id)]})
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, c.id)


class CoverRaceTests(TransactionTestCase):
    """Concurrent uploads finishing at once: exactly one wins, nobody overwrites."""

    def test_concurrent_assignments_leave_exactly_one_stable_cover(self):
        user = User.objects.create_user(username='racer', email='race@kyapture.com', password='Sturdy-Pass-8842!')
        gallery = Gallery.objects.create(photographer=user, title='Race', slug='race-pd')
        assets = [
            MediaAsset.objects.create(
                gallery=gallery, media_type='image', original_name=f'{i}.jpg', file_size=1, order=i,
                processing_status='ready', original_file=f'x/{i}.jpg')
            for i in range(8)
        ]
        barrier = threading.Barrier(len(assets))

        def worker(asset):
            try:
                barrier.wait()
                _auto_assign_cover_if_missing(asset)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(a,)) for a in assets]
        [t.start() for t in threads]
        [t.join() for t in threads]
        gallery.refresh_from_db()
        winner = gallery.cover_photo_id
        self.assertIn(winner, {a.id for a in assets})
        for asset in assets:                       # late arrivals / retries change nothing
            _auto_assign_cover_if_missing(asset)
        gallery.refresh_from_db()
        self.assertEqual(gallery.cover_photo_id, winner)


class SetAsCoverAndHeartTests(Base):
    def setUp(self):
        super().setUp()
        self.a = make_asset(self.gallery, 'a.jpg', order=1)
        self.b = make_asset(self.gallery, 'b.jpg', order=2)
        Gallery.objects.filter(pk=self.gallery.pk).update(cover_photo=self.a)

    def cover(self):
        return Gallery.objects.get(pk=self.gallery.pk).cover_photo_id

    def test_set_as_cover_changes_the_cover(self):
        response = self.client.patch(f'/api/v1/galleries/{self.gallery.slug}/', {'cover_photo': str(self.b.id)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.cover(), self.b.id)

    def test_hearting_a_photo_never_changes_the_cover(self):
        for value in (True, False, True):
            r = self.client.put(f'/api/v1/photos/photo/{self.b.id}/favorite/', {'is_favorite': value}, format='json')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(self.cover(), self.a.id)

    def test_setting_the_cover_never_changes_favorites(self):
        self.client.put(f'/api/v1/photos/photo/{self.a.id}/favorite/', {'is_favorite': True}, format='json')
        self.client.patch(f'/api/v1/galleries/{self.gallery.slug}/', {'cover_photo': str(self.b.id)}, format='json')
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertEqual((self.a.is_favorite, self.b.is_favorite), (True, False))

    def test_another_photographers_photo_cannot_become_my_cover(self):
        theirs_g = Gallery.objects.create(photographer=self.other, title='Theirs', slug='theirs-pd')
        theirs = make_asset(theirs_g, 'x.jpg')
        response = self.client.patch(f'/api/v1/galleries/{self.gallery.slug}/', {'cover_photo': str(theirs.id)}, format='json')
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(self.cover(), self.a.id)


# ───────────────────────── PHOTOGRAPHER FAVORITES ─────────────────────────────
class PhotographerFavoriteTests(Base):
    def setUp(self):
        super().setUp()
        self.a = make_asset(self.gallery, 'a.jpg', order=1)
        self.b = make_asset(self.gallery, 'b.jpg', order=2)
        self.url = lambda asset: f'/api/v1/photos/photo/{asset.id}/favorite/'

    def put(self, asset, value, client=None):
        return (client or self.client).put(self.url(asset), {'is_favorite': value}, format='json')

    def test_toggle_is_idempotent_and_reported_in_the_photo_payload(self):
        self.assertEqual(self.put(self.a, True).data['is_favorite'], True)
        first = MediaAsset.objects.get(pk=self.a.pk).favorited_at
        self.put(self.a, True)
        self.assertEqual(MediaAsset.objects.get(pk=self.a.pk).favorited_at, first)
        listing = self.client.get(f'/api/v1/photos/{self.gallery.slug}/').data
        self.assertEqual({p['original_name']: p['is_favorite'] for p in listing}, {'a.jpg': True, 'b.jpg': False})
        self.assertEqual(self.put(self.a, False).data['is_favorite'], False)
        self.assertIsNone(MediaAsset.objects.get(pk=self.a.pk).favorited_at)

    def test_only_booleans_are_accepted(self):
        for bad in ('true', 1, None, [], 'yes'):
            r = self.client.put(self.url(self.a), {'is_favorite': bad}, format='json')
            self.assertEqual((r.status_code, r.data['code']), (400, 'invalid_is_favorite'), bad)
        self.assertEqual(self.client.put(self.url(self.a), {}, format='json').status_code, 400)

    def test_foreign_unknown_malformed_and_unauthenticated_are_refused(self):
        theirs = make_asset(Gallery.objects.create(photographer=self.other, title='T', slug='t-pd'), 'x.jpg')
        self.assertEqual(self.put(theirs, True).status_code, 404)
        self.assertFalse(MediaAsset.objects.get(pk=theirs.pk).is_favorite)
        self.assertEqual(self.client.put('/api/v1/photos/photo/00000000-0000-0000-0000-000000000000/favorite/', {'is_favorite': True}, format='json').status_code, 404)
        self.assertEqual(self.client.put('/api/v1/photos/photo/not-a-uuid/favorite/', {'is_favorite': True}, format='json').status_code, 404)
        self.assertEqual(self.put(self.a, True, client=APIClient()).status_code, 401)

    def test_a_trashed_collections_photo_is_not_reachable(self):
        Gallery.objects.filter(pk=self.gallery.pk).update(is_active=False)
        self.assertEqual(self.put(self.a, True).status_code, 404)

    def test_favorites_page_lists_only_my_favorites_newest_first_with_collection_info(self):
        g2 = Gallery.objects.create(photographer=self.user, title='Second', slug='second-pd')
        c = make_asset(g2, 'c.jpg')
        theirs = make_asset(Gallery.objects.create(photographer=self.other, title='T', slug='t2-pd'), 'x.jpg')
        MediaAsset.objects.filter(pk=theirs.pk).update(is_favorite=True, favorited_at=timezone.now())
        self.put(self.a, True); time.sleep(0.01); self.put(c, True)
        data = self.client.get('/api/v1/photos/favorites/all/').data
        self.assertEqual([r['original_name'] for r in data['results']], ['c.jpg', 'a.jpg'])
        self.assertEqual((data['results'][0]['gallery_slug'], data['results'][0]['gallery_title']), ('second-pd', 'Second'))
        self.assertTrue(all(r['is_favorite'] for r in data['results']))
        self.assertEqual(data['count'], 2)
        self.assertEqual(APIClient().get('/api/v1/photos/favorites/all/').status_code, 401)

    def test_favorites_page_drops_photos_of_deleted_collections_and_deleted_photos(self):
        self.put(self.a, True); self.put(self.b, True)
        self.delete(f'/api/v1/photos/photo/{self.a.id}/')
        self.assertEqual([r['original_name'] for r in self.client.get('/api/v1/photos/favorites/all/').data['results']], ['b.jpg'])
        self.delete(f'/api/v1/galleries/{self.gallery.slug}/')
        self.assertEqual(self.client.get('/api/v1/photos/favorites/all/').data['count'], 0)


# ─────────────────────────────── DELETES ─────────────────────────────────────
class PhotoDeleteTests(Base):
    def test_deleting_a_photo_removes_the_row_and_every_stored_file(self):
        asset = make_asset(self.gallery)
        files = paths_of(asset)
        self.assertEqual(len(files), 5)                 # original, Download Master, display, medium, thumbnail
        self.assertTrue(all(os.path.exists(p) for p in files))
        self.assertEqual(self.delete(f'/api/v1/photos/photo/{asset.id}/').status_code, 200)
        self.assertFalse(MediaAsset.objects.filter(pk=asset.pk).exists())
        self.assertFalse(any(os.path.exists(p) for p in files), [p for p in files if os.path.exists(p)])

    def test_a_videos_poster_preview_and_playback_files_are_removed_too(self):
        video = make_asset(self.gallery, 'v.mp4', video=True)
        files = paths_of(video)
        self.assertEqual(len(files), 4)
        self.delete(f'/api/v1/photos/photo/{video.id}/')
        self.assertFalse(any(os.path.exists(p) for p in files))

    def test_storage_usage_drops_immediately(self):
        asset = make_asset(self.gallery)
        self.assertEqual(get_user_subscription_metrics(self.user)['current_total_storage_bytes'], 1000)
        self.delete(f'/api/v1/photos/photo/{asset.id}/')
        metrics = get_user_subscription_metrics(self.user)
        self.assertEqual((metrics['current_total_storage_bytes'], metrics['current_photos_count']), (0, 0))

    def test_bulk_delete_purges_each_photo_and_ignores_foreign_ids(self):
        a, b = make_asset(self.gallery, 'a.jpg', order=1), make_asset(self.gallery, 'b.jpg', order=2)
        theirs = make_asset(Gallery.objects.create(photographer=self.other, title='T', slug='t3-pd'), 'x.jpg')
        mine_files, their_files = paths_of(a) + paths_of(b), paths_of(theirs)
        r = self.post(f'/api/v1/photos/{self.gallery.slug}/delete-bulk/', {'photo_ids': [str(a.id), str(b.id), str(theirs.id)]})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(MediaAsset.objects.filter(pk__in=[a.pk, b.pk]).exists())
        self.assertFalse(any(os.path.exists(p) for p in mine_files))
        self.assertTrue(MediaAsset.objects.filter(pk=theirs.pk).exists())
        self.assertTrue(all(os.path.exists(p) for p in their_files))      # someone else's files untouched

    def test_deleted_count_counts_photos_not_cascaded_rows(self):
        asset = make_asset(self.gallery)
        Favorite.objects.create(gallery=self.gallery, media_asset=asset, client_key='k1')
        Favorite.objects.create(gallery=self.gallery, media_asset=asset, client_key='k2')
        r = self.post(f'/api/v1/photos/{self.gallery.slug}/delete-bulk/', {'photo_ids': [str(asset.id)]})
        self.assertEqual(r.data['deleted_count'], 1)       # not 3 (1 photo + 2 cascaded favorites)

    def test_a_foreign_photo_cannot_be_deleted(self):
        theirs = make_asset(Gallery.objects.create(photographer=self.other, title='T', slug='t4-pd'), 'x.jpg')
        files = paths_of(theirs)
        self.assertEqual(self.delete(f'/api/v1/photos/photo/{theirs.id}/').status_code, 404)
        self.assertTrue(MediaAsset.objects.filter(pk=theirs.pk).exists())
        self.assertTrue(all(os.path.exists(p) for p in files))

    def test_malformed_and_unknown_ids_are_404_not_500(self):
        self.assertEqual(self.client.delete('/api/v1/photos/photo/not-a-uuid/').status_code, 404)
        self.assertEqual(self.client.delete('/api/v1/photos/photo/00000000-0000-0000-0000-000000000000/').status_code, 404)
        self.assertEqual(self.client.post(f'/api/v1/photos/{self.gallery.slug}/delete-bulk/', {'photo_ids': ['nope']}, format='json').status_code, 400)

    def test_bulk_delete_on_someone_elses_gallery_is_404(self):
        theirs_g = Gallery.objects.create(photographer=self.other, title='T', slug='t5-pd')
        theirs = make_asset(theirs_g, 'x.jpg')
        r = self.post(f'/api/v1/photos/{theirs_g.slug}/delete-bulk/', {'photo_ids': [str(theirs.id)]})
        self.assertEqual(r.status_code, 404)
        self.assertTrue(MediaAsset.objects.filter(pk=theirs.pk).exists())

    def test_unauthenticated_delete_is_401(self):
        asset = make_asset(self.gallery)
        self.assertEqual(APIClient().delete(f'/api/v1/photos/photo/{asset.id}/').status_code, 401)
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())

    def test_download_history_of_a_deleted_photo_is_kept_without_the_photo_link(self):
        asset = make_asset(self.gallery)
        DownloadLog.objects.create(gallery=self.gallery, media_asset=asset, download_type='photo', email='buyer@example.com', filename='p.jpg')
        Favorite.objects.create(gallery=self.gallery, media_asset=asset, client_key='k')
        self.delete(f'/api/v1/photos/photo/{asset.id}/')
        log = DownloadLog.objects.get()
        self.assertEqual((log.email, log.filename, log.media_asset_id), ('buyer@example.com', 'p.jpg', None))
        self.assertFalse(Favorite.objects.exists())             # visitors' favorites of the photo go with it

    def test_prepared_download_zips_are_purged_with_the_photo(self):
        asset = make_asset(self.gallery)
        storage = PrivateMediaStorage()
        name = storage.save('download_jobs/job-1/g.zip', ContentFile(b'ZIP'))
        DownloadJob.objects.create(gallery=self.gallery, state='ready', files=[{'name': 'g.zip', 'size_bytes': 3, 'storage_path': name}],
                                   expires_at=timezone.now() + timedelta(hours=1))
        self.assertTrue(storage.exists(name))
        self.delete(f'/api/v1/photos/photo/{asset.id}/')
        self.assertFalse(DownloadJob.objects.exists())
        self.assertFalse(storage.exists(name))


class DeferredAndSafeTests(Base):
    def test_files_are_only_removed_after_the_transaction_commits(self):
        asset = make_asset(self.gallery)
        files = paths_of(asset)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.delete(f'/api/v1/photos/photo/{asset.id}/')
        self.assertFalse(MediaAsset.objects.filter(pk=asset.pk).exists())
        self.assertTrue(all(os.path.exists(p) for p in files))          # nothing deleted yet
        self.assertEqual(len(callbacks), 1)                              # ONE batched purge
        for callback in callbacks:
            callback()
        self.assertFalse(any(os.path.exists(p) for p in files))

    def test_a_rolled_back_delete_loses_no_file(self):
        asset = make_asset(self.gallery)
        files = paths_of(asset)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    purge_assets(self.gallery, MediaAsset.objects.filter(pk=asset.pk))
                    raise RuntimeError('boom')
        self.assertEqual(callbacks, [])
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())
        self.assertTrue(all(os.path.exists(p) for p in files))

    def test_any_orm_delete_still_purges_every_file_including_the_download_master(self):
        asset = make_asset(self.gallery)
        files = paths_of(asset)
        self.assertTrue(asset.download_file)
        with self.captureOnCommitCallbacks(execute=True):
            MediaAsset.objects.filter(pk=asset.pk).delete()              # not through the service
        self.assertFalse(any(os.path.exists(p) for p in files))


class PurgeTaskTests(Base):
    def refs(self, asset):
        return [{'s': ASSET_FILE_FIELDS[f], 'n': getattr(asset, f).name} for f in ASSET_FILE_FIELDS if getattr(asset, f)]

    def test_the_purge_is_idempotent(self):
        asset = make_asset(self.gallery)
        refs = self.refs(asset)
        self.assertEqual(run_purge(refs, []), ([], []))
        self.assertEqual(run_purge(refs, []), ([], []))                  # everything already gone: still success
        self.assertEqual(purge_storage_objects.apply(args=[refs, []]).result, 0)

    def test_failures_are_retried_for_only_the_failed_objects_then_logged(self):
        asset = make_asset(self.gallery)
        refs = self.refs(asset)
        real = __import__('apps.photos.purge', fromlist=['delete_object']).delete_object
        calls = []

        def flaky(kind, name):
            calls.append(name)
            if name.endswith('_original.jpg') or '_original' in name:
                raise OSError('storage hiccup')
            return real(kind, name)

        with mock.patch('apps.photos.purge.delete_object', side_effect=flaky):
            failed, _ = run_purge(refs, [])
        self.assertEqual([r['n'] for r in failed], [r['n'] for r in refs if '_original' in r['n']])
        self.assertTrue(os.path.exists(asset.original_file.path))
        self.assertFalse(os.path.exists(asset.display_file.path))
        # the retry (real storage again) finishes the job
        self.assertEqual(run_purge(failed, []), ([], []))
        self.assertFalse(os.path.exists(asset.original_file.path))

    def test_permanent_failure_is_logged_with_the_object_names(self):
        refs = [{'s': 'private', 'n': 'photographers/x/galleries/y/photos/stuck_original.jpg'}]
        with mock.patch('apps.photos.purge.delete_object', side_effect=OSError('denied')):
            with self.assertLogs('apps.photos.tasks', level='ERROR') as logs:
                result = purge_storage_objects.apply(args=[refs, []], retries=5)
        self.assertEqual(result.result, 1)
        self.assertIn('stuck_original.jpg', '\n'.join(logs.output))


class SetAndCollectionDeleteTests(Base):
    def setUp(self):
        super().setUp()
        self.highlights = PhotoSet.objects.get(gallery=self.gallery, name='Highlights')
        self.extra = PhotoSet.objects.create(gallery=self.gallery, name='Party', order=5)
        self.keep = make_asset(self.gallery, 'keep.jpg', order=1, photo_set=self.highlights)
        self.doomed = make_asset(self.gallery, 'doomed.jpg', order=2, photo_set=self.extra)

    def test_deleting_a_set_permanently_deletes_its_photos_and_files_only(self):
        doomed_files, keep_files = paths_of(self.doomed), paths_of(self.keep)
        r = self.delete(f'/api/v1/photos/{self.gallery.slug}/sets/{self.extra.id}/')
        self.assertEqual((r.status_code, r.data['deleted_photos']), (200, 1))
        self.assertFalse(PhotoSet.objects.filter(pk=self.extra.pk).exists())
        self.assertFalse(MediaAsset.objects.filter(pk=self.doomed.pk).exists())
        self.assertFalse(any(os.path.exists(p) for p in doomed_files))
        self.assertTrue(MediaAsset.objects.filter(pk=self.keep.pk).exists())
        self.assertTrue(all(os.path.exists(p) for p in keep_files))

    def test_deleting_the_set_holding_the_cover_falls_back(self):
        Gallery.objects.filter(pk=self.gallery.pk).update(cover_photo=self.doomed)
        self.delete(f'/api/v1/photos/{self.gallery.slug}/sets/{self.extra.id}/')
        self.gallery.refresh_from_db()
        self.assertEqual(self.gallery.cover_photo_id, self.keep.id)

    def test_the_last_set_and_foreign_or_malformed_sets_are_refused(self):
        theirs_g = Gallery.objects.create(photographer=self.other, title='T', slug='t6-pd')
        theirs_set = PhotoSet.objects.get(gallery=theirs_g, name='Highlights')
        self.assertEqual(self.client.delete(f'/api/v1/photos/{theirs_g.slug}/sets/{theirs_set.id}/').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/v1/photos/{self.gallery.slug}/sets/{theirs_set.id}/').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/v1/photos/{self.gallery.slug}/sets/not-a-uuid/').status_code, 404)
        PhotoSet.objects.filter(pk=self.extra.pk).delete()
        self.assertEqual(self.client.delete(f'/api/v1/photos/{self.gallery.slug}/sets/{self.highlights.id}/').status_code, 400)
        self.assertTrue(MediaAsset.objects.filter(pk=self.keep.pk).exists())

    def test_deleting_a_collection_removes_every_row_file_and_zip(self):
        video = make_asset(self.gallery, 'v.mp4', order=3, video=True)
        all_files = paths_of(self.keep) + paths_of(self.doomed) + paths_of(video)
        prefix = os.path.join(self.media_root, 'photographers', str(self.user.id), 'galleries', str(self.gallery.id))
        # a stray object under the collection (e.g. an HLS chunk) must go too
        stray = os.path.join(prefix, 'videos', 'abc', 'hls', 'seg0.ts')
        os.makedirs(os.path.dirname(stray), exist_ok=True)
        with open(stray, 'wb') as handle:
            handle.write(b'TS')
        storage = PrivateMediaStorage()
        zip_name = storage.save('download_jobs/job-2/g.zip', ContentFile(b'ZIP'))
        DownloadJob.objects.create(gallery=self.gallery, state='ready', files=[{'name': 'g.zip', 'size_bytes': 3, 'storage_path': zip_name}],
                                   expires_at=timezone.now() + timedelta(hours=1))
        DownloadLog.objects.create(gallery=self.gallery, download_type='gallery', email='x@example.com')
        fl = FavoriteList.objects.create(gallery=self.gallery, client_key='k', name='My Favorites')
        Favorite.objects.create(gallery=self.gallery, media_asset=self.keep, client_key='k', favorite_list=fl)
        other_g = Gallery.objects.create(photographer=self.user, title='Other', slug='other-pd')
        other_files = paths_of(make_asset(other_g, 'o.jpg'))

        self.assertTrue(all(os.path.exists(p) for p in all_files))
        r = self.delete(f'/api/v1/galleries/{self.gallery.slug}/')
        self.assertEqual(r.status_code, 200)

        self.assertFalse(Gallery.objects.filter(pk=self.gallery.pk).exists())
        for model in (MediaAsset, PhotoSet, DownloadLog, DownloadJob, Favorite, FavoriteList):
            self.assertFalse(model.objects.filter(gallery_id=self.gallery.pk).exists(), model.__name__)
        self.assertFalse(any(os.path.exists(p) for p in all_files))
        self.assertFalse(os.path.exists(stray))
        self.assertFalse(os.path.exists(prefix), 'the collection directory is gone')
        self.assertFalse(storage.exists(zip_name))
        self.assertTrue(Gallery.objects.filter(pk=other_g.pk).exists())            # another collection untouched
        self.assertTrue(all(os.path.exists(p) for p in other_files))
        self.assertEqual(get_user_subscription_metrics(self.user)['current_galleries_count'], 1)

    def test_a_foreign_collection_cannot_be_deleted(self):
        theirs_g = Gallery.objects.create(photographer=self.other, title='T', slug='t7-pd')
        files = paths_of(make_asset(theirs_g, 'x.jpg'))
        self.assertEqual(self.delete(f'/api/v1/galleries/{theirs_g.slug}/').status_code, 404)
        self.assertTrue(Gallery.objects.filter(pk=theirs_g.pk).exists())
        self.assertTrue(all(os.path.exists(p) for p in files))
        self.assertEqual(APIClient().delete(f'/api/v1/galleries/{self.gallery.slug}/').status_code, 401)
        self.assertEqual(self.client.delete('/api/v1/galleries/nope-nope/').status_code, 404)

    def test_the_old_trash_sweep_now_also_removes_files(self):
        from apps.galleries.tasks import purge_trashed_galleries
        files = paths_of(self.keep)
        Gallery.objects.filter(pk=self.gallery.pk).update(is_active=False, trashed_at=timezone.now() - timedelta(days=40))
        with self.captureOnCommitCallbacks(execute=True):
            purge_trashed_galleries()
        self.assertFalse(Gallery.objects.filter(pk=self.gallery.pk).exists())
        self.assertFalse(any(os.path.exists(p) for p in files))


# ─────────────────────────────── purge_orphans ───────────────────────────────
class PurgeOrphansTests(Base):
    def setUp(self):
        super().setUp()
        # A media root of its own per test: a scan must only ever see this test's files.
        self.media_root = tempfile.mkdtemp(prefix='kyapture-test-orphans-')
        self.addCleanup(shutil.rmtree, self.media_root, True)
        self.enterContext(override_settings(MEDIA_ROOT=self.media_root))
        self.asset = make_asset(self.gallery)
        root = os.path.join(self.media_root, 'photographers', str(self.user.id), 'galleries', str(self.gallery.id), 'photos')
        self.orphan = os.path.join(root, 'ghost_original.jpg')
        with open(self.orphan, 'wb') as handle:
            handle.write(b'GHOST')
        self.zip_orphan = os.path.join(self.media_root, 'download_jobs', 'dead-job', 'x.zip')
        os.makedirs(os.path.dirname(self.zip_orphan), exist_ok=True)
        with open(self.zip_orphan, 'wb') as handle:
            handle.write(b'ZIP')
        os.makedirs(os.path.join(self.media_root, 'photographer_logos'), exist_ok=True)
        self.logo = os.path.join(self.media_root, 'photographer_logos', 'logo.png')
        with open(self.logo, 'wb') as handle:
            handle.write(b'LOGO')
        old = time.time() - 3 * 3600
        for path in (self.orphan, self.zip_orphan, self.logo):
            os.utime(path, (old, old))

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        call_command('purge_orphans', *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_default_is_a_dry_run_that_lists_orphans_and_deletes_nothing(self):
        for args in ((), ('--dry-run',)):
            out, _ = self.invoke(*args)
            self.assertIn('ghost_original.jpg', out)
            self.assertIn('dead-job/x.zip', out)
            self.assertIn('DRY RUN', out)
            self.assertTrue(os.path.exists(self.orphan) and os.path.exists(self.zip_orphan))

    def test_referenced_files_and_out_of_scope_files_are_never_listed(self):
        out, _ = self.invoke()
        for path in paths_of(self.asset):
            self.assertNotIn(os.path.basename(path), out)
        self.assertNotIn('logo.png', out)                       # avatars/logos are not collection storage
        self.assertIn('2 orphaned object(s)', out)

    def test_delete_flag_removes_only_the_orphans(self):
        out, _ = self.invoke('--delete')
        self.assertIn('Deleted 2 of 2', out)
        self.assertFalse(os.path.exists(self.orphan))
        self.assertFalse(os.path.exists(self.zip_orphan))
        self.assertTrue(all(os.path.exists(p) for p in paths_of(self.asset)))      # real photo files untouched
        self.assertTrue(os.path.exists(self.logo))
        self.assertIn('0 orphaned', self.invoke()[0])                                  # a second run finds nothing

    def test_recent_files_are_skipped_so_an_in_flight_upload_is_safe(self):
        os.utime(self.orphan, None)                                                  # modified just now
        out, _ = self.invoke('--delete')
        self.assertTrue(os.path.exists(self.orphan))
        self.assertNotIn('ghost_original.jpg', out)
        self.assertIn('Deleted 1 of 1', out)                                         # only the old zip

    def test_a_live_prepared_download_zip_is_not_an_orphan(self):
        storage = PrivateMediaStorage()
        name = storage.save('download_jobs/live-job/g.zip', ContentFile(b'ZIP'))
        DownloadJob.objects.create(gallery=self.gallery, state='ready', files=[{'name': 'g.zip', 'size_bytes': 3, 'storage_path': name}],
                                   expires_at=timezone.now() + timedelta(hours=1))
        old = time.time() - 3 * 3600
        os.utime(storage.path(name), (old, old))
        out, _ = self.invoke('--delete')
        self.assertTrue(storage.exists(name))
        self.assertNotIn('live-job', out)

    def test_dry_run_and_delete_together_are_refused(self):
        _, err = self.invoke('--dry-run', '--delete')
        self.assertIn('either --dry-run or --delete', err)
        self.assertTrue(os.path.exists(self.orphan))
