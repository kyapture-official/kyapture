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