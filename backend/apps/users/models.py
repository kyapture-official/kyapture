# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/models.py
import os
import uuid
import uuid6
from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.core.models import BaseModel
from apps.core.storage import PublicMediaStorage
from .managers import CustomUserManager
from django.core.validators import RegexValidator

# Mirrors apps/galleries/models.py's hex_color_validator. Duplicated rather than
# imported to avoid a cross-app import at model-load time (galleries only
# references users via settings.AUTH_USER_MODEL, never the reverse — keep it that way).
hex_color_validator = RegexValidator(
    regex=r'^#[0-9a-fA-F]{6}$',
    message='Color must be a valid 6-character HEX code (e.g., #FFFFFF).'
)


def get_profile_avatar_path(instance, filename):
    """
    The avatar is shown on the public portfolio page, so like the branding
    logo it lives in PublicMediaStorage under a unique key per upload (a
    fixed key would be stuck behind the year-long immutable cache header).
    """
    ext = os.path.splitext(filename)[1].lower() or '.png'
    return f"photographers/{instance.id}/profile/avatar_{uuid.uuid4().hex[:12]}{ext}"


def get_branding_logo_path(instance, filename):
    """
    Branding logos are client-visible by design, so they live in
    PublicMediaStorage like the other client-visible derivatives (stable,
    non-expiring URL; never the presigned/expiring default storage).

    Unlike a derivative, a logo's key is UNIQUE PER UPLOAD: public media is
    served with a one-year `immutable` cache header, so overwriting one fixed
    key on "replace logo" would leave browsers/CDNs showing the old logo. A
    fresh key makes replacement visible immediately; the previous file is
    deleted by UserProfileSerializer.update().
    """
    ext = os.path.splitext(filename)[1].lower() or '.png'
    return f"photographers/{instance.id}/branding/logo_{uuid.uuid4().hex[:12]}{ext}"


class User(AbstractUser):
    """
    Custom user model for Kaypture.
    Extends AbstractUser to keep Django's built-in group, permission,
    and administrative flag structures, but overrides key fields
    to enforce UUID primary keys and email-based authentication.
    """
    
    # Overriding the default ID field to use secure, fast-indexing UUIDv7
    id = models.UUIDField(
        primary_key=True,
        default=uuid6.uuid7,
        editable=False
    )
    
    # Core Authentication and Registration fields
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True)
    
    # Photographer Profile Branding & Customization
    display_name = models.CharField(max_length=100, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(
        upload_to=get_profile_avatar_path,
        storage=PublicMediaStorage(),
        null=True,
        blank=True
    )
    # NEW: Optional photographer metadata fields
    phone = models.CharField(
        max_length=20, 
        blank=True, 
        default='',
        help_text="Optional contact phone number."
    )
    website = models.URLField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Optional professional portfolio website URL."
    )
    
    is_active_plan = models.BooleanField(default=False)

    # Automatically audit when a photographer registers or updates their profile
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Configuration to make email the primary login field
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    # Attaching our custom scale-ready manager
    objects = CustomUserManager()


    logo = models.ImageField(
        upload_to=get_branding_logo_path,
        storage=PublicMediaStorage(),
        null=True,
        blank=True,
        help_text="Business logo shown on this photographer's public gallery pages."
    )
    branding_color = models.CharField(
        max_length=7,
        default='#111827',
        validators=[hex_color_validator],
        help_text="Default brand accent color, pre-filled when creating new galleries."
    )

    # ── Settings: notification preferences ─────────────────────────────────
    # Each flag gates an email that is actually sent (see
    # apps/users/notifications.py) — there is no preference without a
    # matching send path. Payment notices are transactional about the user's
    # own billing, so they default on; activity alerts are opt-in.
    notify_downloads = models.BooleanField(default=False)
    notify_favorites = models.BooleanField(default=False)
    notify_payments = models.BooleanField(default=True)

    # ── Settings: privacy ──────────────────────────────────────────────────
    # Whether /g/<username>/ (the public portfolio listing) exists. Individual
    # gallery links are unaffected — they are governed by each gallery's own
    # publish/password settings.
    portfolio_public = models.BooleanField(default=True)

    # ── Settings: Collection Defaults ──────────────────────────────────────
    # Starting values for NEW collections only (see
    # apps/users/collection_defaults.py for the schema and how it is applied).
    # Never read when an existing gallery is edited or displayed.
    collection_defaults = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email


class Notification(BaseModel):
    """
    A short, recent event for the photographer's dashboard bell.

    This is NOT the system of record for anything. The durable, inspectable
    history lives where it always has (DownloadLog, Favorite, ManualPayment,
    MediaAsset status ...); a Notification is a pointer to "something happened
    worth a glance", created as a side effect of that event and safe to delete
    (read ones are pruned by a scheduled task) without losing any history.

    Repeated events of the same kind for the same gallery coalesce into one
    unread row with a `count` (see apps/users/notification_service.py), so a
    client downloading 200 photos is one bell entry, not 200.
    """

    class Kind(models.TextChoices):
        DOWNLOAD = 'download', 'Download'
        FAVORITE = 'favorite', 'Favorite'
        PAYMENT = 'payment', 'Payment'
        PUBLISHED = 'published', 'Gallery published'
        PROCESSING_DONE = 'processing_done', 'Processing complete'
        PROCESSING_FAILED = 'processing_failed', 'Processing failed'

    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # Null for account-level events (payments). The destination link is derived
    # from kind + this gallery when serialized, never stored.
    gallery = models.ForeignKey(
        'galleries.Gallery', null=True, blank=True, on_delete=models.CASCADE, related_name='notifications'
    )
    message = models.CharField(max_length=300)
    count = models.PositiveIntegerField(default=1)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-updated_at']
        indexes = [
            # The bell's two hot queries: "unread count" and "newest first".
            models.Index(fields=['user', 'is_read', '-updated_at'], name='idx_notif_user_read_updated'),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} for {self.user_id}: {self.message}'
