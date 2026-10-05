"""
CHUNK 6.4-B.

  * merges existing duplicate default "My Favorites" lists (one visitor email that
    got a list per browser / unlock token) into the OLDEST list; the unique
    constraint that keeps them merged is 0011 (a separate migration: PostgreSQL
    cannot CREATE INDEX on a table that still has this data change's pending
    foreign-key trigger events in the same transaction)
  * DownloadLog.set_names - the set name(s) a download came from
  * DownloadJob.notification - the single bell notification of a multi-part job
"""
from django.db import migrations, models
import django.db.models.deletion


def merge_duplicate_default_lists(apps, schema_editor):
    """
    For every (gallery, lower(email)) holding several default lists: move each
    newer list's favorites into the oldest one (a photo the oldest already has is
    simply dropped), keep a visitor name if the oldest has none, and delete the
    emptied lists. Lists without an email (guests) are never touched. Idempotent.
    """
    FavoriteList = apps.get_model('clients', 'FavoriteList')
    Favorite = apps.get_model('clients', 'Favorite')

    groups = {}
    candidates = (
        FavoriteList.objects.filter(is_default=True, email__isnull=False).exclude(email='')
        .order_by('created_at', 'id')
    )
    for favorite_list in candidates:
        groups.setdefault((favorite_list.gallery_id, favorite_list.email.strip().lower()), []).append(favorite_list)

    for lists in groups.values():
        if len(lists) < 2:
            continue
        keep, extras = lists[0], lists[1:]
        owned = set(Favorite.objects.filter(favorite_list=keep).values_list('media_asset_id', flat=True))
        latest = max(fl.updated_at for fl in lists)
        for extra in extras:
            for favorite in Favorite.objects.filter(favorite_list=extra).order_by('created_at'):
                if favorite.media_asset_id in owned:
                    favorite.delete()
                    continue
                Favorite.objects.filter(pk=favorite.pk).update(favorite_list=keep, email=keep.email)
                owned.add(favorite.media_asset_id)
            if not keep.visitor_name and extra.visitor_name:
                keep.visitor_name = extra.visitor_name
            extra.delete()
        FavoriteList.objects.filter(pk=keep.pk).update(visitor_name=keep.visitor_name, updated_at=latest)


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0009_download_job_ready_email'),
        ('users', '0006_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='downloadlog',
            name='set_names',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='downloadjob',
            name='notification',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='+', to='users.notification'),
        ),
        migrations.RunPython(merge_duplicate_default_lists, migrations.RunPython.noop),
    ]
