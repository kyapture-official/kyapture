# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/serializers.py
from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from apps.core.utils import sanitize_text
from . import payments
from .entitlements import FEATURES, feature_label, plan_feature_flags
from .models import (
    AVERAGE_PHOTO_SIZE_MB, FREE_PLAN_KEY, PaymentInstructions, SubscriptionPlan, UserSubscription, ManualPayment,
    estimate_photo_count,
)



class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """
    Read-only view of a plan row — the single feed for the Billing page, the
    pricing page and every locked-feature banner. `features` is generated from
    the entitlements.FEATURES registry + the plan's flag columns, so the
    comparison table needs no per-plan code. Prices are NPR; limits that are
    null mean unlimited. `estimated_photos` / `average_photo_size_mb` are the
    storage-to-photos estimate (see models.AVERAGE_PHOTO_SIZE_MB).
    """
    storage_bytes = serializers.SerializerMethodField()
    estimated_photos = serializers.SerializerMethodField()
    average_photo_size_mb = serializers.SerializerMethodField()
    is_free = serializers.BooleanField(read_only=True)
    features = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id',
            'key',
            'name',
            'price',
            'is_free',
            'storage_gb',
            'storage_bytes',
            'estimated_photos',
            'average_photo_size_mb',
            'max_collections',
            'video_minutes',
            'features',
        ]
        read_only_fields = fields

    def get_storage_bytes(self, obj):
        # 1 GB = 1024^3 bytes (Binary base-2 representation) [1.1.2]
        return obj.storage_gb * (1024 ** 3)

    def get_estimated_photos(self, obj):
        return estimate_photo_count(obj.storage_gb)

    def get_average_photo_size_mb(self, obj):
        return AVERAGE_PHOTO_SIZE_MB

    def get_features(self, obj):
        flags = plan_feature_flags(obj)
        return [
            {'key': key, 'label': feature_label(key), 'included': flags[key]}
            for key in FEATURES
        ]


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
    entitlements = serializers.SerializerMethodField()

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
            'entitlements',
        ]
        read_only_fields = fields

    def get_entitlements(self, obj):
        # Computed from the live subscription (active AND unexpired), not from
        # this row's own status field, so a lapsed plan reads as Free.
        from .entitlements import entitlements_for_subscription
        return entitlements_for_subscription(obj.user, obj)

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
        from apps.core.utils import get_user_subscription_metrics
        if not hasattr(self, '_metrics_cache'):
            self._metrics_cache = get_user_subscription_metrics(obj.user)
        return self._metrics_cache['current_total_storage_bytes']

    def get_storage_used_gb(self, obj):
        return round(self.get_storage_used_bytes(obj) / (1024 ** 3), 2)

    def get_galleries_used(self, obj):
        from apps.core.utils import get_user_subscription_metrics
        if not hasattr(self, '_metrics_cache'):
            self._metrics_cache = get_user_subscription_metrics(obj.user)
        return self._metrics_cache['live_galleries_count']

    def get_photos_used(self, obj):
        from apps.core.utils import get_user_subscription_metrics
        if not hasattr(self, '_metrics_cache'):
            self._metrics_cache = get_user_subscription_metrics(obj.user)
        return self._metrics_cache['current_photos_count']

class ManualPaymentSubmitSerializer(serializers.Serializer):
    """
    A photographer's manual payment: plan, amount, the transaction ID and a proof file.
    Field checks live here; every rule that must hold under a lock (the pending cap, the
    unique reference, money frozen at submission) is payments.create_payment.
    """
    plan = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.filter(is_active=True).exclude(key=FREE_PLAN_KEY)
    )
    amount = serializers.DecimalField(max_digits=8, decimal_places=2)
    reference = serializers.CharField(
        max_length=128, trim_whitespace=True,
        error_messages={'blank': 'Enter the transaction ID from your payment.',
                        'required': 'Enter the transaction ID from your payment.'},
    )
    payment_proof = serializers.FileField(allow_empty_file=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=payments.NOTES_MAX, default='')

    def validate_reference(self, value):
        try:
            return payments.validate_reference(value)
        except payments.PaymentError as error:
            raise serializers.ValidationError(error.message, code=error.code)

    def validate_payment_proof(self, file):
        try:
            self._proof_type = payments.sniff_proof(file)
        except payments.PaymentError as error:
            raise serializers.ValidationError(error.message, code=error.code)
        return file

    def validate_notes(self, value):
        return sanitize_text(value.strip())

    def validate(self, data):
        # The user cannot choose the price: the amount must equal the plan's price right now,
        # and create_payment freezes that price on the row.
        plan = data['plan']
        if data['amount'] != plan.price:
            raise serializers.ValidationError(
                {'amount': f"The amount (NPR {data['amount']}) does not match the {plan.name} plan price (NPR {plan.price:.2f})."},
                code='amount_mismatch',
            )
        data['proof_type'] = self._proof_type
        return data

    def create(self, validated_data):
        request = self.context['request']
        return payments.create_payment(
            user=request.user, plan=validated_data['plan'], amount=validated_data['amount'],
            reference=validated_data['reference'], proof=validated_data['payment_proof'],
            proof_type=validated_data['proof_type'], notes=validated_data.get('notes', ''), request=request,
        )


class OwnPaymentSerializer(serializers.Serializer):
    """
    One of the signed-in user's OWN payments (Billing history). An explicit allowlist: no proof
    file or link (the receipt is theirs, but only staff ever open it), no reviewer identity.
    """

    def to_representation(self, payment):
        return {
            'id': str(payment.pk),
            'plan_name': payment.plan.name,
            'amount': str(payment.amount),
            'currency': payment.currency,
            'reference': payment.reference,
            'status': payment.status,
            'created_at': payment.created_at,
            'reviewed_at': payment.reviewed_at,
            'rejection_reason': payment.rejection_reason,
            'period_end': payment.period_end,
            'has_proof': bool(payment.payment_proof),
            'notes': payment.notes,
        }


class PaymentInstructionsSerializer(serializers.Serializer):
    """The admin-edited payment instructions row. Plain text only; the QR is a normal public image URL."""

    def to_representation(self, row):
        request = self.context.get('request')
        qr = None
        if row.qr_image:
            qr = request.build_absolute_uri(row.qr_image.url) if request else row.qr_image.url
        return {
            'account_name': row.account_name,
            'esewa_id': row.esewa_id,
            'bank_name': row.bank_name,
            'bank_account_number': row.bank_account_number,
            'bank_branch': row.bank_branch,
            'note': row.note,
            'qr_url': qr,
            'currency': ManualPayment.CURRENCY,
            # The figures of the flow, from settings, so the Billing page never hard-codes them.
            'period_days': settings.MANUAL_PAYMENT_PERIOD_DAYS,
            'proof_max_mb': settings.MANUAL_PAYMENT_PROOF_MAX_MB,
            'max_pending': settings.MANUAL_PAYMENT_MAX_PENDING,
        }
