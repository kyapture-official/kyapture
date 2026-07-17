from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_photo_asset(self, asset_id):
    """
    Asynchronously processes uploaded high-res photographs in the background.
    
    Generates WebP display variants (2048px), WebP thumbnails (600px), 
    and computes the BlurHash string.
    
    Tries up to 3 times with a 60-second delay on transient errors. On final
    failure, transitions status to FAILED, preserving the original file so 
    clients can still download the asset.
    """
    # Defer imports to task execution time to completely bypass circular imports
    from apps.photos.models import MediaAsset
    from apps.core.utils import process_image_pipeline

    asset = None
    try:
        # 1. Retrieve the target asset scoped strictly to image types
        asset = MediaAsset.objects.get(
            id=asset_id,
            media_type=MediaAsset.MediaType.IMAGE
        )

        # 2. Guard: Skip processing if already ready (prevents redundant retries)
        if asset.processing_status == MediaAsset.ProcessingStatus.READY:
            logger.info(f"[Task] Photo {asset_id} is already processed. Skipping.")
            return

        # 3. Transition state to 'processing'
        asset.processing_status = MediaAsset.ProcessingStatus.PROCESSING
        asset.save(update_fields=['processing_status'])

        logger.info(f"[Task] Starting single-pass image processing for asset {asset_id}...")

        # 4. Run your optimized, single-pass in-memory WebP and BlurHash generators
        display_file, thumbnail_file, blurhash_str = process_image_pipeline(asset.original_file)

        # 5. Populate the processed tiers and transition status to 'ready'
        asset.display_file = display_file
        asset.thumbnail_file = thumbnail_file
        asset.blurhash = blurhash_str
        asset.processing_status = MediaAsset.ProcessingStatus.READY
        
        # Save only the modified columns to prevent overwriting other concurrent table updates
        asset.save(update_fields=[
            'display_file', 
            'thumbnail_file', 
            'blurhash', 
            'processing_status'
        ])

        logger.info(f"[Task] Successfully transcoded Photo {asset_id} to WebP Display, Thumbnail, and BlurHash.")

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
    
    Spools the original file to a temporary location, extracts duration metrics,
    captures a poster frame image, and transcodes a short, silent looping 
    WebM preview clip.
    
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
            return

        # 3. Transition state to 'processing'
        asset.processing_status = MediaAsset.ProcessingStatus.PROCESSING
        asset.save(update_fields=['processing_status'])

        logger.info(f"[Task] Initiating FFmpeg subprocess pipeline for video asset {asset_id}...")

        # 4. Execute the secure FFmpeg and FFprobe subprocess transcoding pipeline
        poster_file, preview_file, duration = process_video_pipeline(asset.original_file)

        # 5. Populate the processed video fields and transition status to 'ready'
        asset.poster_image = poster_file
        asset.preview_file = preview_file
        asset.duration = duration
        asset.processing_status = MediaAsset.ProcessingStatus.READY
        
        # Save only the modified columns to prevent database overwrite collisions
        asset.save(update_fields=[
            'poster_image', 
            'preview_file', 
            'duration', 
            'processing_status'
        ])

        logger.info(f"[Task] Successfully transcoded Video {asset_id} and extracted poster frame.")

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