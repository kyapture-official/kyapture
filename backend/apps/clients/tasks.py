# backend/apps/clients/tasks.py
import logging
from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(acks_late=True, soft_time_limit=90, time_limit=120)
def generate_web_size(asset_id, px, expected_state=''):
    """
    Encodes (and caches) one photo's exact-px Web Size -- see apps/clients/web_size.py.
    Routed to its own queue (settings.CELERY_TASK_ROUTES) so the worker's
    --concurrency is the CPU bound for this work. Returns the cache key, or None
    when the photo cannot be decoded. Idempotent: an already cached size is a no-op.
    """
    from apps.photos.models import MediaAsset
    from apps.core.watermark import build_watermark_spec

    from .web_size import WEB_PX_CHOICES, build_cached, watermark_state

    if px not in WEB_PX_CHOICES:
        return None
    try:
        asset = MediaAsset.objects.select_related('gallery__photographer').get(id=asset_id)
    except MediaAsset.DoesNotExist:
        return None
    spec = build_watermark_spec(asset.gallery)
    if watermark_state(spec) != expected_state:
        logger.info('Web Size for asset %s: watermark changed since the request; encoding the current state', asset_id)
    return build_cached(asset, px, spec)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def purge_expired_client_sessions(self):
    """
    Periodic Celery Beat task — see config/celery.py's beat_schedule.

    Phase 4 (auth hardening) — ClientSession rows previously never
    expired and never got cleaned up: a gallery-unlock session lived
    forever unless the photographer explicitly rotated the gallery
    password (GallerySetPasswordView revokes all sessions on change).
    ClientSessionQuerySet.not_expired() (apps/clients/models.py) now
    enforces CLIENT_SESSION_TTL_DAYS at every validation call site, so
    an expired session already can't authorize anything — this task just
    removes the now-useless rows so the table doesn't grow forever.

    Deleting an expired ClientSession never breaks "unlocked gallery
    browsing" for anyone still active: a client with a live, non-expired
    session is untouched by this filter (created_at__lt=cutoff only
    matches sessions ALREADY past the same TTL the validation gate
    already enforces), and a client whose session just expired needs to
    re-enter the gallery password again regardless of whether this task
    has run yet — that's the TTL doing its job, not a bug this task could
    introduce.
    """
    from .models import ClientSession

    cutoff = timezone.now() - timezone.timedelta(days=settings.CLIENT_SESSION_TTL_DAYS)

    try:
        deleted_count, _ = ClientSession.objects.filter(created_at__lt=cutoff).delete()
    except Exception as exc:
        logger.error(f"[purge_expired_client_sessions] Sweep failed: {exc}")
        raise self.retry(exc=exc)

    if deleted_count:
        logger.info(f"[purge_expired_client_sessions] Purged {deleted_count} expired session(s).")
    else:
        logger.info("[purge_expired_client_sessions] No expired sessions found.")
    return deleted_count


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def purge_old_download_logs(self):
    """
    Periodic Celery Beat task — see config/celery.py's beat_schedule.

    Phase 4 (DB cleanup) — purely operational retention trim for
    DownloadLog, which has no natural cap and no relationship to any
    active security control (unlike ClientSession above). Deleting an
    old log row never affects a currently-in-progress or future
    download — DownloadLog is write-only from the download views'
    perspective; nothing reads it back except the photographer-facing
    activity endpoint and quota calculations, neither of which depend on
    rows older than DOWNLOAD_LOG_RETENTION_DAYS.
    """
    from .models import DownloadLog

    cutoff = timezone.now() - timezone.timedelta(days=settings.DOWNLOAD_LOG_RETENTION_DAYS)

    try:
        deleted_count, _ = DownloadLog.objects.filter(created_at__lt=cutoff).delete()
    except Exception as exc:
        logger.error(f"[purge_old_download_logs] Sweep failed: {exc}")
        raise self.retry(exc=exc)

    if deleted_count:
        logger.info(f"[purge_old_download_logs] Purged {deleted_count} old download log(s).")
    else:
        logger.info("[purge_old_download_logs] No old download logs found.")
    return deleted_count


@shared_task(bind=True, max_retries=1)
def prepare_download_job(self, job_id):
    """Builds the ZIP for one DownloadJob in the background. See download_jobs.run_download_job."""
    from .download_jobs import run_download_job

    return run_download_job(job_id)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def purge_expired_download_jobs(self):
    """Hourly Beat task: removes expired/abandoned download jobs and their stored ZIPs."""
    from .download_jobs import purge_expired_jobs

    try:
        return purge_expired_jobs()
    except Exception as exc:
        logger.error(f"[purge_expired_download_jobs] Sweep failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=0)
def send_download_ready_email(self, job_id):
    """
    "Your photos are ready" email for one finished DownloadJob (sent at most
    once per job, rate-limited). A mail problem is logged inside and never
    raised: it must not touch the job, whose files are already ready.
    """
    from .ready_email import deliver_ready_email

    return deliver_ready_email(job_id)
