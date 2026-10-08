# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/download_jobs.py
"""
Background preparation of gallery / set ZIP downloads.

The public download POST authorizes the request (gallery, password session,
download PIN/email token, size policy, selection limits) and then only
*creates a job* here; the ZIP itself is compiled by a Celery task, written to
PRIVATE storage, and handed out through the gated status/file endpoints in
views.py. Nothing in this module trusts the caller: every gate has already run
in the view, and the file endpoints re-run them.

Archives are named ``{gallery-slug}-photo-download-{n}of{m}.zip``; a download
whose photos pass DOWNLOAD_ZIP_PART_MAX_BYTES is split into several parts.
"""
import logging
import os
import tempfile
import time
import zipfile
from datetime import timedelta

from django.conf import settings
from django.core.files import File
from django.utils import timezone

from apps.core.storage import PrivateMediaStorage
from apps.core.utils import sanitize_download_filename
from apps.core.watermark import build_watermark_spec
from apps.photos.models import MediaAsset

from .download_access import effective_high_res_mode, web_px_for_gallery
from .models import DownloadJob
from .web_size import build_cached, read_cached, watermark_state

logger = logging.getLogger(__name__)

STORAGE_PREFIX = 'download_jobs'


def archive_filename(gallery, part=1, total=1):
    """``{gallery-slug}-photo-download-{n}of{m}.zip``, made header/zip safe."""
    return sanitize_download_filename(
        f'{gallery.slug}-photo-download-{part}of{total}.zip', fallback='photo-download-1of1.zip'
    )


def job_assets(gallery, photo_set=None, asset_ids=None):
    """
    The assets a job packages. Mirrors what the public gallery exposes: READY
    images/videos that still have an original on disk, optionally limited to
    one set and/or an explicit id selection — always scoped to THIS gallery.
    """
    qs = MediaAsset.objects.filter(
        gallery=gallery,
        processing_status=MediaAsset.ProcessingStatus.READY,
        media_type__in=[MediaAsset.MediaType.IMAGE, MediaAsset.MediaType.VIDEO],
    ).exclude(original_file='')
    if photo_set is not None:
        qs = qs.filter(photo_set=photo_set)
    if asset_ids:
        qs = qs.filter(id__in=asset_ids)
    return qs.select_related('photo_set').order_by('order', 'created_at')


def size_limit_error(assets):
    """Returns an error code when the selection is above the technical ceilings, else None."""
    if len(assets) > settings.SYNC_ZIP_MAX_ASSET_COUNT:
        return 'download_too_large'
    if sum(asset.file_size or 0 for asset in assets) > settings.SYNC_ZIP_MAX_TOTAL_BYTES:
        return 'download_too_large'
    return None


def job_variant(gallery, resolution):
    """
    The settings a job's files depend on, as one short string: Web Size px and
    the gallery's current watermark state, or the effective High Resolution mode
    (3600 px master / true original). A request is only answered by an earlier
    job made under the same variant, so switching the watermark, the px or the
    mode never hands back a ZIP built under the old setting.
    """
    if resolution == 'web':
        return f'web:{web_px_for_gallery(gallery)}:{watermark_state(build_watermark_spec(gallery))}'
    return f'{resolution}:{effective_high_res_mode(gallery)}'


def find_reusable_job(gallery, *, photo_set, resolution, asset_ids, email):
    """
    An identical request (same gallery, scope, size, selection, visitor and
    settings variant) that is still preparing, or ready and unexpired, is
    reused — a page refresh or a double click must not queue a second multi-GB ZIP.
    """
    now = timezone.now()
    candidates = DownloadJob.objects.filter(
        gallery=gallery, photo_set=photo_set, resolution=resolution,
        asset_ids=sorted(str(i) for i in asset_ids), email=email,
        variant=job_variant(gallery, resolution),
    )
    stale_cutoff = now - timedelta(seconds=settings.DOWNLOAD_JOB_STALE_SECONDS)
    for job in candidates.order_by('-created_at')[:5]:
        if job.state == DownloadJob.State.READY and job.expires_at and job.expires_at > now:
            return job
        if job.state == DownloadJob.State.PREPARING and job.created_at > stale_cutoff:
            return job
    return None


def expire_if_stale(job):
    """A job whose worker vanished must not read as 'preparing' forever."""
    if job.state != DownloadJob.State.PREPARING:
        return job
    if job.created_at < timezone.now() - timedelta(seconds=settings.DOWNLOAD_JOB_STALE_SECONDS):
        job.state = DownloadJob.State.FAILED
        job.error_code = 'prepare_timeout'
        job.save(update_fields=['state', 'error_code', 'updated_at'])
    return job


