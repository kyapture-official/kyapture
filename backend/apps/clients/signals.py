# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/signals.py
"""
Notification hooks for client activity. Wired through model signals so the
download/favorite request paths themselves stay untouched: the alert is a
side effect of the activity row being recorded, and apps/users/notifications.py
swallows every error, so an email problem can never fail a client's request.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.users.notifications import notify_download, notify_favorite

from .models import DownloadLog, Favorite


@receiver(post_save, sender=DownloadLog)
def alert_photographer_of_download(sender, instance, created, **kwargs):
    if created:
        notify_download(instance)


@receiver(post_save, sender=Favorite)
def alert_photographer_of_favorite(sender, instance, created, **kwargs):
    if created:
        notify_favorite(instance)
