# backend/apps/clients/ready_email.py
"""
The "your photos are ready for download" email (Task 1R.5-C).

Sent by the `send_download_ready_email` Celery task once a DownloadJob is READY,
to the visitor who asked for it, at most once per job:

    From     "{studio name}" <the platform's sending address>   (display name only)
    Reply-To the photographer's email, so "Questions? Reply to this email." works
    Link     Page 4 of the download flow, /g/{user}/{slug}/download/file/{job}?key=...,
             an absolute URL on settings.FRONTEND_URL (the public app origin)

Abuse control: at most DOWNLOAD_READY_EMAIL_LIMIT_PER_* sends per hour for one
recipient address, one requesting IP and one gallery. Over a limit the email is
skipped silently -- the prepare/status endpoints answer exactly as before, so
nothing reveals whether an address is valid, deliverable or throttled. A failure
to send is logged and never touches the job.
"""
import logging
import re
from datetime import timedelta
from email.utils import formataddr, parseaddr
from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from apps.core.request_ip import client_ip

from apps.core.share import build_gallery_share_url

from .download_access import issue_job_link_token
from .models import DownloadJob

logger = logging.getLogger(__name__)

LINK_DAYS = 7
_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f]+')


def requester_ip(request):
    """The visitor's IP as DRF's throttles see it (honours NUM_PROXIES), or None when it is not a valid address."""
    return client_ip(request)


def studio_name(gallery):
    photographer = gallery.photographer
    return _CONTROL_CHARS.sub(' ', photographer.display_name or photographer.username).strip() or photographer.username


def job_page_url(job):
    """Absolute link to Page 4 for this job; '' when the app origin is not a usable absolute URL."""
    gallery = job.gallery
    base = build_gallery_share_url(gallery)
    parts = urlsplit(base)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        return ''
    return f'{base}/download/file/{job.id}?key={issue_job_link_token(job, gallery)}'


def build_ready_email(job):
    """The (subject, text body, html body, from header, reply-to) of the email for `job`."""
    gallery = job.gallery
    studio = studio_name(gallery)
    context = {
        'studio': studio,
        'gallery_title': gallery.title,
        'download_url': job_page_url(job),
        'gallery_url': build_gallery_share_url(gallery),
        'days': LINK_DAYS,
    }
    from_address = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    return {
        'subject': _CONTROL_CHARS.sub(' ', f'Your Photos for {gallery.title} are ready for download').strip(),
        'text': render_to_string('clients/emails/download_ready.txt', context),
        'html': render_to_string('clients/emails/download_ready.html', context),
        'from_email': formataddr((studio, from_address)),
        'reply_to': [gallery.photographer.email],
        'download_url': context['download_url'],
    }


def over_limit(job):
    """Which hourly send limit (if any) this job's email would exceed: 'email' | 'ip' | 'gallery' | None."""
    since = timezone.now() - timedelta(seconds=settings.DOWNLOAD_READY_EMAIL_WINDOW_SECONDS)
    sent = DownloadJob.objects.filter(ready_email_sent_at__gte=since).exclude(pk=job.pk)
    checks = [
        ('email', sent.filter(email__iexact=job.email), settings.DOWNLOAD_READY_EMAIL_LIMIT_PER_EMAIL),
        ('gallery', sent.filter(gallery_id=job.gallery_id), settings.DOWNLOAD_READY_EMAIL_LIMIT_PER_GALLERY),
    ]
    if job.requester_ip:
        checks.append(('ip', sent.filter(requester_ip=job.requester_ip), settings.DOWNLOAD_READY_EMAIL_LIMIT_PER_IP))
    for name, queryset, limit in checks:
        if queryset.count() >= limit:
            return name
    return None


def deliver_ready_email(job_id):
    """
    Task body. Returns True when an email was handed to the mail backend, False
    when it was skipped (no recipient, not ready, already sent, rate-limited) or
    failed. Never raises. Every outcome is one INFO line ("Download-ready email
    for job <id>: sent | skipped (<reason>) | failed"); the "queued" line comes
    from download_jobs.send_ready_email.
    """
    try:
        job = DownloadJob.objects.select_related('gallery__photographer').filter(pk=job_id).first()
        if job is None:
            logger.info('Download-ready email for job %s: skipped (job not found)', job_id)
            return False
        if not job.email:
            logger.info('Download-ready email for job %s: skipped (no email)', job.id)
            return False
        if job.state != DownloadJob.State.READY:
            logger.info('Download-ready email for job %s: skipped (job not ready)', job.id)
            return False
        if job.ready_email_sent_at is not None:
            logger.info('Download-ready email for job %s: skipped (already sent)', job.id)
            return False
        limit = over_limit(job)
        if limit:
            logger.info('Download-ready email for job %s: skipped (%s rate limit)', job.id, limit)
            return False
        # Claim the job first: of two racing runs only one updates a row.
        claimed = DownloadJob.objects.filter(pk=job.pk, ready_email_sent_at__isnull=True).update(
            ready_email_sent_at=timezone.now()
        )
        if not claimed:
            logger.info('Download-ready email for job %s: skipped (already sent)', job.id)
            return False
        try:
            mail = build_ready_email(job)
            if not mail['download_url']:
                raise ValueError('FRONTEND_URL is not an absolute http(s) URL')
            message = EmailMultiAlternatives(
                subject=mail['subject'], body=mail['text'], from_email=mail['from_email'],
                to=[job.email], reply_to=mail['reply_to'],
            )
            message.attach_alternative(mail['html'], 'text/html')
            message.send(fail_silently=False)
        except Exception:
            DownloadJob.objects.filter(pk=job.pk).update(ready_email_sent_at=None)
            raise
        logger.info('Download-ready email for job %s: sent', job.id)
        return True
    except Exception:
        logger.exception('Download-ready email for job %s: failed', job_id)
        return False
