# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/signals.py
import logging
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from apps.galleries.models import Gallery
from .models import MediaAsset, PhotoSet

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Gallery)
def create_highlights_set_for_new_gallery(sender, instance, created, **kwargs):
    """Every newly-created gallery starts with its required default set."""
    if created:
        PhotoSet.objects.get_or_create(
            gallery=instance,
            name='Highlights',
            defaults={'order': 1},
        )


@receiver(post_delete, sender=MediaAsset)
def auto_delete_media_asset_files_on_db_delete(sender, instance, **kwargs):
    """
    Automatically purges all physical files, transcoded display images, thumbnails,
    poster frames, and looping previews associated with a MediaAsset record when deleted.
    
    Wrapped in try-except shields to ensure database purges never fail due to S3 
    network drops or expired storage credentials.
    """
    # 1. Purge Original File (Applies to both Images and Videos)
    if instance.original_file:
        try:
            instance.original_file.delete(save=False)
        except Exception as e:
            logger.error(
                f"Failed to delete original_file for MediaAsset {instance.id} on S3/Disk: {str(e)}"
            )

    # 2. Purge Display File (Images only)
    if instance.display_file:
        try:
            instance.display_file.delete(save=False)
        except Exception as e:
            logger.error(
                f"Failed to delete display_file for MediaAsset {instance.id} on S3/Disk: {str(e)}"
            )

    # 3. Purge Thumbnail File (Images only)
    if instance.thumbnail_file:
        try:
            instance.thumbnail_file.delete(save=False)
        except Exception as e:
            logger.error(
                f"Failed to delete thumbnail_file for MediaAsset {instance.id} on S3/Disk: {str(e)}"
            )

    # 3b. Purge Medium (1280px) File (Images only)
    if instance.medium_file:
        try:
            instance.medium_file.delete(save=False)
        except Exception as e:
            logger.error(
                f"Failed to delete medium_file for MediaAsset {instance.id} on S3/Disk: {str(e)}"
            )

    # 4. Purge Video Poster Frame (Videos only)
    if instance.poster_image:
        try:
            instance.poster_image.delete(save=False)
        except Exception as e:
            logger.error(
                f"Failed to delete poster_image for MediaAsset {instance.id} on S3/Disk: {str(e)}"
            )

    # 5. Purge Looping Hover Preview Clip (Videos only — legacy field; no
    #    longer generated for new uploads, but still purged here in case
    #    an older row has one on disk/S3).
    if instance.preview_file:
        try:
            instance.preview_file.delete(save=False)
        except Exception as e:
            logger.error(
                f"Failed to delete preview_file for MediaAsset {instance.id} on S3/Disk: {str(e)}"
            )

    # 5b. Purge H.264/AAC MP4 Playback Derivative (Videos only)
    if instance.playback_file:
        try:
            instance.playback_file.delete(save=False)
        except Exception as e:
            logger.error(
                f"Failed to delete playback_file for MediaAsset {instance.id} on S3/Disk: {str(e)}"
            )

    # 6. Unified HLS Chunk Folder Cleanup Hook (Videos only)
    if instance.media_type == MediaAsset.MediaType.VIDEO:
        # Once the asynchronous transcode infrastructure is running, we will trigger a background 
        # worker task here to recursively purge the HLS S3 directory partition:
        # "photographers/{photog_id}/galleries/{gallery_id}/videos/{video_uuid}/hls/"
        pass
