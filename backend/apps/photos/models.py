import os
import uuid
from django.db import models
from apps.core.models import BaseModel


def get_photo_upload_path(instance, filename):
    """
    Generates a secure, standardized, and isolated path for high-res photo uploads.
    Format: photographers/{photographer_id}/galleries/{gallery_id}/photos/{uuid}.{ext}
    """
    ext = os.path.splitext(filename)[1].lower()
    photo_uuid = instance.id if instance.id else uuid.uuid4()
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/photos/{photo_uuid}{ext}"


def get_thumbnail_upload_path(instance, filename):
    """
    Generates a secure, isolated path for compressed client-facing thumbnails.
    Format: photographers/{photographer_id}/galleries/{gallery_id}/thumbnails/{uuid}_thumb.{ext}
    """
    ext = os.path.splitext(filename)[1].lower()
    photo_uuid = instance.id if instance.id else uuid.uuid4()
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/thumbnails/{photo_uuid}_thumb{ext}"


class Photo(BaseModel):
    """
    Stores metadata and file path configurations for individual photographs.
    Utilizes secure, randomized paths for cloud bucket (S3) multi-tenancy.
    """
    # String reference completely prevents circular dependency imports
    gallery = models.ForeignKey(
        'galleries.Gallery',
        on_delete=models.CASCADE,
        related_name='photos'
    )
    
    # Files are routed dynamically to standardized folders
    image = models.ImageField(upload_to=get_photo_upload_path)
    thumbnail = models.ImageField(
        upload_to=get_thumbnail_upload_path,
        null=True,
        blank=True
    )
    
    # Optional metadata title vs. immutable system metadata
    title = models.CharField(max_length=200, blank=True)
    original_name = models.CharField(max_length=255)
    
    # Essential specifications for billing and frontend UI rendering
    file_size = models.PositiveIntegerField()  # Stored in bytes (used to calculate storage limits)
    width = models.PositiveIntegerField()     # Stored in pixels (required to render masonry grid safely)
    height = models.PositiveIntegerField()    # Stored in pixels (required to render masonry grid safely)
    
    # User-defined drag-and-drop display order index
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'photos'
        ordering = ['order', 'created_at']
        
        indexes = [
            # High-performance compound index for gallery loads and display sorting [1.1.2]
            models.Index(
                fields=['gallery', 'order'],
                name='idx_gallery_photos_order'
            ),
            # Index for analytics/cleanups sorted by date
            models.Index(
                fields=['created_at'],
                name='idx_photos_created_at'
            ),
        ]

    def __str__(self):
        return f"{self.gallery.title} — {self.original_name}"