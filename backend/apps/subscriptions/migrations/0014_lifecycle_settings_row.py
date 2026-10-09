from django.db import migrations


def create_row(apps, schema_editor):
    """The one LifecycleSettings row exists from the start, so reading it is a single query (no lazy create)."""
    LifecycleSettings = apps.get_model('subscriptions', 'LifecycleSettings')
    LifecycleSettings.objects.get_or_create(pk=1)


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0013_subscription_lifecycle'),
    ]

    operations = [
        migrations.RunPython(create_row, migrations.RunPython.noop),
    ]
