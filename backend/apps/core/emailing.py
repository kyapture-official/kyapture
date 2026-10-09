# backend/apps/core/emailing.py
"""
Transactional email, one place (chunk 7.5-D).

Every email the app sends is one entry of EMAILS and is rendered on ONE base template
(templates/emails/base.html + base.txt): a wordmark, one content slot, a footer with the support
address and, for the emails that belong to a notification preference, a link to the notification
settings page. Nothing here is marketing, and nothing loads from a remote host: no image, no web
font, no tracking pixel.

Rules enforced by construction (tests: apps/core/tests/test_emailing_7_5d.py):

  subject    A fixed string from EMAILS. A caller cannot pass one, so user text (a gallery title, a
             name, a plan name, a reason) and secrets (a code, a token) can never reach a header.
  values     Every string in the context is folded to one line (control characters, CR and LF
             become spaces) and HTML-escaped by the template engine. The text version is rendered
             with autoescape off on purpose: it is text/plain.
  links      Built with app_url() from settings.FRONTEND_URL, never from the request's Host and
             never hard-coded. The caller builds a path (or uses an existing link helper).
  sender     settings.DEFAULT_FROM_EMAIL; Reply-To settings.EMAIL_REPLY_TO (the one exception, the
             "photos are ready" email, passes the photographer's address on purpose).
  dates      Shown in settings.BILLING_TIME_ZONE (Asia/Kathmandu), like the subscription lifecycle.

send_email() raises when the mail backend fails, because its callers are Celery tasks that retry
(or the lifecycle job, which releases its claim). A request thread never calls it, except the
download-code email, which uses safe_send_email() and turns a failure into a 503 answer.
"""
import logging
import re
from dataclasses import dataclass
from email.utils import formataddr, parseaddr
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context
from django.template.loader import get_template, render_to_string

logger = logging.getLogger(__name__)

SITE_NAME = 'Kyapture'
_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f  ]+')
_BLANK_RUNS = re.compile(r'\n{3,}')


@dataclass(frozen=True)
class EmailSpec:
    subject: str                      # fixed text: no placeholder, nothing user-supplied, no secret
    preferences_link: bool = False    # the footer links to the notification settings page


EMAILS = {
    # client visitors (no account): the studio's photos and the one-time download code
    'download_ready': EmailSpec('Your photos are ready for download'),
    'download_code': EmailSpec('Your Kyapture download code'),
    # account security (always sent: no preference applies)
    'password_reset': EmailSpec('Reset your Kyapture password'),
    'password_changed': EmailSpec('Your Kyapture password was changed'),
    # account deletion (7.5-E): always sent, no preference applies
    'deletion_code': EmailSpec('Confirm deleting your Kyapture account'),
    'deletion_requested': EmailSpec('Your Kyapture account is scheduled for deletion'),
    'account_deleted': EmailSpec('Your Kyapture account was deleted'),
    # photographer notification preferences (Settings > Notifications)
    'notify_download': EmailSpec('New download from one of your collections', preferences_link=True),
    'notify_favorite': EmailSpec('New favorite in one of your collections', preferences_link=True),
    'payment_received': EmailSpec('We received your payment', preferences_link=True),
    'payment_approved': EmailSpec('Your payment was approved', preferences_link=True),
    'payment_rejected': EmailSpec('Your payment could not be approved', preferences_link=True),
    'plan_expiring': EmailSpec('Your Kyapture plan is ending soon', preferences_link=True),
    'plan_ended': EmailSpec('Your Kyapture plan has ended', preferences_link=True),
    # staff
    'staff_payment_alert': EmailSpec('New payment to review'),
}


# ─── values ──────────────────────────────────────────────────────────────────

def clean_line(value):
    """One line of text: control characters (CR, LF, tab, NUL, line separators) become spaces."""
    return _CONTROL_CHARS.sub(' ', str(value)).strip()


def clean_context(context):
    """Every string of a flat context folded to one line (a number, bool or None is left alone)."""
    return {key: clean_line(value) if isinstance(value, str) else value for key, value in context.items()}


# ─── links ───────────────────────────────────────────────────────────────────

def app_url(path=''):
    """
    `settings.FRONTEND_URL` + `path`. Raises when FRONTEND_URL is not an absolute http(s) URL, so a
    misconfigured stack fails loudly in the worker instead of mailing a dead link.
    """
    parts = urlsplit(settings.FRONTEND_URL)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise ValueError('FRONTEND_URL is not an absolute http(s) URL')
    return f'{settings.FRONTEND_URL}{path}'


def preferences_url():
    return app_url('/dashboard/settings/notifications')


def billing_url():
    return app_url('/dashboard/billing')


# ─── dates (always in the billing zone) ──────────────────────────────────────

def _billing_tz():
    return ZoneInfo(settings.BILLING_TIME_ZONE)


def format_date(moment):
    """'14 Oct 2026' in BILLING_TIME_ZONE."""
    return f'{moment.astimezone(_billing_tz()):%d %b %Y}'


def format_datetime(moment):
    """'14 Oct 2026, 18:05 (UTC+05:45)' in BILLING_TIME_ZONE."""
    local = moment.astimezone(_billing_tz())
    offset = local.strftime('%z')
    return f'{local:%d %b %Y, %H:%M} (UTC{offset[:3]}:{offset[3:]})'


# ─── render ──────────────────────────────────────────────────────────────────

def render_email(key, context=None):
    """(subject, text, html) of one email. Raises KeyError for a key that is not in EMAILS."""
    spec = EMAILS[key]
    ctx = clean_context(context or {})
    ctx.update({
        'subject': spec.subject,
        'site_name': SITE_NAME,
        'support_email': settings.SUPPORT_EMAIL,
        'preferences_url': preferences_url() if spec.preferences_link else '',
    })
    html = render_to_string(f'emails/{key}.html', ctx)
    # text/plain is rendered with autoescape off (an ampersand must not become &amp;); values were folded above.
    text = get_template(f'emails/{key}.txt').template.render(Context(ctx, autoescape=False))
    text = _BLANK_RUNS.sub('\n\n', text).strip() + '\n'
    return spec.subject, text, html


def reply_to_default():
    address = settings.EMAIL_REPLY_TO or settings.SUPPORT_EMAIL
    return [address] if address else []


def display_from(name):
    """`"Studio Name" <platform address>` for a studio-branded sender; the name is folded to one line."""
    address = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    return formataddr((clean_line(name), address))


def send_email(key, to, context=None, *, from_email=None, reply_to=None):
    """
    Renders and sends one email through the configured backend. Raises if rendering or sending
    fails; the caller (a Celery task, or the lifecycle job) decides whether to retry.
    """
    subject, text, html = render_email(key, context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=[clean_line(to)],
        reply_to=[clean_line(a) for a in (reply_to if reply_to is not None else reply_to_default())],
    )
    message.attach_alternative(html, 'text/html')
    message.send(fail_silently=False)


def safe_send_email(key, to, context=None, **kwargs):
    """send_email() for a request thread: True when handed to the backend, False (and one log line) when not."""
    try:
        send_email(key, to, context, **kwargs)
        return True
    except Exception as exc:                      # logged by type only: no trace, no address, no link
        logger.error('Email %s could not be sent (%s)', key, type(exc).__name__)
        return False
