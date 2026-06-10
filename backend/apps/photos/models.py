import os
from decimal import Decimal
from django.db import models
from apps.core.models import BaseModel


# ─────────────────────────────────────────────────────────────
# DYNAMIC MULTI-TENANT STORAGE PATH GENERATORS
# ─────────────────────────────────────────────────────────────

def get_original_asset_path(instance, filename):
    """
    Generates S3/local paths for original, full-res lossless source files.
    Dynamically routes to 'photos' or 'videos' subdirectories.
    """
    ext = os.path.splitext(filename)[1].lower()
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    
    # Dynamic folder segmentation based on choice field
    folder = "photos" if instance.media_type == MediaAsset.MediaType.IMAGE else "videos"
    return f"photographers/{photographer_id}/galleries/{gallery_id}/{folder}/{instance.id}_original{ext}"


def get_display_photo_path(instance, filename):
    """Generates paths for 2048px WebP full-screen display images (null for videos)."""
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/photos/{instance.id}_display.webp"


def get_thumbnail_photo_path(instance, filename):
    """Generates paths for 600px WebP grid thumbnails (null for videos)."""
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/thumbnails/{instance.id}_thumb.webp"


def get_video_poster_path(instance, filename):
    """Generates paths for frame-captured video poster thumbnails (null for images)."""
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/videos/{instance.id}_poster.webp"


def get_video_preview_path(instance, filename):
    """Generates paths for looping hover silent preview clips (null for images)."""
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/videos/{instance.id}_preview.webm"


# ─────────────────────────────────────────────────────────────
# UNIFIED MEDIA ASSET MODEL (The Production Standard)
# ─────────────────────────────────────────────────────────────

class MediaAsset(BaseModel):
    """
    Unified database table representing both photographs and videography assets.
    Provides bulletproof sequential ordering, clean API serialization, and 
    painless frontend grid calculations.
    """
    class MediaType(models.TextChoices):
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Video'

    # NEW: Processing states for both photos and videos
    class ProcessingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        READY = 'ready', 'Ready'
        FAILED = 'failed', 'Failed'

    gallery = models.ForeignKey(
        'galleries.Gallery',
        on_delete=models.CASCADE,
        related_name='assets'
    )
    
    # ─── Core Discriminator Flag ───
    media_type = models.CharField(
        max_length=10,
        choices=MediaType.choices,
        default=MediaType.IMAGE
    )

    # ─── Shared Common Attributes ───
    title = models.CharField(max_length=200, blank=True)
    original_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()
    
    # NEW: Decimal field replaces PositiveIntegerField to enable O(1) drag-and-drop insertions
    order = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        default=Decimal('1.0')
    )

    # ─── Tier 1: Shared Original Source (Downloads) ───
    original_file = models.FileField(upload_to=get_original_asset_path, max_length=500)

    # ─── Image Specific Fields ───
    display_file = models.ImageField(upload_to=get_display_photo_path, max_length=500, null=True, blank=True)
    thumbnail_file = models.ImageField(upload_to=get_thumbnail_photo_path, max_length=500, null=True, blank=True)
    blurhash = models.CharField(max_length=100, blank=True, null=True)
    width = models.PositiveIntegerField(null=True, blank=True)   
    height = models.PositiveIntegerField(null=True, blank=True)  

    # ─── Video Specific Fields ───
    stream_url = models.URLField(max_length=500, blank=True, null=True)  
    poster_image = models.ImageField(upload_to=get_video_poster_path, max_length=500, null=True, blank=True)
    preview_file = models.FileField(upload_to=get_video_preview_path, max_length=500, null=True, blank=True)
    duration = models.PositiveIntegerField(null=True, blank=True)  
    
    # OLD video_status is now a unified asset processing status
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING
    )

    class Meta:
        db_table = 'media_assets'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['gallery', 'order'], name='idx_gallery_assets_order'),
            models.Index(fields=['gallery', 'media_type'], name='idx_gallery_assets_type'),
            models.Index(fields=['created_at'], name='idx_assets_created_at'),
            # NEW: Index for background worker processing sweeps
            models.Index(fields=['processing_status'], name='idx_assets_proc_status'),
        ]

    def __str__(self):
        return f"{self.get_media_type_display()}: {self.gallery.title} — {self.original_name} [{self.processing_status}]"

    # NEW property helper shortcuts
    @property
    def is_ready(self):
        return self.processing_status == self.ProcessingStatus.READY

    @property
    def is_photo(self):
        return self.media_type == self.MediaType.IMAGE

    @property
    def is_video(self):
        return self.media_type == self.MediaType.VIDEO