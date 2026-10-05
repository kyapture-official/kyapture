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

The flags themselves are columns on SubscriptionPlan (admin-editable); the
FEATURES registry below is the one place that names them. A user with no live
paid subscription is on the Free plan ROW, so the owner can also grant a
feature to Free from admin.

Staff/superusers are entitled, matching how the upload gate already treats
them (apps/photos/views.py).
"""
from django.utils import timezone

BRANDING = 'branding'
WATERMARK = 'watermark'
# 1R.6: Original (byte-identical, unwatermarked) high-resolution downloads
# are plan-gated — see apps/galleries/serializers.py (save-time gate) and
# apps/clients/download_access.py (effective-mode resolution at download time).
ORIGINAL_DOWNLOAD = 'original_download'

# feature key -> (SubscriptionPlan flag field, comparison-table label,
#                 upgrade-error code, subject+verb and action, for the upgrade message).
# Adding a plan-gated feature = one boolean column + one line here.
FEATURES = {
    BRANDING: ('branding', 'Custom logo & colour', 'branding_requires_upgrade',
               'Custom branding is', 'add your logo'),
    WATERMARK: ('watermark', 'Watermark', 'watermark_requires_upgrade',
                'Watermarking is', 'enable it'),
    ORIGINAL_DOWNLOAD: ('original_download', 'Original-quality download', 'original_download_requires_upgrade',
                        'Original-quality downloads are', 'offer untouched originals'),
}
UPGRADE_CODES = {key: spec[2] for key, spec in FEATURES.items()}


def feature_label(feature):
    return FEATURES[feature][1]


def required_plan_name(feature):
    """Cheapest active plan that includes `feature` (None if no plan does)."""
    from .models import SubscriptionPlan
    plan = (
        SubscriptionPlan.objects
        .filter(is_active=True, **{FEATURES[feature][0]: True})
        .order_by('price')
        .first()
    )
    return plan.name if plan else None


def upgrade_message(feature):
    """Locked-feature copy, naming the real cheapest plan that unlocks it."""
    _field, _label, _code, noun, action = FEATURES[feature]
    plan_name = required_plan_name(feature)
    where = f'on the {plan_name} plan and above' if plan_name else 'on a paid plan'
    return f'{noun} available {where}. Upgrade your plan to {action}.'


def plan_feature_flags(plan):
    """{feature: bool} for a SubscriptionPlan row."""
    return {key: bool(getattr(plan, spec[0])) for key, spec in FEATURES.items()}


def _answer(plan, paid):
    flags = plan_feature_flags(plan)
    flags['plan_name'] = plan.name if paid else None
    return flags


def _all_features(plan_name):
    answer = {key: True for key in FEATURES}
    answer['plan_name'] = plan_name
    return answer


def _plan_for(user):
    """(plan row, is_paid): the live paid plan, else the Free plan row."""
    from .models import SubscriptionPlan
    plan = _active_plan(user)
    return (plan, True) if plan else (SubscriptionPlan.get_free(), False)


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
    {'branding': bool, 'watermark': bool, 'original_download': bool,
     'plan_name': str | None}. One subscription query (plus the Free row for
    unpaid users); callers needing several flags should use this rather than
    calling has_feature() repeatedly.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return {**{key: False for key in FEATURES}, 'plan_name': None}
    if user.is_superuser or user.is_staff:
        return _all_features('Admin')
    return _answer(*_plan_for(user))


def entitlements_for_subscription(user, subscription):
    """
    Same answer as get_feature_entitlements(), computed from a UserSubscription
    row the caller ALREADY loaded (with its plan), so serializing a
    subscription doesn't re-query the same row just to read its plan flags.
    """
    if user.is_superuser or user.is_staff:
        return _all_features('Admin')
    live = (
        subscription is not None
        and subscription.status == 'active'
        and subscription.expires_at > timezone.now()
    )
    if live:
        return _answer(subscription.plan, True)
    from .models import SubscriptionPlan
    return _answer(SubscriptionPlan.get_free(), False)


def has_feature(user, feature):
    return get_feature_entitlements(user)[feature]


def require_feature(user, feature):
    """Raises the project's standard 403 gating error ({'error', 'code'}) for an unentitled user."""
    if not has_feature(user, feature):
        from apps.core.utils import raise_gating_violation
        raise_gating_violation(upgrade_message(feature), UPGRADE_CODES[feature])
