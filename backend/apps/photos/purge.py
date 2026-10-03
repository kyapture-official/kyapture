# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/purge.py
"""
PERMANENT deletion of photos, sets and collections - database rows AND every
storage object they own.

One mechanism, used by every delete path (the photo / bulk / set / collection
views, the legacy trash sweep, and - as a safety net - MediaAsset's post_delete
signal for any cascade):

  1. the rows are deleted inside a transaction;
  2. the storage objects they owned are collected (original, Download Master,
     display / medium / thumbnail derivatives - which carry the watermark -,
     video poster / preview / playback, and any prepared download ZIPs);
  3. transaction.on_commit queues ONE idempotent Celery task that deletes them.
     A rolled-back delete therefore never loses a file, and a committed delete
     never leaves a file behind even if the web request dies right after.

The purge task retries with backoff, treats "already gone" as success, and logs
every object it could not delete (apps/photos management command
`purge_orphans` finds whatever a permanently failed purge left behind).

Quota needs no bookkeeping: usage is computed from the live MediaAsset rows
(apps.core.utils.get_user_subscription_metrics), so it drops the moment the rows
are deleted.

Activity history (our choice): download history of a deleted PHOTO is kept as a
row without the photo link (who downloaded, when, filename) because it is lead
history; the photo's visitor favorites go with it. Deleting a whole COLLECTION
deletes its activity too - there is nothing left for it to describe.
"""
import logging
import threading
from contextlib import contextmanager

from django.db import transaction
from django.db.models import OuterRef, Subquery

from apps.core.storage import PrivateMediaStorage, PublicMediaStorage

logger = logging.getLogger(__name__)

PRIVATE = 'private'
PUBLIC = 'public'

# Which storage each MediaAsset file field lives in (see apps/photos/models.py).
ASSET_FILE_FIELDS = {
    'original_file': PRIVATE,
    'download_file': PRIVATE,       # the Download Master
    'display_file': PUBLIC,         # display / medium / thumbnail carry the watermark
    'medium_file': PUBLIC,
    'thumbnail_file': PUBLIC,
    'poster_image': PUBLIC,
    'preview_file': PUBLIC,
    'playback_file': PUBLIC,
}
PURGE_CHUNK = 200
PURGE_MAX_RETRIES = 5


def storage_for(kind):
    return PrivateMediaStorage() if kind == PRIVATE else PublicMediaStorage()


def asset_refs(asset):
    """[{'s': storage kind, 'n': object name}] for every file an asset owns."""
    refs = []
    for field, kind in ASSET_FILE_FIELDS.items():
        name = getattr(getattr(asset, field, None), 'name', None)
        if name:
            refs.append({'s': kind, 'n': name})
    return refs


def gallery_prefix(gallery):
    """Every object of a collection lives under this key prefix (originals, derivatives, HLS...)."""
    return f'photographers/{gallery.photographer_id}/galleries/{gallery.pk}/'


# ─── collecting what to delete ───────────────────────────────────────────────

class _Collector(threading.local):
    def __init__(self):
        self.stack = []


_collector = _Collector()


class PurgeBatch:
    def __init__(self):
        self.refs = []
        self.prefixes = []

    def add_refs(self, refs):
        self.refs.extend(refs)

    def add_prefix(self, kind, prefix):
        self.prefixes.append({'s': kind, 'n': prefix})


@contextmanager
def collecting_purges():
    """
    While active, MediaAsset deletions (explicit or cascaded) add their storage
    objects to ONE batch instead of queueing a task each; leaving the block
    schedules a single on-commit purge.
    """
    batch = PurgeBatch()
    _collector.stack.append(batch)
    try:
        yield batch
    finally:
        _collector.stack.pop()
    schedule_purge(batch.refs, batch.prefixes)


def schedule_purge(refs, prefixes=()):
    """Queue the idempotent purge after the surrounding transaction commits."""
    refs = list({(r['s'], r['n']): r for r in refs}.values())      # de-duplicate
    prefixes = list({(p['s'], p['n']): p for p in prefixes}.values())
    if not refs and not prefixes:
        return
    from .tasks import purge_storage_objects

    def enqueue():
        for start in range(0, max(len(refs), 1), PURGE_CHUNK):
            chunk = refs[start:start + PURGE_CHUNK]
            purge_storage_objects.delay(chunk, prefixes if start == 0 else [])

    # robust: a broker hiccup is logged, never raised into the request that deleted the rows
    transaction.on_commit(enqueue, robust=True)


def queue_asset_files(asset):
    """Called from MediaAsset's post_delete signal for every deleted asset."""
    refs = asset_refs(asset)
    if _collector.stack:
        _collector.stack[-1].add_refs(refs)
    else:
        schedule_purge(refs)


