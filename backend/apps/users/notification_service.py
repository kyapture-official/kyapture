# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/notification_service.py
"""
Creates the dashboard-bell notifications (see users.models.Notification).

Event flow:  real event -> durable record (DownloadLog / Favorite / payment /
asset status ...) -> notification -> bell.  The record is already written by the
time anything here runs; a notification is only a pointer to it, so nothing in
this module can lose or alter history, and every function here swallows its own
errors — a bell problem must never fail the download/upload/payment that
triggered it.

Only events that really exist are wired in:
  download / favorite   apps/clients/signals.py (on DownloadLog / Favorite creation)
  payment               apps/subscriptions/views.py (admin approves/rejects)
  published             apps/galleries (publish toggle / gallery update)
  processing done/failed apps/photos/tasks.py (image + video pipelines)

Burst events coalesce: while a notification of the same kind for the same
gallery is still UNREAD and recent, the next event bumps its `count` and
rewrites its message instead of adding a row.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Notification

logger = logging.getLogger(__name__)

COALESCE_WINDOW = timedelta(minutes=30)
Kind = Notification.Kind


def record_notification(user, kind, gallery=None, *, message, coalesced_message=None):
    """
    Records one event. `coalesced_message` is a format string using `{count}`;
    when given, an unread, recent notification of the same (user, kind,
    gallery) is bumped instead of a new row being created. Returns the
    notification, or None if recording failed.
    """
    try:
        with transaction.atomic():
            if coalesced_message:
                existing = (
                    Notification.objects.select_for_update()
                    .filter(
                        user=user, kind=kind, gallery=gallery, is_read=False,
                        updated_at__gte=timezone.now() - COALESCE_WINDOW,
                    )
                    .first()
                )
                if existing:
                    existing.count += 1
                    existing.message = coalesced_message.format(count=existing.count)[:300]
                    existing.save(update_fields=['count', 'message', 'updated_at'])
                    return existing
            return Notification.objects.create(user=user, kind=kind, gallery=gallery, message=message[:300])
    except Exception:
        logger.exception('Could not record %s notification for user_id=%s', kind, getattr(user, 'pk', None))
        return None


# ─── per-event builders (each takes the already-persisted record) ────────────

def notify_download_event(download_log):
    gallery = download_log.gallery
    who = download_log.email or 'A client'
    if download_log.download_type == 'gallery':
        what = f'the "{download_log.photo_set.name}" set' if download_log.photo_set_id else 'the full collection'
    else:
        what = 'a video' if download_log.download_type == 'video' else 'a photo'
    record_notification(
        gallery.photographer, Kind.DOWNLOAD, gallery,
        message=f'{who} downloaded {what} from "{gallery.title}"',
        coalesced_message='{count} downloads from "' + gallery.title.replace('{', '{{').replace('}', '}}') + '"',
    )


def notify_favorite_event(favorite):
    gallery = favorite.gallery
    who = favorite.email or 'A client'
    record_notification(
        gallery.photographer, Kind.FAVORITE, gallery,
        message=f'{who} favorited a photo in "{gallery.title}"',
        coalesced_message='{count} new favorites in "' + gallery.title.replace('{', '{{').replace('}', '}}') + '"',
    )


def notify_payment_event(payment):
    approved = payment.status == 'approved'
    record_notification(
        payment.user, Kind.PAYMENT, None,
        message=(
            f'Your {payment.plan.name} plan payment was approved — your plan is active'
            if approved else f'Your {payment.plan.name} plan payment could not be approved'
        ),
    )


def notify_published(gallery):
    record_notification(
        gallery.photographer, Kind.PUBLISHED, gallery,
        message=f'"{gallery.title}" is now published and visible to clients',
    )


def notify_processing(asset, ok):
    gallery = asset.gallery
    title = gallery.title.replace('{', '{{').replace('}', '}}')
    noun = 'video' if asset.media_type == 'video' else 'photo'
    if ok:
        record_notification(
            gallery.photographer, Kind.PROCESSING_DONE, gallery,
            message=f'1 {noun} finished processing in "{gallery.title}"',
            coalesced_message='{count} items finished processing in "' + title + '"',
        )
    else:
        record_notification(
            gallery.photographer, Kind.PROCESSING_FAILED, gallery,
            message=f'1 {noun} failed to process in "{gallery.title}"',
            coalesced_message='{count} items failed to process in "' + title + '"',
        )


# ─── destination links (derived at read time, never stored) ──────────────────

def notification_link(notification):
    gallery = notification.gallery
    kind = notification.kind
    if kind == Kind.PAYMENT or gallery is None:
        return '/dashboard/billing'
    base = f'/dashboard/galleries/{gallery.slug}'
    if kind == Kind.DOWNLOAD:
        return f'{base}/activities?tab=downloads'
    if kind == Kind.FAVORITE:
        return f'{base}/activities?tab=favorites'
    return base
