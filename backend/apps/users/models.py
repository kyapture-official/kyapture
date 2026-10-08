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

    # ── Session revocation (7-C) ───────────────────────────────────────────
    # Every JWT (access and refresh) carries this number as its `tv` claim.
    # CookieJWTAuthentication and the refresh view refuse a token whose claim is
    # not the current value, so bumping it (apps/users/utils.py
    # revoke_all_sessions: password reset, password change, logout-all) kills
    # every token already issued, cookie or bearer, on the very next request.
    token_version = models.PositiveIntegerField(default=0, editable=False)

    # ── Suspension (7.5-A) ─────────────────────────────────────────────────
    # A suspended account is `is_active=False` (the one switch every login, token
    # and public gallery lookup already reads); these two only record when and
    # why staff did it. Plain text, shown to staff escaped. Cleared on reactivation
    # (the audit log keeps the history). An account deactivated any other way
    # (Django admin) has is_active=False and no `suspended_at`.
    suspended_at = models.DateTimeField(null=True, blank=True, editable=False)
    suspension_reason = models.CharField(max_length=300, blank=True, default='', editable=False)

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
        FEEDBACK = 'feedback', 'New feedback'     # sent to staff (see apps/users/feedback_api.py)
        # A gallery's password or download PIN was locked after too many wrong attempts (apps/clients/lockout.py).
        SECURITY = 'security', 'Security alert'
        # Sent to staff when a user submits a manual payment (apps/subscriptions/payments.py).
        PAYMENT_REVIEW = 'payment_review', 'Payment to review'

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


class Feedback(BaseModel):
    """
    A message a signed-in user sent to the KYAPTURE team (POST /api/v1/feedback/).

    Everything the client sends is untrusted and is cleaned in
    apps/users/feedback_api.py before it lands here. `message` and `subject` are
    stored and returned as plain text and must be rendered escaped by any UI.
    The auto-captured context is limited to `route` (path only, no query or
    fragment), `gallery_slug`, `app_version` and `browser_class`; the last two
    only ever hold allowlisted values. No attachments: a feedback row is text.
    """

    class Category(models.TextChoices):
        BUG = 'bug', 'Bug'
        FEATURE_REQUEST = 'feature_request', 'Feature request'
        DESIGN = 'design', 'Design'
        PERFORMANCE = 'performance', 'Performance'
        DOWNLOAD = 'download', 'Download'
        UPLOAD = 'upload', 'Upload'
        SECURITY_PRIVACY = 'security_privacy', 'Security / privacy'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        NEW = 'new', 'New'
        REVIEWED = 'reviewed', 'Reviewed'
        IN_PROGRESS = 'in_progress', 'In progress'
        RESOLVED = 'resolved', 'Resolved'
        DISMISSED = 'dismissed', 'Dismissed'

    class Browser(models.TextChoices):
        CHROME = 'chrome', 'Chrome'
        EDGE = 'edge', 'Edge'
        FIREFOX = 'firefox', 'Firefox'
        SAFARI = 'safari', 'Safari'
        OPERA = 'opera', 'Opera'
        OTHER = 'other', 'Other'

    SUBJECT_MAX = 120
    MESSAGE_MAX = 4000
    ROUTE_MAX = 200

    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='feedback')
    category = models.CharField(max_length=20, choices=Category.choices)
    subject = models.CharField(max_length=SUBJECT_MAX)
    message = models.TextField()
    route = models.CharField(max_length=ROUTE_MAX, blank=True, default='')
    gallery_slug = models.CharField(max_length=225, blank=True, default='')
    app_version = models.CharField(max_length=32, blank=True, default='')
    browser_class = models.CharField(max_length=10, choices=Browser.choices, default=Browser.OTHER)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)

    class Meta:
        db_table = 'feedback'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='idx_feedback_status_created'),
            models.Index(fields=['user', '-created_at'], name='idx_feedback_user_created'),
        ]

    def __str__(self):
        return f'{self.get_category_display()} from {self.user_id}: {self.subject}'


