# C:/Users/LENOVO/Desktop/kyapture/backend/apps/galleries/models.py
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from apps.core.models import BaseModel

# Enforces 6-character HEX format (e.g., #FFA500) at the DB and API layer
hex_color_validator = RegexValidator(
    regex=r'^#[0-9a-fA-F]{6}$',
    message='Color must be a valid 6-character HEX code (e.g., #FFFFFF).'
)


class Gallery(BaseModel):
    """
    Manages photo collections/galleries created by photographers.
    Provides settings for password protection, downloads, watermarking,
    and visual customization (branding).
    """
    photographer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='galleries'
    )
    title = models.CharField(max_length=200)
    
    # We remove unique=True from the slug field. 
    # Uniqueness is scoped per-photographer using a UniqueConstraint in Meta.
    slug = models.SlugField(max_length=225)
    description = models.TextField(blank=True, default='')
    
    event_date = models.DateField(null=True, blank=True)
    
    cover_photo = models.ForeignKey(
        'photos.MediaAsset',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='cover_for_gallery'
    )
    
    branding_color = models.CharField(
        max_length=7,
        default='#000000',
        validators=[hex_color_validator]
    )

    # Locked product decision: Design is a real MVP feature (cover layout,
    # typography, color palette, grid style/spacing, selected cover photo id).
    # Kept intentionally simple — a JSON blob of a small fixed set of choices,
    # not a theme builder. See docs/KYAPTURE_PRODUCT_DECISIONS.md #6.
    design_settings = models.JSONField(default=dict, blank=True)

    # Access Control Settings
    is_password_protected = models.BooleanField(default=False)
    password_hash = models.CharField(max_length=255, null=True, blank=True)

    # Phase 3: optional SECOND gate, independent of the gallery password
    # above — a photographer can leave a gallery open (no password) but
    # still require a PIN before a client can trigger an actual download
    # (ZIP or single-file). Presence of a hash IS the "protected" flag;
    # no separate boolean, mirroring how has_password is derived from
    # password_hash elsewhere (GalleryListSerializer.get_has_password).
    # Never stores the plaintext PIN — bcrypt hash only, same as the
    # gallery password above.
    download_pin_hash = models.CharField(max_length=255, null=True, blank=True)

    # Performance & Download Toggles
    allow_download = models.BooleanField(default=False)
    watermark_enabled = models.BooleanField(default=False)

    # Deployment Status
    is_published = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Phase 4 — trash/purge lifecycle (fixes the soft-delete storage leak,
    # F-30: a soft-deleted gallery previously stayed invisible AND
    # zero-cost forever — no purge task existed anywhere, so a user could
    # delete+reupload indefinitely at no counted storage/gallery-count
    # cost). `is_active=False` still means "trashed, hidden from normal
    # use" exactly as before; `trashed_at` records WHEN, so a scheduled
    # purge task (apps/galleries/tasks.py::purge_trashed_galleries) can
    # hard-delete anything past the retention window
    # (settings.GALLERY_TRASH_RETENTION_DAYS). Until purged, the gallery
    # and its storage still count toward the owner's quota
    # (get_user_subscription_metrics no longer filters by is_active) —
    # that's the actual fix for the leak: deleting no longer frees quota
    # until the data is actually gone.
    trashed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'galleries'
        ordering = ['-created_at']
        
        constraints = [
            # Guarantees a photographer cannot have two galleries with the same slug.
            # Scopes uniqueness specifically to each tenant (photographer) [1.2.7].
            models.UniqueConstraint(
                fields=['photographer', 'slug'],
                name='unique_photographer_gallery_slug'
            )
        ]
        
        indexes = [
            # High-performance compound index for public portfolio queries
            # (e.g., fetching a photographer's active public collections) [1.1.2]
            models.Index(
                fields=['photographer', 'is_published'],
                name='idx_photog_published'
            ),
            # Covers the scheduled purge task's "find everything past its
            # retention window" sweep (is_active=False AND trashed_at <=
            # cutoff) without a full table scan.
            models.Index(
                fields=['is_active', 'trashed_at'],
                name='idx_gallery_trash_purge'
            ),
        ]

    def __str__(self):
        return f"{self.photographer.username} / {self.title}"