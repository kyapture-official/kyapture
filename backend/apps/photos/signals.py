# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/signals.py
import logging
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from apps.galleries.models import Gallery
from .models import MediaAsset, PhotoSet
from .purge import queue_asset_files

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
def purge_media_asset_files_on_delete(sender, instance, **kwargs):
    """
    Safety net for EVERY way a MediaAsset row can disappear (explicit delete,
    bulk delete, set/collection cascade, admin, account deletion): the files it
    owned - original, Download Master, display/medium/thumbnail (watermarked)
    derivatives, video poster/preview/playback - are queued for the idempotent
    purge task AFTER the transaction commits (apps/photos/purge.py). Nothing is
    deleted from storage here, so a rolled-back delete never loses a file.
    """
    queue_asset_files(instance)
