# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/models.py
import os
import uuid
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from apps.core.models import BaseModel
from apps.core.storage import PrivateMediaStorage, PublicMediaStorage


def get_payment_proof_upload_path(instance, filename):
    """
    Generates a secure, randomized, and isolated path for manual payment proof uploads.
    Format: payment_proofs/{user_uuid}/{payment_uuid}.{ext}
    """
    ext = os.path.splitext(filename)[1].lower()
    payment_uuid = instance.id if instance.id else uuid.uuid4()
    user_uuid = instance.user.id
    return f"payment_proofs/{user_uuid}/{payment_uuid}{ext}"


def get_payment_qr_upload_path(instance, filename):
    """The payment QR is public by design: a random name per upload, so a replaced QR never shows a cached old one."""
    ext = os.path.splitext(filename)[1].lower()
    return f"payment_instructions/qr_{uuid.uuid4().hex[:16]}{ext}"


FREE_PLAN_KEY = 'free'

# The ONE place the "average photo" size lives. The Billing page's "about N
# photos" figure under each plan's storage is an ESTIMATE:
#     photos = storage_gb * 1000 MB / AVERAGE_PHOTO_SIZE_MB,
# rounded down to 2 significant digits. It is served by the plans API
# (`average_photo_size_mb`, `estimated_photos`); the frontend never hard-codes it.
AVERAGE_PHOTO_SIZE_MB = 3


def estimate_photo_count(storage_gb):
    """Estimated photos that fit in `storage_gb`, rounded down to 2 significant digits (3 GB -> 1000)."""
    photos = int(storage_gb * 1000 // AVERAGE_PHOTO_SIZE_MB)
    if photos < 100:
        return photos
    step = 10 ** (len(str(photos)) - 2)
    return photos // step * step


class SubscriptionPlan(BaseModel):
    """
    THE single source of truth for every plan: display name, price (NPR),
    limits and feature flags. Edited in Django admin (later the staff
    console) — no price, limit or feature list lives in code. The Free tier
    is a row here too (key='free', price 0): a photographer with no live paid
    subscription is on that row, so its limits and flags are owner-editable
    exactly like the paid plans'.

    Read feature flags through apps/subscriptions/entitlements.py (the
    FEATURES registry names the flag fields below), never directly.
    """
    key = models.SlugField(
        max_length=50, unique=True, blank=True,
        help_text="Stable identifier (e.g. free, basic, pro, studio). Leave blank to derive it from the name; do not change once in use.",
    )
    name = models.CharField(max_length=50, unique=True, verbose_name='Display name')
    price = models.DecimalField(
        max_digits=8, decimal_places=2, verbose_name='Price (NPR / month)',
        help_text="Monthly price in Nepali rupees. 0 for the Free tier.",
    )

    # Limits. Empty (NULL) = unlimited.
    storage_gb = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    max_collections = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)],
        help_text="Maximum collections (galleries). Leave empty for unlimited.",
    )
    video_minutes = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Video allowance in minutes, counted across all of the account's videos. "
                  "0 = videos not allowed on this plan. Leave empty for unlimited.",
    )

    # Feature flags — one per plan-gated feature, named in entitlements.FEATURES.
    original_download = models.BooleanField(
        default=False, help_text="Clients can download byte-identical originals.")
    watermark = models.BooleanField(
        default=False, help_text="Watermark on client gallery images.")
    branding = models.BooleanField(
        default=False, help_text="Custom logo and colour on client galleries.")

    is_active = models.BooleanField(default=True, help_text="Shown on the Billing page.")

    class Meta:
        db_table = 'subscription_plans'
        ordering = ['price']

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def is_free(self):
        return self.key == FREE_PLAN_KEY

    @classmethod
    def get_free(cls):
        """The Free-tier row. Self-heals if an admin deleted it (editable afterwards)."""
        from .seed import PLAN_SEED
        plan, _ = cls.objects.get_or_create(key=FREE_PLAN_KEY, defaults=PLAN_SEED[FREE_PLAN_KEY])
        return plan

    def __str__(self):
        return f"{self.name} — NPR {self.price:,.0f}/month"


