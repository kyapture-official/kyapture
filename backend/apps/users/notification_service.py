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
  feedback              apps/users/feedback_api.py (a user submits feedback; staff only)

Burst events coalesce: while a notification of the same kind for the same
gallery is still UNREAD and recent, the next event bumps its `count` and
rewrites its message instead of adding a row.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Notification, User

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
    """
    One notification per real download, worded "<What> downloaded by <email>".
    Separate downloads are deliberately NOT coalesced: the text names who
    downloaded what, which a "3 downloads" roll-up would lose (the bell's list is
    paginated and purged, so one row per download is bounded).

    The exception is the parts of ONE multi-part ZIP (the log carries its
    `_download_job`): they are one download, so they share ONE notification that
    grows "... · 2 files", "... · 3 files" as each part is fetched.
    """
    gallery = download_log.gallery
    who = download_log.email or 'a client'
    what = 'Gallery' if download_log.download_type == 'gallery' else (
        'Video' if download_log.download_type == 'video' else 'Photo'
    )
    message = f'{what} downloaded by {who}'
    job = getattr(download_log, '_download_job', None)
    if job is not None:
        return _notify_job_download(gallery, job, message)
    return record_notification(gallery.photographer, Kind.DOWNLOAD, gallery, message=message)


def _notify_job_download(gallery, job, message):
    """The job's single notification: created with its first part, bumped by each later one."""
    from apps.clients.models import DownloadJob      # clients imports this module's package at load time

    try:
        with transaction.atomic():
            row = DownloadJob.objects.select_for_update().filter(pk=job.pk).first()
            existing = Notification.objects.filter(pk=row.notification_id).first() if row and row.notification_id else None
            if existing:
                existing.count += 1
                existing.message = f'{message} · {existing.count} files'[:300]
                existing.is_read = False          # a new file is new activity, even if the first part was read
                existing.read_at = None
                existing.save(update_fields=['count', 'message', 'is_read', 'read_at', 'updated_at'])
                return existing
            note = Notification.objects.create(
                user=gallery.photographer, kind=Kind.DOWNLOAD, gallery=gallery, message=message[:300],
            )
            if row:
                DownloadJob.objects.filter(pk=row.pk).update(notification=note)
            return note
    except Exception:
        logger.exception('Could not record the download notification of job %s', job.pk)
        return None


def notify_favorite_event(favorite):
    """
    "<email> favorited N photos". Bursts from the SAME visitor in the same
    gallery roll into one unread notification whose N grows; another visitor's
    favorites never merge into it (the text names who).
    """
    gallery = favorite.gallery
    who = favorite.email or 'A guest'
    prefix = f'{who} favorited '
    try:
        with transaction.atomic():
            existing = (
                Notification.objects.select_for_update()
                .filter(
                    user=gallery.photographer, kind=Kind.FAVORITE, gallery=gallery, is_read=False,
                    updated_at__gte=timezone.now() - COALESCE_WINDOW, message__startswith=prefix,
                )
                .first()
            )
            if existing:
                existing.count += 1
                existing.message = f'{prefix}{existing.count} photos'[:300]
                existing.save(update_fields=['count', 'message', 'updated_at'])
                return existing
    except Exception:
        logger.exception('Could not update favorite notification for gallery %s', gallery.pk)
        return None
    return record_notification(gallery.photographer, Kind.FAVORITE, gallery, message=f'{prefix}1 photo')


def notify_payment_event(payment):
    approved = payment.status == 'approved'
    record_notification(
        payment.user, Kind.PAYMENT, None,
        message=(
            f'Your {payment.plan.name} plan payment was approved — your plan is active'
            if approved else f'Your {payment.plan.name} plan payment could not be approved'
        ),
    )


def notify_staff_feedback(feedback):
    """
    One bell notification per staff account (Django is_staff) for each new
    feedback. Not coalesced: each is a distinct message to triage. The text names
    the category and subject only; the full message stays in the inbox.
    """
    message = f'New {feedback.get_category_display().lower()} feedback: {feedback.subject}'
    created = []
    for staff in User.objects.filter(is_staff=True, is_active=True):
        note = record_notification(staff, Kind.FEEDBACK, None, message=message)
        if note:
            created.append(note)
    return created


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
    if kind == Kind.FEEDBACK:
        return '/dashboard/feedback'
    if kind == Kind.PAYMENT or gallery is None:
        return '/dashboard/billing'
    base = f'/dashboard/galleries/{gallery.slug}'
    if kind == Kind.DOWNLOAD:
        return f'{base}/activities?tab=downloads'
    if kind == Kind.FAVORITE:
        return f'{base}/activities?tab=favorites'
    return base
