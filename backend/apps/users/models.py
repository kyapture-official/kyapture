# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/models.py
import uuid6
from django.contrib.auth.models import AbstractUser
from django.db import models
from .managers import CustomUserManager
from django.core.validators import RegexValidator

# Mirrors apps/galleries/models.py's hex_color_validator. Duplicated rather than
# imported to avoid a cross-app import at model-load time (galleries only
# references users via settings.AUTH_USER_MODEL, never the reverse — keep it that way).
hex_color_validator = RegexValidator(
    regex=r'^#[0-9a-fA-F]{6}$',
    message='Color must be a valid 6-character HEX code (e.g., #FFFFFF).'
)


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
        upload_to='avatars/', 
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
        upload_to='photographer_logos/',
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

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email