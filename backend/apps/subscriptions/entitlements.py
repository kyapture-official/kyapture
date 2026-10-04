# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/entitlements.py
"""
Plan-feature entitlements — the single place that answers "may this
photographer use feature X?" for the paid, plan-gated features.

Reuses the existing plan architecture (UserSubscription -> SubscriptionPlan)
rather than introducing a parallel system: an entitlement is a flag on the
photographer's CURRENT plan, and "current" means an ACTIVE subscription that
has not passed its expiry. A missing, pending, cancelled or lapsed
subscription is the Free tier and is entitled to nothing here.

Used on both sides of every paid feature:
  - writes (user/gallery serializers) reject Free users with a 403 gating
    error, so the frontend can never be the only enforcement;
  - reads (public gallery payload, watermark processing) re-check at use time,
    so a lapsed plan stops showing the logo / watermarking new derivatives
    even though the stored configuration still exists.

Staff/superusers are entitled, matching how the upload gate already treats
them (apps/photos/views.py).
"""
from django.utils import timezone

BRANDING = 'branding'
WATERMARK = 'watermark'
# 1R.6: Original (byte-identical, unwatermarked) high-resolution downloads
# are gated behind the same Pro+ bundle as branding/watermark — see
# apps/galleries/serializers.py (save-time gate) and apps/clients/
# download_access.py (effective-mode resolution at download time).
ORIGINAL_DOWNLOAD = 'original_download'

UPGRADE_CODES = {
    BRANDING: 'branding_requires_upgrade',
    WATERMARK: 'watermark_requires_upgrade',
    ORIGINAL_DOWNLOAD: 'original_download_requires_upgrade',
}
UPGRADE_MESSAGES = {
    BRANDING: 'Custom branding is available on the Pro plan and above. Upgrade your plan to add your logo.',
    WATERMARK: 'Watermarking is available on the Pro plan and above. Upgrade your plan to enable it.',
    ORIGINAL_DOWNLOAD: 'Original-quality downloads are available on the Pro plan and above. Upgrade your plan to offer untouched originals.',
}


def _active_plan(user):
    from .models import UserSubscription
    sub = (
        UserSubscription.objects
        .select_related('plan')
        .filter(user=user, status=UserSubscription.SubscriptionStatus.ACTIVE, expires_at__gt=timezone.now())
        .first()
    )
    return sub.plan if sub else None


def get_feature_entitlements(user):
    """
    {'branding': bool, 'watermark': bool, 'plan_name': str | None}.
    One subscription query; callers needing both flags should use this
    rather than calling has_feature() twice.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return {BRANDING: False, WATERMARK: False, ORIGINAL_DOWNLOAD: False, 'plan_name': None}
    if user.is_superuser or user.is_staff:
        return {BRANDING: True, WATERMARK: True, ORIGINAL_DOWNLOAD: True, 'plan_name': 'Admin'}
    plan = _active_plan(user)
    included = bool(plan and plan.includes_branding_watermark)
    return {
        BRANDING: included, WATERMARK: included, ORIGINAL_DOWNLOAD: included,
        'plan_name': plan.name if plan else None,
    }


def entitlements_for_subscription(user, subscription):
    """
    Same answer as get_feature_entitlements(), computed from a UserSubscription
    row the caller ALREADY loaded (with its plan), so serializing a
    subscription doesn't re-query the same row just to read its plan flag.
    """
    if user.is_superuser or user.is_staff:
        return {BRANDING: True, WATERMARK: True, ORIGINAL_DOWNLOAD: True, 'plan_name': 'Admin'}
    live = (
        subscription is not None
        and subscription.status == 'active'
        and subscription.expires_at > timezone.now()
    )
    plan = subscription.plan if live else None
    included = bool(plan and plan.includes_branding_watermark)
    return {
        BRANDING: included, WATERMARK: included, ORIGINAL_DOWNLOAD: included,
        'plan_name': plan.name if plan else None,
    }


def has_feature(user, feature):
    return get_feature_entitlements(user)[feature]


def require_feature(user, feature):
    """Raises the project's standard 403 gating error ({'error', 'code'}) for a Free user."""
    if not has_feature(user, feature):
        from apps.core.utils import raise_gating_violation
        raise_gating_violation(UPGRADE_MESSAGES[feature], UPGRADE_CODES[feature])
