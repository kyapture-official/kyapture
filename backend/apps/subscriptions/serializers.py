from django.db import models
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers
from apps.photos.models import Photo
from .models import SubscriptionPlan, UserSubscription, ManualPayment
from rest_framework.exceptions import ValidationError



class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """
    Read-only. Returns subscription plan tiers for the pricing page.
    Converts and exposes standard storage parameters as bytes for frontend utility [1.1.2].
    """
    storage_bytes = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id',
            'name',
            'price',
            'max_galleries',
            'max_photos_per_gallery',
            'storage_gb',
            'storage_bytes',
        ]
        read_only_fields = fields

    def get_storage_bytes(self, obj):
        # 1 GB = 1024^3 bytes (Binary base-2 representation) [1.1.2]
        return obj.storage_gb * (1024 ** 3)


class UserSubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializes a photographer's active subscription status.
    Uses cached single-pass database aggregations to compute usage metrics 
    without executing redundant subqueries, maximizing database throughput [1.1.2].
    """
    plan = SubscriptionPlanSerializer(read_only=True)

    # Computed fields for the sidebar and dashboard gating
    days_remaining = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    storage_used_bytes = serializers.SerializerMethodField()
    storage_used_gb = serializers.SerializerMethodField()
    galleries_used = serializers.SerializerMethodField()
    photos_used = serializers.SerializerMethodField()

    class Meta:
        model = UserSubscription
        fields = [
            'id',
            'plan',
            'status',
            'payment_method',
            'starts_at',
            'expires_at',
            'days_remaining',
            'is_expired',
            'storage_used_bytes',
            'storage_used_gb',
            'galleries_used',
            'photos_used',
        ]
        read_only_fields = fields

    def _get_photo_metrics(self, user):
        """
        Caches aggregated photo metrics on the serializer instance [1.1.2].
        Combines total storage size and overall photo counts into a single 
        SQL pass, preventing redundant subqueries [1.1.2].
        """
        if not hasattr(self, '_photo_metrics_cache'):
            # Single-pass database aggregation [1.1.2]
            metrics = Photo.objects.filter(
                gallery__photographer=user
            ).aggregate(
                total_size=Sum('file_size'),
                total_count=models.Count('id')
            )
            # Normalize SQL NULL values (None) to integer 0 [1.1.2]
            self._photo_metrics_cache = {
                'total_size': metrics['total_size'] or 0,
                'total_count': metrics['total_count'] or 0
            }
        return self._photo_metrics_cache

    def get_days_remaining(self, obj):
        """Calculates exact days left in active session. Protects negative values."""
        if not obj.expires_at or obj.status != 'active':
            return 0
        delta = obj.expires_at - timezone.now()
        return max(0, delta.days)

    def get_is_expired(self, obj):
        """Checks if current timestamp has exceeded subscription parameters."""
        if not obj.expires_at:
            return True
        return timezone.now() > obj.expires_at

    def get_storage_used_bytes(self, obj):
        """Returns aggregate photographer storage footprint in bytes [1.1.2]."""
        metrics = self._get_photo_metrics(obj.user)
        return metrics['total_size']

    def get_storage_used_gb(self, obj):
        """Translates and rounds total storage usage to 2-decimal gigabytes."""
        total_bytes = self.get_storage_used_bytes(obj)
        gb = total_bytes / (1024 ** 3)
        return round(gb, 2)

    def get_galleries_used(self, obj):
        """Counts total active galleries created by the photographer."""
        return obj.user.galleries.count()

    def get_photos_used(self, obj):
        """Returns total active photos uploaded by the photographer."""
        metrics = self._get_photo_metrics(obj.user)
        return metrics['total_count']


class ManualPaymentSubmitSerializer(serializers.ModelSerializer):
    """
    Handles photographer manual payment receipt submissions.
    Enforces three-layer validation on uploaded payment proofs [1.1.2].
    """
    payment_proof = serializers.ImageField(required=True)
    plan = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.filter(is_active=True)
    )

    class Meta:
        model = ManualPayment
        fields = ['plan', 'amount', 'payment_proof', 'notes']

    def validate_payment_proof(self, file):
        """Enforces a strict 5MB file-size ceiling on receipts to prevent storage abuse [1.1.2]."""
        MAX_PROOF_SIZE = 5 * 1024 * 1024  # 5 MB
        if file.size > MAX_PROOF_SIZE:
            raise serializers.ValidationError("Receipt image exceeds the 5MB limit.")
        
        # Enforce valid receipt image formats
        from PIL import Image as PILImage, UnidentifiedImageError
        try:
            file.seek(0)
            with PILImage.open(file) as img:
                img.verify()
            file.seek(0)
        except Exception:
            raise serializers.ValidationError("Uploaded file is not a valid or readable image receipt.")
            
        return file

    def validate(self, data):
        """
        Cross-field validation:
        1. Validates that the submitted payment amount matches the plan price 
        2. Blocks duplicate pending submissions for the same plan
        """
        
        user = self.context['request'].user
        plan = data.get('plan')
        amount = data.get('amount')

        if plan and amount:
            #1. Prevent photographers from forging the price on checkout
            if amount != plan.price:
                raise serializers.ValidationError({
                    "amount": f"Submitted payment amount (${amount}) does not match the chosen plan tier price (${plan.price})."
                })
            
            # 2. Block duplicate pending submissions for the same plan [1.1.2]
            duplicate = ManualPayment.objects.filter(
                user=user,
                plan=plan,
                status=ManualPayment.VerificationStatus.PENDING
            ).exists()
            
            if duplicate:
                raise serializers.ValidationError({
                    "plan": "You already have a pending payment submission for this plan tier. Please await administrative review."
                })
                
        return data

    def create(self, validated_data):
        """Creates the manual payment record with status=pending."""
        user = self.context['request'].user
        return ManualPayment.objects.create(
            user=user,
            status=ManualPayment.VerificationStatus.PENDING,
            **validated_data
        )    
        
        
# ─────────────────────────────────────────────────────────────
# 5. ADMIN PAYMENT LIST SERIALIZER (Read-Only)
# GET /api/v1/subscriptions/admin/payments/
# ─────────────────────────────────────────────────────────────
class AdminPaymentListSerializer(serializers.ModelSerializer):
    """
    Production-Grade Read-Only Serializer for administrative reviews.
    
    Exposes complete relational data including plan specifics and 
    photographer profile parameters by traversing ForeignKeys directly
    to avoid N+1 query overhead at the serialization layer.
    """
    # Nested representation of the target subscription plan
    plan = SubscriptionPlanSerializer(read_only=True)
    payment_proof_url = serializers.SerializerMethodField()

    # Direct database field traversal for related User entity properties
    photographer_email = serializers.CharField(
        source='user.email',
        read_only=True
    )
    photographer_display_name = serializers.CharField(
        source='user.display_name',
        read_only=True
    )

    class Meta:
        model = ManualPayment
        fields = [
            'id',
            'photographer_email',
            'photographer_display_name',
            'plan',
            'amount',
            'payment_method',
            'payment_proof_url',
            'notes',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_payment_proof_url(self, obj):
        """
        Safely generates absolute URL for manual financial transaction proof receipts.
        Handles both absolute domain prefixes and standard relative storage fallbacks.
        """
        request = self.context.get('request')
        if not obj.payment_proof:
            return None
            
        if request:
            return request.build_absolute_uri(obj.payment_proof.url)
            
        # Fallback in environments where the request context is missing (e.g. background tasks / shells)
        return obj.payment_proof.url


# ─────────────────────────────────────────────────────────────
# 6. ADMIN PAYMENT REVIEW SERIALIZER (Write-Only Validation)
# POST /api/v1/subscriptions/payments/{id}/review/
# ─────────────────────────────────────────────────────────────
class AdminPaymentReviewSerializer(serializers.Serializer):
    """
    Validates administrative decisions on pending ledger entries.
    
    Enforces strict idempotency. Validates that the underlying entity
    state is 'pending' before allowing any transitions to 'approved' 
    or 'rejected'.
    """
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    admin_note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        default=''
    )

    def validate(self, data):
        """
        Executes strict business-logic validations:
        1. Guarantees that the target payment context is present.
        2. Asserts state machine integrity (re-approving or re-rejecting is blocked).
        """
        payment = self.context.get('payment')
        
        # Guard Clause: Prevent code execution on invalid context configuration
        if not payment:
            raise ValidationError(
                detail="System Error: Serializer execution context is missing the target payment record.",
                code="missing_context"
            )

        # Idempotency Guard: State transitions can only originate from 'pending'
        if payment.status != 'pending':
            raise ValidationError(
                detail={
                    "action": f"This payment has already been evaluated and is marked as '{payment.status}'. Re-reviewing is blocked."
                },
                code="invalid_state_transition"
            )
            
        return data        