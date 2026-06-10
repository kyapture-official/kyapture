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

    # Access Control Settings
    is_password_protected = models.BooleanField(default=False)
    password_hash = models.CharField(max_length=255, null=True, blank=True)

    # Performance & Download Toggles
    allow_download = models.BooleanField(default=False)
    watermark_enabled = models.BooleanField(default=False)

    # Deployment Status
    is_published = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True) 
    expires_at = models.DateTimeField(null=True, blank=True)

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
            )
        ]

    def __str__(self):
        return f"{self.photographer.username} / {self.title}"