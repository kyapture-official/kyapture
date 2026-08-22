import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_phone_user_website'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='logo',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='photographer_logos/',
                help_text="Business logo shown on this photographer's public gallery pages.",
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='branding_color',
            field=models.CharField(
                default='#111827',
                max_length=7,
                help_text='Default brand accent color, pre-filled when creating new galleries.',
                validators=[django.core.validators.RegexValidator(
                    message='Color must be a valid 6-character HEX code (e.g., #FFFFFF).',
                    regex='^#[0-9a-fA-F]{6}$',
                )],
            ),
        ),
    ]