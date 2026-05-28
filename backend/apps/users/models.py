import uuid6
from django.contrib.auth.models import AbstractUser
from django.db import models
from .managers import CustomUserManager


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
    is_active_plan = models.BooleanField(default=False)

    # Automatically audit when a photographer registers or updates their profile
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Configuration to make email the primary login field
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    # Attaching our custom scale-ready manager
    objects = CustomUserManager()

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email