def is_expired(job):
    return bool(job.state == DownloadJob.State.READY and job.expires_at and job.expires_at <= timezone.now())


def job_files_exist(job):
    """True when every stored ZIP of a READY job is still in private storage."""
    storage = PrivateMediaStorage()
    try:
        return all(storage.exists(entry['storage_path']) for entry in (job.files or []))
    except Exception:
        # A storage hiccup must not flip a good job to "missing"; the file
        # endpoint's own open() is the final judge.
        logger.warning('Could not verify the stored files of download job %s', job.id)
        return True


def mark_file_missing(job):
    """The stored ZIP vanished: the job can no longer be served, so it says so."""
    logger.error('Download job %s is ready but its stored file is missing', job.id)
    return _fail(job, 'file_missing')


def _fail(job, code):
    job.state = DownloadJob.State.FAILED
    job.error_code = code
    job.files = []
    job.save(update_fields=['state', 'error_code', 'files', 'updated_at'])
    return job


def _source_size(field):
    try:
        return int(field.size or 0)
    except Exception:
        return 0


def _prepare_entry(asset, job, gallery, used_names, web_spec=None):
    """
    What goes into the archive for `asset`: (entry_name, size, data, field).
    'data' is set for a Web Size image at the exact chosen px (cached per
    photo/px/watermark state, see web_size.py -- encoded here only on a miss,
    and this already runs inside the job's Celery task); otherwise 'field' is
    the stored file to stream. None when the asset has no usable source.
    `web_spec` is the gallery's watermark, resolved once per job.
    """
    # Imported here to avoid a views <-> download_jobs import cycle.
    from .views import _resolve_zip_source, _unique_zip_entry_name, _zip_entry_base_name

    if job.resolution == 'web' and asset.media_type == MediaAsset.MediaType.IMAGE:
        key = build_cached(asset, web_px_for_gallery(gallery), web_spec)
        data = read_cached(key) if key else None
        if data is not None:
            stem = os.path.splitext(sanitize_download_filename(asset.original_name, fallback=str(asset.id)))[0]
            return _unique_zip_entry_name(f'{stem}.jpg', used_names), len(data), data, None

    source_field = _resolve_zip_source(asset, job.resolution, gallery)
    if not source_field:
        return None
    entry_name = _unique_zip_entry_name(_zip_entry_base_name(asset, source_field, job.resolution), used_names)
    return entry_name, _source_size(source_field), None, source_field


