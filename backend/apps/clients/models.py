# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/models.py
import secrets
from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from apps.core.models import BaseModel


def generate_secure_token():
    """
    Generates a cryptographically secure, unguessable 64-character hex token.
    Uses Python's native CSPRNG secrets module. 32 bytes of entropy = 64 characters [1.1.2].
    """
    return secrets.token_hex(32)


class ClientSessionQuerySet(models.QuerySet):
    def not_expired(self):
        """
        Phase 4 (auth hardening) — a ClientSession previously never
        expired at all: once issued (by a correct gallery-password
        unlock), the token stayed valid forever until the photographer
        explicitly rotated the gallery password (GallerySetPasswordView
        revokes all sessions on change) or manually deleted rows. This
        enforces a maximum session age (CLIENT_SESSION_TTL_DAYS) on top
        of that — every session-validation call site in apps/clients/
        views.py goes through this instead of a bare
        `ClientSession.objects.filter(...)`, so the TTL is enforced
        consistently everywhere a token is checked, not just in one place.
        """
        cutoff = timezone.now() - timezone.timedelta(
            days=getattr(settings, 'CLIENT_SESSION_TTL_DAYS', 30)
        )
        return self.filter(created_at__gte=cutoff)


class ClientSession(BaseModel):
    """
    Tracks anonymous client gallery access authorization.
    When a public client unlocks a password-protected gallery,
    this record stores their authorization token, eliminating the need
    for a standard registration/user account.
    """
    objects = ClientSessionQuerySet.as_manager()

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
    


class DownloadLog(BaseModel):
    """
    Audits and logs high-resolution gallery downloads requested by guest clients.
    Acts as the primary lead generation database for photographers, tracking
    who downloaded their collections and when.
    """

    class DownloadType(models.TextChoices):
        GALLERY = 'gallery', 'Full Gallery'
        PHOTO = 'photo', 'Single Photo'
        VIDEO = 'video', 'Single Video'

    class Resolution(models.TextChoices):
        WEB = 'web', 'Web Size'
        DOWNLOAD = 'download', 'Download Master'
        ORIGINAL = 'original', 'High Resolution'

    gallery = models.ForeignKey(
        'galleries.Gallery',
        on_delete=models.CASCADE,
        related_name='download_logs'
    )

    # Phase 3: which media asset was downloaded, when this log entry is
    # for a single-photo/single-video download rather than the full
    # gallery ZIP. Null means "full gallery" (download_type=GALLERY).
    # SET_NULL on asset deletion: the audit row (who/when/resolution)
    # must survive the photo being deleted later.
    media_asset = models.ForeignKey(
        'photos.MediaAsset',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='download_logs'
    )

    # Which PhotoSet the download was scoped to, if the client downloaded
    # from within a set tab rather than the full gallery. Purely
    # informational — SET_NULL so deleting a set never deletes its
    # download history.
    photo_set = models.ForeignKey(
        'photos.PhotoSet',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='download_logs'
    )

    download_type = models.CharField(
        max_length=10,
        choices=DownloadType.choices,
        default=DownloadType.GALLERY,
    )

    resolution = models.CharField(
        max_length=10,
        choices=Resolution.choices,
        default=Resolution.ORIGINAL,
        help_text="Which derivative was actually served: the web-optimized "
                   "display file, optimized download master, or authorized original."
    )

    pin_verified = models.BooleanField(
        default=False,
        help_text="Whether this download required and passed the gallery's "
                   "optional download PIN gate.",
    )

    # Required for a full-gallery ZIP (the lead-capture flow); null for a
    # single-photo/video download, which is deliberately frictionless and
    # captures no email (see PublicPhotoDownloadView's docstring).
    email = models.EmailField(
        null=True,
        blank=True,
        help_text="Client email — required for a gallery ZIP download (lead capture), "
                  "null for a frictionless single-photo/video download.",
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Auditable IP address of the client device requesting the download."
    )

    # The attachment name the server ACTUALLY sent in Content-Disposition for
    # this download (e.g. "my-gallery-photo-download-1of1.zip" or the photo's
    # name). Stored, not re-derived, so the activity row stays truthful even
    # if the gallery slug, set name or asset name changes later. Blank only on
    # rows written before this field existed.
    filename = models.CharField(max_length=255, blank=True, default='')

    # How many photos/videos were in a gallery/set ZIP (null for a single-file
    # download and for rows written before this field existed).
    photo_count = models.PositiveIntegerField(null=True, blank=True)

    # Names of the photo sets the downloaded files came from (a whole-gallery or
    # multi-set ZIP spans several; `photo_set` can hold only one). Stored, not
    # re-derived, so the row stays truthful if a set is renamed or deleted.
    set_names = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'download_logs'
        ordering = ['-created_at']
        indexes = [
            # High-performance index for photographer analytics dashboards
            models.Index(
                fields=['gallery', 'created_at'],
                name='idx_download_gallery_date'
            )
        ]

    def __str__(self):
        return f"Download: {self.gallery.title} — {self.email}"


