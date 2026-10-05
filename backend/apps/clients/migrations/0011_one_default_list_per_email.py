"""CHUNK 6.4-B: one visitor email = ONE default "My Favorites" list per gallery (case-insensitive)."""
from django.db import migrations, models
import django.db.models.functions.text


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0010_merge_duplicate_favorite_lists'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='favoritelist',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower('email'), models.F('gallery'),
                condition=models.Q(('email__isnull', False), ('is_default', True), models.Q(('email', ''), _negated=True)),
                name='unique_default_list_per_gallery_email'),
        ),
    ]
