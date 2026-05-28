import os
import uuid
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from apps.core.models import BaseModel


def get_payment_proof_upload_path(instance, filename):
    """
    Generates a secure, randomized, and isolated path for manual payment proof uploads.
    Format: payment_proofs/{user_uuid}/{payment_uuid}.{ext}
    """
    ext = os.path.splitext(filename)[1].lower()
    payment_uuid = instance.id if instance.id else uuid.uuid4()
    user_uuid = instance.user.id
    return f"payment_proofs/{user_uuid}/{payment_uuid}{ext}"


class SubscriptionPlan(BaseModel):
    """
    Represents platform tiers (e.g., Basic, Pro, Studio) detailing
    pricing parameters and multi-tenant system resource limitations.
    """
    name = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    
    # System Resource Limits (Strict Positive Values Only)
    max_galleries = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    max_photos_per_gallery = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    storage_gb = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'subscription_plans'
        ordering = ['price']

    def __str__(self):
        return f"{self.name} — ${self.price}/mo"


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


class ManualPayment(BaseModel):
    """
    Holds receipts and metadata for out-of-band payment transfers (direct eSewa/Khalti/Bank screenshots).
    Admins review, approve, or reject these records inside the administrative dashboard.
    """
    class VerificationStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

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
    payment_proof = models.ImageField(upload_to=get_payment_proof_upload_path)
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

    class Meta:
        db_table = 'manual_payments'
        ordering = ['-created_at']
        indexes = [
            # High-performance index for filtering pending verification queues
            models.Index(fields=['status'], name='idx_manual_pay_status')
        ]

    def __str__(self):
        return f"Payment #{str(self.id)[:8]} — {self.user.email} ({self.get_status_display()})"