class FavoriteList(BaseModel):
    """
    One visitor's named list of favorites inside one gallery (Pixieset-style
    "My Favorites"). There are no client accounts, so a list belongs to the same
    identity a Favorite always did: `client_key` (the gallery unlock token for a
    protected gallery, or the browser's anonymous client_uid for an open one).
    `client_key` is a credential and is never exposed; the photographer sees
    the visitor's `email` instead (null = a guest who never gave one).
    """
    gallery = models.ForeignKey(
        'galleries.Gallery', on_delete=models.CASCADE, related_name='favorite_lists'
    )
    client_key = models.CharField(max_length=128)
    email = models.EmailField(null=True, blank=True)
    visitor_name = models.CharField(max_length=80, blank=True, default='')
    name = models.CharField(max_length=80, default='My Favorites')
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = 'favorite_lists'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['gallery', 'client_key', 'name'], name='unique_favorite_list_name'),
            # One visitor email = ONE default "My Favorites" list per gallery, however
            # many browsers / unlock tokens they come back with (case-insensitive).
            models.UniqueConstraint(
                Lower('email'), 'gallery',
                condition=models.Q(is_default=True, email__isnull=False) & ~models.Q(email=''),
                name='unique_default_list_per_gallery_email',
            ),
        ]
        indexes = [
            models.Index(fields=['gallery', 'client_key'], name='idx_favlist_gallery_client'),
        ]

    def __str__(self):
        return f"{self.name} ({self.email or 'guest'})"


class Favorite(BaseModel):
    """
    A single client's favorite mark on one media asset within one gallery.

    Client identity model (Phase 3): this app has no client accounts, so
    favorites reuse the two identity mechanisms that already exist for
    gallery access rather than inventing a third:

    - Password-protected galleries: `client_key` is the same
      ClientSession.access_token already issued at unlock — the
      strongest identity available here, since it was only handed out
      after a correct password check. `client_session` links back to
      that row (and its optional email) for photographer-side visibility.
    - Open (non-protected) galleries: there is no session/token concept
      at all today. `client_key` is a random identifier the frontend
      generates once per browser and persists (same sessionStorage
      pattern as clientStore's gallery tokens), sent by the client on
      every favorite call. This is the best identity available for a
      fully anonymous, unauthenticated view — consistent with how this
      app already treats anonymous clients everywhere else.

    Either way, `client_key` + `gallery` + `media_asset` is the natural
    unique key: idempotent favorite/unfavorite is just "does this row
    exist," and scoping every query by `gallery` as well as `client_key`
    means a client's identity from one gallery can never leak favorites
    into another gallery, even for the rare case of two galleries
    generating the same client-side key.
    """
    gallery = models.ForeignKey(
        'galleries.Gallery',
        on_delete=models.CASCADE,
        related_name='favorites'
    )
    media_asset = models.ForeignKey(
        'photos.MediaAsset',
        on_delete=models.CASCADE,
        related_name='favorited_by'
    )
    client_session = models.ForeignKey(
        ClientSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='favorites',
        help_text="Set only for password-protected galleries, where a real "
                  "ClientSession already exists.",
    )
    client_key = models.CharField(
        max_length=128,
        help_text="Stable per-client identifier: the gallery's access_token "
                  "for protected galleries, or a client-generated anonymous "
                  "id for open galleries.",
    )
    email = models.EmailField(
        null=True,
        blank=True,
        help_text="Copied from the client session's email when available, "
                  "for photographer-facing favorite activity.",
    )
    # The visitor's list this favorite sits in. A photo may be in several of a
    # visitor's lists. Null only on rows from before lists existed (the
    # migration backfills those into a default "My Favorites" list).
    favorite_list = models.ForeignKey(
        FavoriteList, null=True, blank=True, on_delete=models.CASCADE, related_name='favorites'
    )

    class Meta:
        db_table = 'favorites'
        ordering = ['-created_at']
        constraints = [
            # The idempotency guarantee: favoriting twice is a no-op, not
            # a duplicate row - per list, so a photo can live in several lists.
            models.UniqueConstraint(
                fields=['favorite_list', 'media_asset'],
                condition=models.Q(favorite_list__isnull=False),
                name='unique_favorite_per_list_asset',
            ),
            models.UniqueConstraint(
                fields=['gallery', 'media_asset', 'client_key'],
                condition=models.Q(favorite_list__isnull=True),
                name='unique_favorite_per_client_asset',
            ),
        ]
        indexes = [
            # Covers "does this client have any favorites in this
            # gallery" (initial page load) without a per-photo query.
            models.Index(fields=['gallery', 'client_key'], name='idx_favorite_gallery_client'),
            # Covers the photographer-facing "most favorited" aggregation.
            models.Index(fields=['media_asset'], name='idx_favorite_media_asset'),
        ]

    def __str__(self):
        return f"Favorite: {self.gallery.title} — asset {self.media_asset_id}"


