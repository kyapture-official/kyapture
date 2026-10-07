from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('galleries', '0009_clear_stray_pin_limit'),
    ]

    operations = [
        migrations.AddField(
            model_name='gallery',
            name='media_token',
            field=models.CharField(blank=True, default='', editable=False, max_length=32),
        ),
    ]