class PasswordResetToken(models.Model):
    """
    One emailed "forgot password" link (7-C).

    Only the SHA-256 of the random token is stored; the token itself exists in
    the email and, once, in the browser. A row is usable while `expires_at` is
    in the future (settings.PASSWORD_RESET_TOKEN_MINUTES). It is deleted when it
    is used, when a newer link is requested for the same account, and when any
    password change revokes the account's sessions, so a link works at most once
    and only the newest one works.
    """

    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='password_reset_tokens')
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = 'password_reset_tokens'

    def __str__(self):
        return f'Password reset link for {self.user_id} (expires {self.expires_at:%Y-%m-%d %H:%M})'


class AuditLogQuerySet(models.QuerySet):
    """An audit row can be added, never changed or removed through the ORM."""

    def update(self, **kwargs):
        raise AuditLogImmutable('Audit log rows cannot be updated.')

    def delete(self):
        raise AuditLogImmutable('Audit log rows cannot be deleted.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise AuditLogImmutable('Audit log rows cannot be updated.')


class AuditLogImmutable(Exception):
    pass


class StaffAuditLog(models.Model):
    """
    Append-only record of every staff action and every security event (7.5-A).

    One row says: WHO (`actor_*`, empty for the system or an anonymous visitor),
    DID WHAT (`action`), TO WHOM (`target_*`), WHEN (`created_at`), from WHICH
    ADDRESS (`ip`, always `apps.core.request_ip.client_ip`, i.e. the trusted-proxy
    setup of 7-B, never a header the client chose), and `reason`: staff-typed plain
    text for a suspend/reactivate, otherwise a coarse code ("pin", "reset" ...).
    It never holds a password, PIN, code, token, key or hash.

    Users are referenced by plain id plus an email snapshot, not by foreign key:
    deleting an account must neither cascade into nor rewrite its history. The
    ORM refuses UPDATE and DELETE (here and in the manager), the admin shows the
    table read-only, and on PostgreSQL a trigger (migration 0010) refuses them
    in the database itself.
    """

    class Action(models.TextChoices):
        # Staff actions
        USER_LIST = 'staff.user_list', 'Viewed the user list'
        USER_LOOKUP = 'staff.user_lookup', 'Looked up a user by email'
        AUDIT_VIEW = 'staff.audit_view', 'Viewed the audit log'
        SUSPEND = 'account.suspend', 'Suspended an account'
        REACTIVATE = 'account.reactivate', 'Reactivated an account'
        FEEDBACK_STATUS = 'staff.feedback_status', 'Changed a feedback status'
        PAYMENT_REVIEW = 'staff.payment_review', 'Reviewed a manual payment'   # 7.5-A rows; 7.5-B writes the three below
        PAYMENT_APPROVE = 'payment.approve', 'Approved a manual payment'
        PAYMENT_REJECT = 'payment.reject', 'Rejected a manual payment'
        PAYMENT_PROOF_VIEW = 'payment.proof_view', 'Opened a payment proof'
        INBOX_VIEW = 'staff.inbox_view', 'Viewed a staff queue'
        # Security events
        LOGIN_LOCKOUT = 'security.login_lockout', 'Login locked'
        GALLERY_LOCKOUT = 'security.gallery_lockout', 'Gallery gate locked'
        PASSWORD_RESET = 'security.password_reset', 'Password reset'
        PASSWORD_CHANGE = 'security.password_change', 'Password changed'
        # A user's own act, recorded for the trail (7.5-B): the actor is the user, not staff.
        PAYMENT_SUBMIT = 'payment.submit', 'Submitted a manual payment'


    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=30, choices=Action.choices, db_index=True)
    actor_id = models.UUIDField(null=True, blank=True)
    actor_email = models.EmailField(blank=True, default='')
    target_id = models.UUIDField(null=True, blank=True, db_index=True)
    target_email = models.EmailField(blank=True, default='')
    ip = models.GenericIPAddressField(null=True, blank=True)
    reason = models.CharField(max_length=300, blank=True, default='')

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        db_table = 'staff_audit_log'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['actor_id', '-created_at'], name='idx_audit_actor_created'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditLogImmutable('Audit log rows cannot be changed.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditLogImmutable('Audit log rows cannot be deleted.')

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.action} actor={self.actor_id} target={self.target_id}'
