import secrets
from django.db import models
from apps.core.models import BaseModel


def generate_secure_token():
    """
    Generates a cryptographically secure, unguessable 64-character hex token.
    Uses Python's native CSPRNG secrets module. 32 bytes of entropy = 64 characters [1.1.2].
    """
    return secrets.token_hex(32)


class ClientSession(BaseModel):
    """
    Tracks anonymous client gallery access authorization.
    When a public client unlocks a password-protected gallery,
    this record stores their authorization token, eliminating the need
    for a standard registration/user account.
    """
    # String relationship target completely prevents circular dependency loops
    gallery = models.ForeignKey(
        'galleries.Gallery',
        on_delete=models.CASCADE,
        related_name='client_sessions'
    )
    
    email = models.EmailField(
        null=True, 
        blank=True,
        help_text="Optional email provided by client for download tracking or newsletter leads."
    )
    
    # Secure, auto-generated token. Mark editable=False to protect DB-level state.
    access_token = models.CharField(
        max_length=64, 
        unique=True,
        default=generate_secure_token,
        editable=False
    )
    
    ip_address = models.GenericIPAddressField(
        null=True, 
        blank=True,
        help_text="Auditable IP address of the client device."
    )
    
    has_download_access = models.BooleanField(
        default=False,
        help_text="Tracks whether this specific client session is permitted to trigger gallery downloads."
    )

    class Meta:
        db_table = 'client_sessions'
        ordering = ['-created_at']
        indexes = [
            # Compound index optimizing token lookups and stale session cleanup tasks [1.1.2]
            models.Index(
                fields=['access_token', 'created_at'], 
                name='idx_client_token_lookup'
            )
        ]

    def __str__(self):
        # Prevent string-null parsing issues when email is empty
        client_identifier = self.email if self.email else "Anonymous"
        return f"Session: {self.gallery.title} — {client_identifier}"