class UserSubscription(BaseModel):
    """
    Tracks a photographer's active subscription status, payment methods,
    and system access lifecycle bounds.
    """
    class SubscriptionStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'
        CANCELLED = 'cancelled', 'Cancelled'
        PENDING = 'pending', 'Pending'

    class PaymentMethod(models.TextChoices):
        ESEWA = 'esewa', 'eSewa'
        KHALTI = 'khalti', 'Khalti'
        BANK = 'bank', 'Bank Transfer'
        MANUAL = 'manual', 'Manual'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='user_subscriptions'
    )
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.PENDING
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices
    )
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'user_subscriptions'
        ordering = ['-expires_at']
        indexes = [
            # Compound index specifically optimized for background subscription sweep operations [1.1.2]
            models.Index(fields=['status', 'expires_at'], name='idx_sub_status_expiry')
        ]

    def __str__(self):
        return f"{self.user.email} — {self.plan.name} ({self.get_status_display()})"

def normalize_reference(text):
    """
    The form a payment reference is compared in: trimmed and lower-cased. The
    database holds a unique constraint on this value (ManualPayment.reference_key),
    so "ABC-1", " abc-1 " and "abc-1" are one reference.
    """
    return (text or '').strip().lower()


#Offline/Invoice Payments
class ManualPayment(BaseModel):
    """
    One bank-transfer / eSewa payment a photographer reports, waiting for staff.
    The ONLY payment model: submit (apps/subscriptions/views.py), the Billing page
    and the staff review (apps/subscriptions/staff_payments.py) all use this row.

    Money is frozen at submission: `amount`, `currency` and `plan_price` never
    change afterwards, so a later price edit on the plan cannot change a pending
    payment. Approving applies `plan` (the plan the user paid for) for
    settings.MANUAL_PAYMENT_PERIOD_DAYS and records the granted period here.
    The proof file is private: it is reachable only through the staff proof link.
    """
    class VerificationStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    CURRENCY = 'NPR'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='manual_payments'
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='manual_payments'
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default=CURRENCY)
    # The plan's price when the payment was submitted (amount must equal it then).
    plan_price = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    # The transaction id the user typed. `reference_key` is its trimmed, lower-cased
    # form; blank only on rows from before 7.5-B. A reference is unique across all
    # payments except REJECTED ones (see Meta.constraints and payments.py).
    reference = models.CharField(max_length=64, blank=True, default='')
    reference_key = models.CharField(max_length=64, blank=True, default='', editable=False)

    payment_proof = models.FileField(upload_to=get_payment_proof_upload_path, storage=PrivateMediaStorage())
    proof_type = models.CharField(max_length=40, blank=True, default='')   # sniffed from the bytes, not the name
    proof_size = models.PositiveBigIntegerField(default=0)                  # bytes (64-bit by the project rule)
    notes = models.TextField(blank=True)

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='verified_payments'
    )
    status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # Shown to the user on Billing and mailed to them. Plain text, set on reject only.
    rejection_reason = models.CharField(max_length=300, blank=True, default='')
    # The period an approval granted: expires_at of the subscription after this payment.
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'manual_payments'
        ordering = ['-created_at']
        indexes = [
            # High-performance index for filtering pending verification queues
            models.Index(fields=['status'], name='idx_manual_pay_status')
        ]
        constraints = [
            # One live claim per transaction id: pending and approved payments cannot share
            # a reference. A REJECTED payment releases it (only its own user may reuse it:
            # payments.check_reference). Rows from before 7.5-B have no reference.
            models.UniqueConstraint(
                fields=['reference_key'], name='uniq_manual_pay_reference',
                condition=~Q(status='rejected') & ~Q(reference_key=''),
            ),
        ]

    def save(self, *args, **kwargs):
        self.reference_key = normalize_reference(self.reference)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'reference' in update_fields:
            kwargs['update_fields'] = {*update_fields, 'reference_key'}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment #{str(self.id)[:8]} — {self.user.email} ({self.get_status_display()})"


