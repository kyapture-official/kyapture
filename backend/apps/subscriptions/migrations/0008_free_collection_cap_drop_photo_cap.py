from django.db import migrations

# ---------------------------------------------------------------------------
# DUMMY VALUE — PLACEHOLDER, NOT A PRODUCT DECISION (chunk BILL-B).
# Free gets a collection cap (value from apps/subscriptions/seed.py); Basic, Pro
# and Studio stay empty = unlimited. The owner replaces it in Django admin
# (Subscriptions -> Subscription plans). Only a Free row still at "unlimited"
# is touched, so a value already edited in admin is never overwritten.
# ---------------------------------------------------------------------------


def seed_free_collection_cap(apps, schema_editor):
    from apps.subscriptions.seed import PLAN_SEED
    Plan = apps.get_model('subscriptions', 'SubscriptionPlan')
    Plan.objects.filter(key='free', max_collections__isnull=True).update(
        max_collections=PLAN_SEED['free']['max_collections'])


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0007_video_minutes_enforced'),
    ]

    operations = [
        # Photo storage (GB) is now the only photo cap.
        migrations.RemoveField(model_name='subscriptionplan', name='max_photos_per_gallery'),
        migrations.RunPython(seed_free_collection_cap, migrations.RunPython.noop),
    ]
