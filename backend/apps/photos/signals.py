from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Photo


@receiver(post_delete, sender=Photo)
def auto_delete_files_on_db_delete(sender, instance, **kwargs):
    """
    Automatically deletes physical image and thumbnail binaries from local disk 
    or AWS S3 buckets when a Photo database record is deleted [1.1.2].
    Works across API deletes, cascade deletes, and Django Admin.
    """
    if instance.image:
        # Django's storage layer handles physical file deletions safely on disk or S3 [1.1.2]
        instance.image.delete(save=False)
    if instance.thumbnail:
        instance.thumbnail.delete(save=False)