from django.db import migrations
from django.utils.text import slugify

# ---------------------------------------------------------------------------
# DUMMY VALUES — PLACEHOLDERS, NOT REAL PRICING.
# The owner will replace every number below in Django admin (Subscriptions ->
# Subscription plans); nothing here is a product decision. Prices are NPR/month.
# Unlimited collections on every plan (Pixieset parity) = max_collections None.
# ---------------------------------------------------------------------------
DUMMY_PLANS = [
    # key,      name,     NPR/mo, GB,  original, watermark, branding
    ('free',   'Free',        0,    3, False, False, False),
    ('basic',  'Basic',     499,   20, False, False, False),
    ('pro',    'Pro',      1499,  100, True,  True,  True),
    ('studio', 'Studio',   2999,  500, True,  True,  True),
]


def seed(apps, schema_editor):
    Plan = apps.get_model('subscriptions', 'SubscriptionPlan')
    taken = set()
    for key, name, price, gb, original, watermark, branding in DUMMY_PLANS:
        plan = Plan.objects.filter(name__iexact=name).first() or Plan(name=name)
        plan.key = key
        plan.price = price
        plan.storage_gb = gb
        plan.max_collections = None          # unlimited
        plan.video_minutes = None            # no limit (not enforced yet)
        plan.original_download = original
        plan.watermark = watermark
        plan.branding = branding
        plan.is_active = True
        # An existing paid plan keeps its photos-per-collection limit; Free has none.
        if plan._state.adding:
            plan.max_photos_per_gallery = None
        plan.save()
        taken.add(plan.pk)
    # Any other pre-existing plan (custom names): derive a key, carry the old flag.
    for plan in Plan.objects.exclude(pk__in=taken):
        base = slugify(plan.name) or 'plan'
        key, n = base, 2
        while Plan.objects.filter(key=key).exists():
            key, n = f'{base}-{n}', n + 1
        plan.key = key
        plan.original_download = plan.watermark = plan.branding = plan.includes_branding_watermark
        plan.save()


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0004_plan_db_backed_schema'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
