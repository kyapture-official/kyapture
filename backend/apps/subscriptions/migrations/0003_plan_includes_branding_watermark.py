from django.db import migrations, models


def flag_existing_pro_and_above(apps, schema_editor):
    """
    Existing databases already hold the Pro and Studio plans (seed_plans).
    Pro-and-above includes Branding + Watermark, so flag those rows; Basic
    and any other plan stay unflagged until an admin opts them in.
    """
    SubscriptionPlan = apps.get_model('subscriptions', 'SubscriptionPlan')
    for plan in SubscriptionPlan.objects.all():
        if plan.name.strip().lower() in ('pro', 'studio'):
            plan.includes_branding_watermark = True
            plan.save(update_fields=['includes_branding_watermark'])


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionplan',
            name='includes_branding_watermark',
            field=models.BooleanField(
                default=False,
                help_text='Plan includes custom Branding (logo) and Watermark.',
            ),
        ),
        migrations.RunPython(flag_existing_pro_and_above, migrations.RunPython.noop),
    ]