class PaymentInstructions(models.Model):
    """
    Where to send the money, shown on the Billing page (chunk 7.5-B). One row,
    edited in Django admin (Subscriptions -> Payment instructions) and read at
    request time, so an edit shows immediately with no deploy.

    PUBLIC INFORMATION ONLY: the page shows every field to any signed-in user.
    Never put a password, PIN, API key or login here. Text is stored as plain
    text (tags stripped) and rendered escaped; the QR is a re-encoded image in
    public storage under a random name.
    """
    id = models.PositiveSmallIntegerField(primary_key=True, editable=False)  # always 1, set in save()
    account_name = models.CharField(max_length=100, blank=True, default='')
    esewa_id = models.CharField(max_length=60, blank=True, default='', verbose_name='eSewa ID / number')
    bank_name = models.CharField(max_length=100, blank=True, default='')
    bank_account_number = models.CharField(max_length=60, blank=True, default='')
    bank_branch = models.CharField(max_length=100, blank=True, default='')
    qr_image = models.ImageField(
        upload_to=get_payment_qr_upload_path, storage=PublicMediaStorage(), blank=True, null=True,
        verbose_name='QR image', help_text="Optional. PNG, JPEG or WEBP, public: anyone with the link can see it.",
    )
    note = models.TextField(
        max_length=500, blank=True, default='',
        help_text="Short plain-text note shown above the payment form (for example how long a review takes).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    LINE_FIELDS = ('account_name', 'esewa_id', 'bank_name', 'bank_account_number', 'bank_branch')

    class Meta:
        db_table = 'payment_instructions'
        verbose_name = 'Payment instructions'
        verbose_name_plural = 'Payment instructions'

    def save(self, *args, **kwargs):
        from apps.core.utils import sanitize_text
        self.pk = 1  # singleton
        for name in self.LINE_FIELDS:
            setattr(self, name, sanitize_text(' '.join(str(getattr(self, name) or '').split())))
        self.note = sanitize_text(str(self.note or '').strip())
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """The single row; created empty if missing."""
        try:
            return cls.objects.get(pk=1)
        except cls.DoesNotExist:
            return cls.objects.get_or_create(pk=1)[0]

    def __str__(self):
        return 'Payment instructions'


class UploadLimits(models.Model):
    """
    The ONE row of per-file upload limits that protect the server (chunk UP-A).
    Edited in Django admin (Subscriptions -> Upload limits) and read at request
    time through apps/subscriptions/upload_limits.py, so a change applies to the
    next upload with no restart and no deploy. These are global safety limits,
    not plan values (the plan's storage and video minutes are separate).

    The defaults below are the only place a figure lives in code. 1 MB here is
    1024 * 1024 bytes. max_video_mb must fit under the web server's request-body
    limit (nginx client_max_body_size): see docs/KYAPTURE_UPLOAD_LIMITS.md.
    """
    id = models.PositiveSmallIntegerField(primary_key=True, editable=False)  # always 1, set in save()
    max_image_mb = models.PositiveIntegerField(
        default=100, validators=[MinValueValidator(1)],
        verbose_name='Max image size (MB)',
        help_text="A photo larger than this is refused before it is processed.",
    )
    max_image_pixels = models.PositiveBigIntegerField(
        default=144_000_000, validators=[MinValueValidator(1)],
        verbose_name='Max image pixels (width x height)',
        help_text="A photo with more pixels than this is refused from its header, before it is decoded.",
    )
    max_video_mb = models.PositiveIntegerField(
        default=2048, validators=[MinValueValidator(1)],
        verbose_name='Max video size (MB)',
        help_text="A video larger than this is refused. The web server's client_max_body_size must be at least "
                  "this plus overhead (see docs/KYAPTURE_UPLOAD_LIMITS.md).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'upload_limits'
        verbose_name = 'Upload limits'
        verbose_name_plural = 'Upload limits'

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """The single row; created with the defaults if missing."""
        try:
            return cls.objects.get(pk=1)
        except cls.DoesNotExist:
            return cls.objects.get_or_create(pk=1)[0]

    def __str__(self):
        return 'Upload limits'
