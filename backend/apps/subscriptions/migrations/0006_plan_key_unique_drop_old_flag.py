from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0005_seed_plans_dummy'),
    ]

    operations = [
        migrations.RemoveField(model_name='subscriptionplan', name='includes_branding_watermark'),
        migrations.AlterField(
            model_name='subscriptionplan', name='key',
            field=models.SlugField(max_length=50, unique=True, blank=True, help_text='Stable identifier (e.g. free, basic, pro, studio). Leave blank to derive it from the name; do not change once in use.'),
        ),
    ]
