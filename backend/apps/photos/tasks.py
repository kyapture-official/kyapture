# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/tasks.py
from celery import shared_task
import logging
# Defer imports to task execution time to completely bypass circular imports
from apps.photos.models import MediaAsset
from apps.core.utils import process_image_pipeline, process_download_master

logger = logging.getLogger(__name__)


def _auto_assign_cover_if_missing(asset):
    """
    Locked product decision (Phase 1, item 6): the gallery's cover is
    auto-assigned from the first successful (READY) photo/video upload
    when the gallery doesn't have one yet.

    Implemented as a single conditional UPDATE — not a
    select-then-save — specifically so it's race-safe when several
    assets in the same batch finish processing concurrently: Django
    translates .filter(cover_photo__isnull=True).update(...) into one
    atomic 'UPDATE ... WHERE cover_photo_id IS NULL' at the database
    level, so only the first asset to reach this line for a given
    gallery can ever win, with no read-modify-write gap for a second
    worker to race into.
    """
    from apps.galleries.models import Gallery
    try:
        Gallery.objects.filter(
            pk=asset.gallery_id, cover_photo__isnull=True
        ).update(cover_photo_id=asset.id)
    except Exception:
        # Cover assignment is a nice-to-have side effect of processing —
        # never let it fail (or retry) the processing task itself.
        logger.exception(
            f"[Task] Auto-cover-assign failed for asset {asset.id}, gallery {asset.gallery_id}."
        )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_photo_asset(self, asset_id):
    """
    Asynchronously processes uploaded high-res photographs in the background.

    Generates the 640/1280/2048 WebP derivative set (thumbnail, medium,
    display) and computes the BlurHash string.

    Tries up to 3 times with a 60-second delay on transient errors. On final
    failure, transitions status to FAILED, preserving the original file so 
    clients can still download the asset.
    """
    

    asset = None
    try:
        # 1. Retrieve the target asset scoped strictly to image types
        asset = MediaAsset.objects.select_related('gallery__photographer').get(
            id=asset_id,
            media_type=MediaAsset.MediaType.IMAGE
        )

        # 2. Guard: Skip processing if already ready (prevents redundant retries)
        if asset.processing_status == MediaAsset.ProcessingStatus.READY:
            logger.info(f"[Task] Photo {asset_id} is already processed. Skipping.")
            # Assets created before the download-master field existed remain
            # READY and must not have their working web tiers regenerated.
            # Backfill just this missing private derivative instead.
            if not asset.download_file and asset.original_file:
                try:
                    asset.download_file = process_download_master(asset.original_file)
                    if asset.download_file:
                        asset.save(update_fields=['download_file'])
                except Exception:
                    logger.exception("[Task] Download-master backfill failed for photo %s", asset_id)
            # An eager/local retry, an import recovery, or a task replay can
            # encounter an already-READY asset from a gallery that still has
            # no cover. The processing work must remain a no-op, but the
            # idempotent conditional update below is still safe and restores
            # the gallery-level invariant without replacing a manual cover.
            _auto_assign_cover_if_missing(asset)
            return

        # 3. Transition state to 'processing'
        asset.processing_status = MediaAsset.ProcessingStatus.PROCESSING
        asset.save(update_fields=['processing_status'])

        logger.info(f"[Task] Starting single-pass image processing for asset {asset_id}...")

        # 4. Run your optimized, single-pass in-memory WebP and BlurHash generators
        watermark_text = None
        if asset.gallery.watermark_enabled:
            photographer = asset.gallery.photographer
            watermark_text = f"© {photographer.display_name or photographer.username}"

        display_file, medium_file, thumbnail_file, download_file, blurhash_str = process_image_pipeline(
            asset.original_file, watermark_text=watermark_text
        )

        # 5. Populate the processed tiers and transition status to 'ready'
        asset.display_file = display_file
        asset.medium_file = medium_file
        asset.thumbnail_file = thumbnail_file
        asset.download_file = download_file
        asset.blurhash = blurhash_str
        asset.processing_status = MediaAsset.ProcessingStatus.READY
        
        # Save only the modified columns to prevent overwriting other concurrent table updates
        asset.save(update_fields=[
            'display_file', 
            'medium_file',
            'thumbnail_file', 
            'download_file',
            'blurhash', 
            'processing_status'
        ])

        logger.info(f"[Task] Successfully transcoded Photo {asset_id} to WebP Display/Medium/Thumbnail and BlurHash.")

        _auto_assign_cover_if_missing(asset)

    except MediaAsset.DoesNotExist:
        logger.warning(f"[Task] MediaAsset {asset_id} not found in database. Aborting task.")
        return

    except Exception as exc:
        logger.error(f"[Task] Image processing failed for Asset {asset_id}: {str(exc)}")
        if asset is not None:
            asset.processing_status = MediaAsset.ProcessingStatus.FAILED
            asset.save(update_fields=['processing_status'])
            
        # Retry task if retry thresholds have not been exceeded
        raise self.retry(exc=exc)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_video_asset(self, asset_id):
    """
    Asynchronously processes uploaded high-res video assets in the background.

    Spools the original file to a temporary location in bounded chunks,
    extracts duration metrics, captures a poster frame image, and
    transcodes one browser-compatible H.264/AAC MP4 playback derivative
    (faststart, scaled down to a 1080p-max height).

    Wrapped in exception shields and automatic retries to guarantee state-machine
    integrity across transient system bottlenecks.
    """
    # Defer imports to task execution time to completely bypass circular imports
    from apps.photos.models import MediaAsset
    from apps.core.utils import process_video_pipeline

    asset = None
    try:
        # 1. Retrieve the target asset scoped strictly to video types
        asset = MediaAsset.objects.get(
            id=asset_id,
            media_type=MediaAsset.MediaType.VIDEO
        )

        # 2. Guard: Skip processing if already ready (prevents duplicate triggers)
        if asset.processing_status == MediaAsset.ProcessingStatus.READY:
            logger.info(f"[Task] Video {asset_id} is already processed. Skipping.")
            _auto_assign_cover_if_missing(asset)
            return

        # 3. Transition state to 'processing'
        asset.processing_status = MediaAsset.ProcessingStatus.PROCESSING
        asset.save(update_fields=['processing_status'])

        logger.info(f"[Task] Initiating FFmpeg subprocess pipeline for video asset {asset_id}...")

        # 4. Execute the secure FFmpeg and FFprobe subprocess transcoding pipeline
        poster_file, playback_file, duration = process_video_pipeline(asset.original_file)

        # 5. Populate the processed video fields and transition status to 'ready'
        asset.poster_image = poster_file
        asset.playback_file = playback_file
        asset.duration = duration
        asset.processing_status = MediaAsset.ProcessingStatus.READY
        
        # Save only the modified columns to prevent database overwrite collisions
        asset.save(update_fields=[
            'poster_image', 
            'playback_file', 
            'duration', 
            'processing_status'
        ])

        logger.info(f"[Task] Successfully transcoded Video {asset_id}: poster + H.264/AAC MP4 playback derivative.")

        _auto_assign_cover_if_missing(asset)

    except MediaAsset.DoesNotExist:
        logger.warning(f"[Task] MediaAsset {asset_id} not found in database. Aborting task.")
        return

    except Exception as exc:
        logger.error(f"[Task] Video processing failed for Asset {asset_id}: {str(exc)}")
        if asset is not None:
            asset.processing_status = MediaAsset.ProcessingStatus.FAILED
            asset.save(update_fields=['processing_status'])
            
        # Retry task if retry thresholds have not been exceeded
        raise self.retry(exc=exc)
