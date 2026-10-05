# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/testing.py
"""Test helper: put a user on a real plan row so entitlement checks run for real."""
from datetime import timedelta

from django.utils import timezone

from .models import SubscriptionPlan, UserSubscription


def grant_plan(user, name='Pro', includes_branding_watermark=True, days=30,
               status=UserSubscription.SubscriptionStatus.ACTIVE):
    """`includes_branding_watermark` switches all three paid-feature flags together."""
    plan, _ = SubscriptionPlan.objects.update_or_create(
        name=name,
        defaults={
            'key': name.lower(), 'price': 1499, 'max_collections': 20, 'max_photos_per_gallery': 500,
            'storage_gb': 50, 'original_download': includes_branding_watermark,
            'watermark': includes_branding_watermark, 'branding': includes_branding_watermark,
        },
    )
    now = timezone.now()
    UserSubscription.objects.update_or_create(
        user=user,
        defaults={
            'plan': plan, 'status': status,
            'payment_method': UserSubscription.PaymentMethod.MANUAL,
            'starts_at': now - timedelta(days=1), 'expires_at': now + timedelta(days=days),
        },
    )
    return plan
