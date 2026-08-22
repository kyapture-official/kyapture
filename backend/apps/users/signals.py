# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/signals.py
import logging
from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver

from .models import User

logger = logging.getLogger(__name__)

# File-type fields on User that need orphan cleanup when replaced or cleared.
FILE_FIELDS = ('avatar', 'logo')


@receiver(pre_save, sender=User)
def auto_delete_old_file_on_change(sender, instance, **kwargs):
    """
    WHAT: Deletes the previous avatar/logo file from storage (local disk or S3)
        whenever a photographer uploads a replacement or explicitly clears it.
    WHY:  ModelSerializer.update() calls instance.save() after setattr()-ing new
        field values. Django's ORM never diffs FileField changes on save — it
        just writes the new path to the DB row. Without this signal, every
        replaced/cleared avatar or logo leaves the old binary permanently
        orphaned in storage (S3 cost leak; local disk fills up over time).

    Fires on EVERY User save (profile edits, password changes, etc.), not just
    avatar/logo updates — the per-field name comparison below makes it a no-op
    for saves that don't touch these two fields, at the cost of one extra
    SELECT per save. Acceptable: User saves are not a hot path.
    """
    if not instance.pk:
        return  # New user being created — nothing to compare against yet

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return  # Nothing to clean up if the row doesn't exist yet

    for field_name in FILE_FIELDS:
        old_file = getattr(old_instance, field_name)
        new_file = getattr(instance, field_name)

        # Nothing to clean up if there was no previous file, or it's unchanged
        if not old_file or old_file.name == new_file.name:
            continue

        try:
            old_file.delete(save=False)
        except Exception as e:
            logger.error(
                f"Failed to delete old '{field_name}' file for User {instance.pk} "
                f"on S3/Disk: {str(e)}"
            )


@receiver(post_delete, sender=User)
def auto_delete_files_on_user_delete(sender, instance, **kwargs):
    """
    WHAT: Purges avatar/logo files when the User row itself is deleted.
    WHY:  Mirrors apps/photos/signals.py's MediaAsset cleanup pattern. Gallery/
        MediaAsset CASCADE deletes already clean up gallery-scoped files, but
        the User row's own avatar/logo files have no other cleanup path.
    """
    for field_name in FILE_FIELDS:
        file_field = getattr(instance, field_name, None)
        if not file_field:
            continue
        try:
            file_field.delete(save=False)
        except Exception as e:
            logger.error(
                f"Failed to delete '{field_name}' file for deleted User {instance.pk} "
                f"on S3/Disk: {str(e)}"
            )