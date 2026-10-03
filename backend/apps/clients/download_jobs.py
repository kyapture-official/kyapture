# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/download_jobs.py
"""
Background preparation of gallery / set ZIP downloads.

The public download POST authorizes the request (gallery, password session,
download PIN/email token, size policy, selection limits) and then only
*creates a job* here; the ZIP itself is compiled by a Celery task, written to
PRIVATE storage, and handed out through the gated status/file endpoints in
views.py. Nothing in this module trusts the caller: every gate has already run
in the view, and the file endpoints re-run them.

Archives are always a single part named
``{gallery-slug}-photo-download-1of1.zip`` — there is no multi-part splitting
in the backend, so ``n of m`` is always ``1of1``.
"""
import logging
import os
import tempfile
import time
import zipfile
from datetime import timedelta

from django.conf import settings
from django.core.files import File
from django.core.mail import send_mail
from django.utils import timezone

from apps.core.storage import PrivateMediaStorage
from apps.core.utils import sanitize_download_filename
from apps.photos.models import MediaAsset

from .models import DownloadJob

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
    return qs.order_by('order', 'created_at')


def size_limit_error(assets):
    """Returns an error code when the selection is above the technical ceilings, else None."""
    if len(assets) > settings.SYNC_ZIP_MAX_ASSET_COUNT:
        return 'download_too_large'
    if sum(asset.file_size or 0 for asset in assets) > settings.SYNC_ZIP_MAX_TOTAL_BYTES:
        return 'download_too_large'
    return None


def find_reusable_job(gallery, *, photo_set, resolution, asset_ids, email):
    """
    An identical request (same gallery, scope, size, selection and visitor)
    that is still preparing, or ready and unexpired, is reused — a page
    refresh or a double click must not queue a second multi-GB ZIP.
    """
    now = timezone.now()
    candidates = DownloadJob.objects.filter(
        gallery=gallery, photo_set=photo_set, resolution=resolution,
        asset_ids=sorted(str(i) for i in asset_ids), email=email,
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


def run_download_job(job_id):
    """
    Task body: compile the job's ZIP (ZIP_STORED — photos/videos are already
    compressed), store it privately, mark the job READY. Safe to call twice:
    only a PREPARING job is ever worked on.
    """
    # Same helpers the single-file endpoint uses, so a ZIP entry is exactly
    # the bytes (and name) a one-photo download would give. Imported here to
    # avoid a views <-> download_jobs import cycle.
    from .views import _resolve_zip_source, _unique_zip_entry_name, _zip_entry_base_name

    try:
        job = DownloadJob.objects.select_related('gallery__photographer', 'photo_set').get(id=job_id)
    except DownloadJob.DoesNotExist:
        return None
    if job.state != DownloadJob.State.PREPARING:
        return job.state

    gallery = job.gallery
    assets = list(job_assets(gallery, job.photo_set, job.asset_ids))
    if not assets:
        _fail(job, 'no_media')
        return job.state
    if size_limit_error(assets):
        _fail(job, 'download_too_large')
        return job.state

    temp_fd, temp_path = tempfile.mkstemp(suffix='.zip')
    os.close(temp_fd)
    stored_name = None
    storage = PrivateMediaStorage()
    try:
        used_names = set()
        added = 0
        with zipfile.ZipFile(temp_path, 'w', compression=zipfile.ZIP_STORED) as archive:
            for asset in assets:
                source_field = _resolve_zip_source(asset, job.resolution)
                if not source_field:
                    continue
                entry_name = _unique_zip_entry_name(
                    _zip_entry_base_name(asset, source_field, job.resolution), used_names
                )
                try:
                    source_field.open('rb')
                    zinfo = zipfile.ZipInfo(filename=entry_name, date_time=time.localtime(time.time())[:6])
                    zinfo.compress_type = zipfile.ZIP_STORED
                    with archive.open(zinfo, 'w', force_zip64=True) as destination:
                        for chunk in source_field.chunks(chunk_size=1024 * 1024):
                            destination.write(chunk)
                    added += 1
                except Exception:
                    logger.exception('Failed to add asset %s to download job %s', asset.id, job.id)
                    used_names.discard(entry_name.lower())
                finally:
                    source_field.close()

        if not added:
            _fail(job, 'no_media')
            return job.state

        name = archive_filename(gallery)
        with open(temp_path, 'rb') as handle:
            stored_name = storage.save(f'{STORAGE_PREFIX}/{job.id}/{name}', File(handle))

        job.files = [{
            'name': name, 'size_bytes': os.path.getsize(temp_path), 'storage_path': stored_name,
            'photo_count': added,
        }]
        job.state = DownloadJob.State.READY
        job.error_code = ''
        job.expires_at = timezone.now() + timedelta(seconds=settings.DOWNLOAD_JOB_TTL_SECONDS)
        job.save(update_fields=['files', 'state', 'error_code', 'expires_at', 'updated_at'])
    except Exception:
        logger.exception('Download job %s failed', job.id)
        if stored_name:
            _delete_stored(storage, stored_name)
        _fail(job, 'prepare_failed')
        return job.state
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

    send_ready_email(job)
    return job.state


def send_ready_email(job):
    """
    "Your photos are ready" mail to the visitor who asked for the download,
    with a link back to the standalone download page (which re-verifies them
    and resumes this job). Only when an email was captured; a mail problem
    never affects the job.
    """
    if not job.email:
        return False
    gallery = job.gallery
    link = (
        f'{settings.FRONTEND_URL}/g/{gallery.photographer.username}/{gallery.slug}/download?job={job.id}'
    )
    try:
        send_mail(
            subject=f'Your photos from "{gallery.title}" are ready',
            message=(
                f'The download you requested from "{gallery.title}" is ready.\n\n'
                f'Open this link to download it: {link}\n\n'
                f'The files stay available for a limited time.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[job.email],
            fail_silently=True,
        )
        return True
    except Exception:
        logger.exception('Could not send the download-ready email for job %s', job.id)
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
