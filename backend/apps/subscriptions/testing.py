# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/testing.py
"""Test helper: put a user on a real plan row so entitlement checks run for real."""
from datetime import timedelta

from django.utils import timezone

from .models import SubscriptionPlan, UserSubscription
from .seed import PLAN_SEED


def grant_plan(user, name='Pro', includes_branding_watermark=True, days=30,
               status=UserSubscription.SubscriptionStatus.ACTIVE):
    """
    Subscribes `user` to the named plan ROW (price and limits come from the plan
    table / seed, never from this helper; a seeded plan missing from the table is
    re-created from the seed). `includes_branding_watermark` switches all three
    paid-feature flags together.
    """
    plan = SubscriptionPlan.objects.filter(name__iexact=name).first()
    if plan is None:
        plan = SubscriptionPlan.objects.create(**PLAN_SEED[name.lower()])
    for flag in ('original_download', 'watermark', 'branding'):
        setattr(plan, flag, includes_branding_watermark)
    plan.save()
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


def ensure_seed_plans():
    """
    Re-creates the migration-seeded plan rows that are missing (the seed values
    from seed.py). A TransactionTestCase flushes every table after each test,
    which drops these rows; a class that needs them calls this in setUp instead
    of using serialized_rollback, so the order the suite runs it in cannot
    change its result (7F).
    """
    for key, values in PLAN_SEED.items():
        SubscriptionPlan.objects.get_or_create(key=key, defaults=values)
    return SubscriptionPlan.objects.filter(key__in=PLAN_SEED).count()