class DownloadJob(BaseModel):
    """
    A gallery / set ZIP that is prepared in the background (Celery) before the
    client can download it — gallery downloads never stream straight off the
    request that asked for them.

    Lifecycle: the authorized POST creates the row (PREPARING) and queues the
    task -> the task writes the ZIP into PRIVATE storage and marks it READY
    (or FAILED) -> the client polls the status endpoint and, once READY,
    downloads each file through a short-lived signed URL. Rows (and their
    stored ZIPs) expire and are purged, see apps/clients/download_jobs.py.

    A job is bound to the gallery it was created for and to the email that
    passed the download gate, so another gallery, or another visitor's
    token, can never read it.
    """

    class State(models.TextChoices):
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready'
        FAILED = 'failed', 'Failed'

    gallery = models.ForeignKey(
        'galleries.Gallery', on_delete=models.CASCADE, related_name='download_jobs'
    )
    photo_set = models.ForeignKey(
        'photos.PhotoSet', null=True, blank=True, on_delete=models.SET_NULL, related_name='download_jobs'
    )
    resolution = models.CharField(max_length=10, default='download')
    # What the files were made from when the job was created (Web Size px + watermark
    # state, or the High Resolution mode). An identical request is only reused while
    # this still matches the gallery's current settings (download_jobs.job_variant).
    variant = models.CharField(max_length=80, blank=True, default='')
    # Optional explicit selection (validated UUIDs); empty = the whole gallery/set.
    asset_ids = models.JSONField(default=list, blank=True)

    email = models.EmailField(null=True, blank=True)
    pin_verified = models.BooleanField(default=False)

    state = models.CharField(max_length=10, choices=State.choices, default=State.PREPARING)
    error_code = models.CharField(max_length=40, blank=True, default='')
    # [{"name": str, "size_bytes": int, "storage_path": str}] — storage_path is
    # a PRIVATE storage key and is never serialized to a client.
    files = models.JSONField(default=list, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # "Your photos are ready" email (apps/clients/ready_email.py): stamped when it
    # is claimed, so one job mails at most once; requester_ip is the visitor's
    # address when the job was asked for, kept only to rate-limit those emails.
    ready_email_sent_at = models.DateTimeField(null=True, blank=True)
    requester_ip = models.GenericIPAddressField(null=True, blank=True)

    # Set when the first file of this job is actually served — one job is one
    # row in the photographer's Download Activity, however often it is re-saved.
    download_log = models.ForeignKey(
        DownloadLog, null=True, blank=True, on_delete=models.SET_NULL, related_name='jobs'
    )
    # The ONE bell notification of this job: every part of a multi-part ZIP that
    # is downloaded bumps it ("N files") instead of adding a row per part.
    notification = models.ForeignKey(
        'users.Notification', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    class Meta:
        db_table = 'download_jobs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['gallery', 'state'], name='idx_djob_gallery_state'),
            models.Index(fields=['expires_at'], name='idx_djob_expires'),
        ]

    def __str__(self):
        return f"DownloadJob {self.id} ({self.state})"
