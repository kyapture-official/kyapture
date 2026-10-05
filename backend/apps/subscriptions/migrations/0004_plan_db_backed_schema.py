import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    """Schema half of the DB-backed plans change (data is 0005, cleanup 0006)."""

    dependencies = [
        ('subscriptions', '0003_plan_includes_branding_watermark'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionplan', name='key',
            field=models.SlugField(max_length=50, null=True, help_text='Stable identifier (e.g. free, basic, pro, studio). Leave blank to derive it from the name; do not change once in use.'),
        ),
        migrations.AddField(
            model_name='subscriptionplan', name='original_download',
            field=models.BooleanField(default=False, help_text='Clients can download byte-identical originals.'),
        ),
        migrations.AddField(
            model_name='subscriptionplan', name='watermark',
            field=models.BooleanField(default=False, help_text='Watermark on client gallery images.'),
        ),
        migrations.AddField(
            model_name='subscriptionplan', name='branding',
            field=models.BooleanField(default=False, help_text='Custom logo and colour on client galleries.'),
        ),
        migrations.AddField(
            model_name='subscriptionplan', name='video_minutes',
            field=models.PositiveIntegerField(null=True, blank=True, help_text='Video allowance in minutes. Leave empty for no limit. Not enforced yet (owner decision pending).'),
        ),
        migrations.RenameField(
            model_name='subscriptionplan', old_name='max_galleries', new_name='max_collections',
        ),
        migrations.AlterField(
            model_name='subscriptionplan', name='max_collections',
            field=models.PositiveIntegerField(null=True, blank=True, validators=[django.core.validators.MinValueValidator(1)], help_text='Maximum collections (galleries). Leave empty for unlimited.'),
        ),
        migrations.AlterField(
            model_name='subscriptionplan', name='max_photos_per_gallery',
            field=models.PositiveIntegerField(null=True, blank=True, validators=[django.core.validators.MinValueValidator(1)], help_text='Maximum photos per collection. Leave empty for unlimited.'),
        ),
        migrations.AlterField(
            model_name='subscriptionplan', name='name',
            field=models.CharField(max_length=50, unique=True, verbose_name='Display name'),
        ),
        migrations.AlterField(
            model_name='subscriptionplan', name='price',
            field=models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Price (NPR / month)', help_text='Monthly price in Nepali rupees. 0 for the Free tier.'),
        ),
        migrations.AlterField(
            model_name='subscriptionplan', name='is_active',
            field=models.BooleanField(default=True, help_text='Shown on the Billing page.'),
        ),
    ]
