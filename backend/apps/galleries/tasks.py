# backend/apps/galleries/tasks.py
import logging
from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def purge_trashed_galleries(self):
    """
    Periodic Celery Beat task — see config/celery.py's beat_schedule.

    WHY THIS EXISTS (F-30, the soft-delete storage leak): before this,
    GalleryDetailView.delete() only ever flipped is_active to False —
    nothing anywhere ever hard-deleted a trashed gallery's row or its
    files, so S3/disk usage grew unbounded for every deleted gallery
    forever, at zero counted quota cost (get_user_subscription_metrics
    only counted is_active=True rows before this phase).

    This task finds every gallery that is BOTH trashed (is_active=False)
    AND past its retention window (trashed_at <= now - RETENTION_DAYS),
    and hard-deletes it. `Gallery.delete()` cascades to every related
    row (MediaAsset, PhotoSet, Favorite, DownloadLog, ClientSession — all
    on_delete=CASCADE from Gallery), and MediaAsset's own post_delete
    signal (apps/photos/signals.py) purges each asset's actual S3/disk
    files as part of that cascade — so one Gallery.delete() call here is
    enough to remove the database rows AND the underlying storage
    objects, with no separate S3-cleanup step needed.

    Idempotent / retry-safe: the query itself is idempotent (a gallery
    already purged simply won't match the filter on the next run — no
    "already deleted" error path to handle), each gallery is deleted in
    its own try/except so one bad row can't block the rest of the batch,
    and re-running this task after a partial failure just re-attempts
    whatever's still eligible.

    Safety: a gallery with `trashed_at IS NULL` (never soft-deleted, or
    soft-deleted before this field existed and not yet backfilled — see
    migration 0008) is NEVER eligible here, regardless of is_active —
    this task can only ever remove a gallery that was BOTH explicitly
    trashed AND has an explicit trash timestamp past the window. An
    active gallery is never touched: the query requires is_active=False.
    """
    from apps.photos.purge import purge_gallery
    from .models import Gallery

    cutoff = timezone.now() - timezone.timedelta(days=settings.GALLERY_TRASH_RETENTION_DAYS)

    try:
        eligible_ids = list(
            Gallery.objects
            .filter(is_active=False, trashed_at__isnull=False, trashed_at__lte=cutoff)
            .values_list('id', flat=True)
        )
    except Exception as exc:
        # A failure just finding the candidates (e.g. a transient DB
        # connection drop) is retried wholesale — nothing has been
        # deleted yet, so retrying the whole task is safe.
        logger.error(f"[purge_trashed_galleries] Failed to query eligible galleries: {exc}")
        raise self.retry(exc=exc)

    if not eligible_ids:
        logger.info("[purge_trashed_galleries] No galleries past retention window.")
        return 0

    purged_count = 0
    for gallery_id in eligible_ids:
        try:
            # Re-filter by id + the same safety predicates at delete time
            # (not just re-using the id from the list above) so a gallery
            # that was somehow reactivated between the query and this
            # loop iteration is safely skipped rather than deleted anyway.
            gallery = Gallery.objects.filter(
                id=gallery_id, is_active=False, trashed_at__isnull=False, trashed_at__lte=cutoff,
            ).first()
            if gallery is not None:
                purge_gallery(gallery)      # rows + every stored file, same as an owner delete
                purged_count += 1
        except Exception:
            # One bad row must never abort the batch — log it and let the
            # NEXT scheduled sweep retry this specific gallery, rather
            # than retrying the whole task (which would re-purge everyone
            # already successfully purged in this same run — wasteful,
            # though harmless since a second delete of an already-gone
            # row is just a no-op).
            logger.exception(
                "[purge_trashed_galleries] Failed to purge gallery %s — will retry on next sweep.",
                gallery_id,
            )

    logger.info(f"[purge_trashed_galleries] Purged {purged_count} gallery(ies).")
    return purged_count
