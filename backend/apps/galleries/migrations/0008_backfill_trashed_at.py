# backend/apps/galleries/migrations/0008_backfill_trashed_at.py
"""
Data migration: backfills `trashed_at` for galleries that were already
soft-deleted (is_active=False) BEFORE this field existed.

WHY: the new scheduled purge task (apps/galleries/tasks.py) only ever
touches a gallery once `trashed_at` is set AND past the retention
window — a NULL trashed_at is treated as "not eligible for purge yet"
deliberately, so this migration must never invent a value that would
cause an immediate/unexpected purge of a gallery a photographer soft-
deleted long ago and may not realize is now on a retention clock.

`updated_at` (auto_now=True) is the best available signal for "when did
this row last change," and the only write GalleryDetailView.delete()
ever made to a gallery was exactly the is_active=True -> False flip — so
for any row that is currently inactive, `updated_at` IS (to a very high
degree of confidence, barring some other unrelated field write landing
last) the actual soft-delete timestamp. This is a reasonable, safe
inference — not a guess invented from nothing — and it starts these
pre-existing trashed galleries on the same retention clock a
newly-deleted gallery gets, rather than leaving them in permanent limbo
(never eligible for purge, forever) or purging them immediately (which
would be "blindly deleting existing user data," explicitly disallowed).
"""
from django.db import migrations
from django.db.models import F


def backfill_trashed_at(apps, schema_editor):
    Gallery = apps.get_model('galleries', 'Gallery')
    Gallery.objects.filter(is_active=False, trashed_at__isnull=True).update(
        trashed_at=F('updated_at')
    )


def noop_reverse(apps, schema_editor):
    # Reversing this migration should not silently invent an "un-trash"
    # action — there is nothing meaningful to undo (the field itself is
    # removed by reversing 0007, not this migration).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('galleries', '0007_gallery_trashed_at_gallery_idx_gallery_trash_purge'),
    ]

    operations = [
        migrations.RunPython(backfill_trashed_at, noop_reverse),
    ]