def run_download_job(job_id):
    """
    Task body: compile the job's ZIP part(s) (ZIP_STORED -- photos/videos are
    already compressed), store them privately, mark the job READY. A new part
    starts once the next photo would push the current one past
    DOWNLOAD_ZIP_PART_MAX_BYTES; the parts are named
    ``{gallery-slug}-photo-download-{n}of{m}.zip``. Safe to call twice: only a
    PREPARING job is ever worked on.
    """
    try:
        job = DownloadJob.objects.select_related('gallery__photographer', 'photo_set').get(id=job_id)
    except DownloadJob.DoesNotExist:
        return None
    if job.state != DownloadJob.State.PREPARING:
        return job.state

    gallery = job.gallery
    if not gallery.photographer.is_active:      # 7.5-A: the owner was suspended after the visitor asked
        _fail(job, 'owner_unavailable')
        return job.state
    assets = list(job_assets(gallery, job.photo_set, job.asset_ids))
    if not assets:
        _fail(job, 'no_media')
        return job.state
    if size_limit_error(assets):
        _fail(job, 'download_too_large')
        return job.state

    part_limit = max(1, int(settings.DOWNLOAD_ZIP_PART_MAX_BYTES))
    parts = []          # {'path': temp file, 'count': photos, 'bytes': payload bytes, 'sets': set names}
    stored_names = []
    storage = PrivateMediaStorage()
    archive = None
    try:
        used_names = set()
        web_spec = build_watermark_spec(gallery) if job.resolution == 'web' else None

        def start_part():
            fd, path = tempfile.mkstemp(suffix='.zip')
            os.close(fd)
            parts.append({'path': path, 'count': 0, 'bytes': 0, 'sets': []})
            return zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED)

        for asset in assets:
            prepared = _prepare_entry(asset, job, gallery, used_names, web_spec)
            if prepared is None:
                continue
            entry_name, size, data, source_field = prepared
            if archive is None or (parts[-1]['count'] and parts[-1]['bytes'] + size > part_limit):
                if archive is not None:
                    archive.close()
                archive = start_part()
            zinfo = zipfile.ZipInfo(filename=entry_name, date_time=time.localtime(time.time())[:6])
            zinfo.compress_type = zipfile.ZIP_STORED
            try:
                if data is not None:
                    archive.writestr(zinfo, data)
                else:
                    source_field.open('rb')
                    with archive.open(zinfo, 'w', force_zip64=True) as destination:
                        for chunk in source_field.chunks(chunk_size=1024 * 1024):
                            destination.write(chunk)
                parts[-1]['count'] += 1
                parts[-1]['bytes'] += size
                set_name = asset.photo_set.name if asset.photo_set_id else None
                if set_name and set_name not in parts[-1]['sets']:
                    parts[-1]['sets'].append(set_name)
            except Exception:
                # A photo that cannot be written must not be dropped quietly: the
                # ZIP would reach the client short of what was asked for. The
                # outer handler fails the whole job and removes every part.
                logger.exception('Failed to add asset %s to download job %s', asset.id, job.id)
                raise
            finally:
                if source_field is not None:
                    source_field.close()
        if archive is not None:
            archive.close()
            archive = None

        parts = [part for part in parts if part['count']]
        if not parts:
            _fail(job, 'no_media')
            return job.state

        files = []
        for number, part in enumerate(parts, start=1):
            name = archive_filename(gallery, number, len(parts))
            with open(part['path'], 'rb') as handle:
                stored_name = storage.save(f'{STORAGE_PREFIX}/{job.id}/{name}', File(handle))
            stored_names.append(stored_name)
            files.append({
                'name': name, 'size_bytes': os.path.getsize(part['path']), 'storage_path': stored_name,
                'photo_count': part['count'], 'set_names': part['sets'],
            })

        job.files = files
        job.state = DownloadJob.State.READY
        job.error_code = ''
        job.expires_at = timezone.now() + timedelta(seconds=settings.DOWNLOAD_JOB_TTL_SECONDS)
        job.save(update_fields=['files', 'state', 'error_code', 'expires_at', 'updated_at'])
    except Exception:
        logger.exception('Download job %s failed', job.id)
        for stored_name in stored_names:
            _delete_stored(storage, stored_name)
        _fail(job, 'prepare_failed')
        return job.state
    finally:
        if archive is not None:
            archive.close()
        for part in parts:
            try:
                os.remove(part['path'])
            except OSError:
                pass

    send_ready_email(job)
    return job.state


def send_ready_email(job):
    """Queues the "photos are ready" email (its own Celery task); a queueing problem never affects the job."""
    if not job.email:
        logger.info('Download-ready email for job %s: skipped (no email)', job.id)
        return False
    from .tasks import send_download_ready_email   # tasks imports this module lazily too

    try:
        send_download_ready_email.delay(str(job.id))
        logger.info('Download-ready email for job %s: queued', job.id)
        return True
    except Exception:
        logger.exception('Download-ready email for job %s: failed (could not queue)', job.id)
        return False


def _delete_stored(storage, name):
    try:
        storage.delete(name)
    except Exception:
        logger.warning('Could not delete stored download file %s', name)
        return
    # Local storage leaves the (now empty) per-job directory behind.
    try:
        directory = os.path.dirname(storage.path(name))
        os.rmdir(directory)
    except (AttributeError, NotImplementedError, OSError):
        pass


def delete_job_files(job):
    storage = PrivateMediaStorage()
    for entry in job.files or []:
        path = entry.get('storage_path')
        if path:
            _delete_stored(storage, path)


def job_storage_refs(jobs):
    """Purge-task references for the stored ZIPs of the given jobs (private storage)."""
    return [
        {'s': 'private', 'n': entry['storage_path']}
        for job in jobs for entry in (job.files or []) if entry.get('storage_path')
    ]


def purge_expired_jobs():
    """
    Removes jobs past their expiry (READY) or abandoned (never finished within
    a day), deleting their stored ZIPs first. Returns how many were purged.
    """
    now = timezone.now()
    expired = DownloadJob.objects.filter(expires_at__lte=now) | DownloadJob.objects.filter(
        expires_at__isnull=True, created_at__lte=now - timedelta(days=1)
    )
    purged = 0
    for job in expired.distinct():
        delete_job_files(job)
        job.delete()
        purged += 1
    if purged:
        logger.info('[purge_expired_download_jobs] Purged %s job(s).', purged)
    return purged
