from django.db import migrations, models

# ---------------------------------------------------------------------------
# DUMMY VALUES — PLACEHOLDERS, NOT REAL PRICING (chunk VID-A).
# Video minutes per plan: 0 = no video allowed, empty = unlimited, N = N minutes.
# The owner will replace these in Django admin (Subscriptions -> Subscription
# plans); nothing here is a product decision. Only rows still at the old
# "no limit" default are touched, so a value edited in admin is never overwritten.
# ---------------------------------------------------------------------------
DUMMY_VIDEO_MINUTES = {'free': 0, 'basic': 0, 'pro': 60, 'studio': 120}


def seed_video_minutes(apps, schema_editor):
    Plan = apps.get_model('subscriptions', 'SubscriptionPlan')
    for key, minutes in DUMMY_VIDEO_MINUTES.items():
        Plan.objects.filter(key=key, video_minutes__isnull=True).update(video_minutes=minutes)


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0006_plan_key_unique_drop_old_flag'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscriptionplan',
            name='video_minutes',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text="Video allowance in minutes, counted across all of the account's videos. "
                          "0 = videos not allowed on this plan. Leave empty for unlimited.",
            ),
        ),
        migrations.RunPython(seed_video_minutes, migrations.RunPython.noop),
    ]
