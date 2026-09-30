# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/models.py
import os
from decimal import Decimal
from django.db import models
from apps.core.models import BaseModel
from apps.core.storage import PrivateMediaStorage, PublicMediaStorage


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
    """Generates paths for 2048px WebP full-screen/lightbox display images (null for videos)."""
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/photos/{instance.id}_display.webp"


def get_medium_photo_path(instance, filename):
    """
    Generates paths for 1280px WebP mid-size images — the middle rung of
    the 640/1280/2048 srcset (grid columns at typical desktop/tablet
    widths land here; avoids forcing a phone-sized 640px view or a
    full 2048px lightbox load for an ordinary in-page gallery view).
    """
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/photos/{instance.id}_medium.webp"


def get_thumbnail_photo_path(instance, filename):
    """Generates paths for 640px WebP grid thumbnails (null for videos)."""
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/thumbnails/{instance.id}_thumb.webp"


def get_video_poster_path(instance, filename):
    """
    Generates paths for frame-captured video poster thumbnails (null for
    images). Extension is .jpg because that's what the pipeline actually
    produces (FFmpeg -f image2 JPEG bytes) — a prior .webp extension here
    caused storage backends that infer Content-Type from the key
    extension (S3 via django-storages) to serve real JPEG bytes labeled
    image/webp, which browsers can fail to render (F-25b).
    """
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/videos/{instance.id}_poster.jpg"


def get_video_preview_path(instance, filename):
    """
    Generates paths for the (legacy, no longer generated) looping hover
    preview clip. Kept only so any already-processed rows with a
    preview_file keep resolving; process_video_asset no longer creates
    new ones — confirmed unused by any frontend UI (nothing reads
    preview_url), so generating it was pure wasted processing/storage.
    """
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/videos/{instance.id}_preview.webm"


def get_video_playback_path(instance, filename):
    """
    Generates paths for the browser-compatible H.264/AAC MP4 playback
    derivative — what PublicVideoStreamView actually serves for inline
    viewing, so an original MOV/HEVC/variable-codec upload always has a
    guaranteed-playable derivative regardless of the source codec.
    """
    photographer_id = instance.gallery.photographer.id
    gallery_id = instance.gallery.id
    return f"photographers/{photographer_id}/galleries/{gallery_id}/videos/{instance.id}_playback.mp4"


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
    # PrivateMediaStorage: private ACL + signed, expiring URLs. Never
    # served directly — always reached through an authorization-gated
    # download endpoint (PublicPhotoDownloadView, the ZIP endpoint, or the
    # dashboard's own tenant-scoped views).
    original_file = models.FileField(
        upload_to=get_original_asset_path, max_length=500, storage=PrivateMediaStorage()
    )

    # ─── Image Specific Fields ───
    # All derivatives use PublicMediaStorage: public-read, unsigned,
    # immutable-cacheable, overwrite-on-retry. See apps/core/storage.py.
    display_file = models.ImageField(
        upload_to=get_display_photo_path, max_length=500, null=True, blank=True, storage=PublicMediaStorage()
    )
    medium_file = models.ImageField(
        upload_to=get_medium_photo_path, max_length=500, null=True, blank=True, storage=PublicMediaStorage()
    )
    thumbnail_file = models.ImageField(
        upload_to=get_thumbnail_photo_path, max_length=500, null=True, blank=True, storage=PublicMediaStorage()
    )
    blurhash = models.CharField(max_length=100, blank=True, null=True)
    width = models.PositiveIntegerField(null=True, blank=True)   
    height = models.PositiveIntegerField(null=True, blank=True)  

    # ─── Video Specific Fields ───
    stream_url = models.URLField(max_length=500, blank=True, null=True)  
    poster_image = models.ImageField(
        upload_to=get_video_poster_path, max_length=500, null=True, blank=True, storage=PublicMediaStorage()
    )
    preview_file = models.FileField(
        upload_to=get_video_preview_path, max_length=500, null=True, blank=True, storage=PublicMediaStorage()
    )
    # Browser-compatible H.264/AAC MP4 derivative — see get_video_playback_path().
    playback_file = models.FileField(
        upload_to=get_video_playback_path, max_length=500, null=True, blank=True, storage=PublicMediaStorage()
    )
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