# ─── deleting storage objects (runs in the Celery task) ──────────────────────

def delete_object(kind, name):
    """Delete one object; a missing object counts as deleted. Raises on a real failure."""
    storage = storage_for(kind)
    storage.delete(name)


def delete_prefix(kind, prefix):
    """Recursively delete every object under `prefix` (and the emptied local directories)."""
    storage = storage_for(kind)
    try:
        directories, files = storage.listdir(prefix)
    except (FileNotFoundError, NotADirectoryError):
        return 0
    removed = 0
    for name in files:
        storage.delete(f'{prefix}{name}')
        removed += 1
    for directory in directories:
        removed += delete_prefix(kind, f'{prefix}{directory}/')
    try:
        import os
        os.rmdir(storage.path(prefix))
    except (AttributeError, NotImplementedError, OSError):
        pass   # object stores have no directories; a non-empty local dir is simply left
    return removed


def run_purge(refs, prefixes):
    """Delete everything given; returns (failed_refs, failed_prefixes)."""
    failed_refs, failed_prefixes = [], []
    for ref in refs:
        try:
            delete_object(ref['s'], ref['n'])
        except Exception:
            logger.exception('[purge] could not delete %s object %s', ref['s'], ref['n'])
            failed_refs.append(ref)
    for prefix in prefixes:
        try:
            delete_prefix(prefix['s'], prefix['n'])
        except Exception:
            logger.exception('[purge] could not delete %s prefix %s', prefix['s'], prefix['n'])
            failed_prefixes.append(prefix)
    return failed_refs, failed_prefixes


# ─── covers ──────────────────────────────────────────────────────────────────

def ensure_cover(gallery_id):
    """
    A collection with no cover gets its first READY photo (by order) as cover.

    One conditional UPDATE ... WHERE cover_photo_id IS NULL with a subquery, so
    it is atomic, idempotent (safe under Celery retries and concurrent
    deletes/uploads) and can never overwrite a cover someone already chose.
    No READY photo left -> the cover simply stays empty.
    """
    from apps.galleries.models import Gallery
    from .models import MediaAsset

    first_ready = (
        MediaAsset.objects
        .filter(gallery=OuterRef('pk'), processing_status=MediaAsset.ProcessingStatus.READY)
        .order_by('order', 'created_at')
        .values('pk')[:1]
    )
    return Gallery.objects.filter(pk=gallery_id, cover_photo__isnull=True).update(cover_photo=Subquery(first_ready))


# ─── the delete services ─────────────────────────────────────────────────────

def _drop_prepared_downloads(gallery):
    """Prepared download ZIPs may contain what is being deleted: remove them (rows + files)."""
    from apps.clients.download_jobs import job_storage_refs
    from apps.clients.models import DownloadJob

    jobs = list(DownloadJob.objects.filter(gallery=gallery))
    refs = job_storage_refs(jobs)
    if jobs:
        DownloadJob.objects.filter(pk__in=[j.pk for j in jobs]).delete()
    return refs


def purge_assets(gallery, queryset):
    """Permanently delete the given assets of `gallery`. Returns how many rows were deleted."""
    with transaction.atomic():
        with collecting_purges() as batch:
            ids = list(queryset.values_list('pk', flat=True))
            if not ids:
                return 0
            from .models import MediaAsset
            batch.add_refs(_drop_prepared_downloads(gallery))
            _, per_model = MediaAsset.objects.filter(pk__in=ids, gallery=gallery).delete()   # signal adds the files
            ensure_cover(gallery.pk)
    # Count PHOTOS only: QuerySet.delete() also counts cascaded rows (visitor favorites...),
    # which would make the UI read a clean delete as a partial failure.
    return per_model.get(MediaAsset._meta.label, 0)


def purge_photo_set(gallery, photo_set):
    """Permanently delete a set AND the photos in it (rows + files). Returns the photo count removed."""
    from .models import MediaAsset
    with transaction.atomic():
        with collecting_purges() as batch:
            batch.add_refs(_drop_prepared_downloads(gallery))
            _, per_model = MediaAsset.objects.filter(gallery=gallery, photo_set=photo_set).delete()
            count = per_model.get(MediaAsset._meta.label, 0)
            photo_set.delete()
            ensure_cover(gallery.pk)
    return count


def purge_gallery(gallery):
    """Permanently delete a whole collection: every row, every file, every prepared ZIP."""
    with transaction.atomic():
        with collecting_purges() as batch:
            batch.add_refs(_drop_prepared_downloads(gallery))
            prefix = gallery_prefix(gallery)
            batch.add_prefix(PRIVATE, prefix)
            batch.add_prefix(PUBLIC, prefix)
            gallery.delete()        # cascades assets (their files are collected by the signal), sets, activity...
