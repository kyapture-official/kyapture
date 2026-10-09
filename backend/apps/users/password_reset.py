# backend/apps/users/password_reset.py
"""
"Forgot password" links (7-C).

A link is `{FRONTEND_URL}/reset-password#token=<43 url-safe chars>` (256 random
bits). The token sits in the URL fragment, so a browser never sends it to any
server, not even ours (no access log, no Referer); the reset page reads it once,
removes it from the address bar and history, and POSTs it in a JSON body.

Only its SHA-256 is stored (PasswordResetToken). The link host comes from the
FRONTEND_URL setting, never from the request's Host / X-Forwarded-Host headers,
so a forged header cannot point the emailed link at another site.

Nothing here logs a token, a link or a password.
"""
import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.emailing import app_url, format_datetime, send_email

logger = logging.getLogger(__name__)

TOKEN_BYTES = 32
TOKEN_MAX_LENGTH = 128   # anything longer is not one of ours; refused before hashing


def hash_token(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def reset_link(raw):
    return app_url(f'/reset-password#token={raw}')


def issue_token(user):
    """
    A new raw token for `user`. Every older link of this account stops working
    (only the newest link is valid), and expired links of every account are
    purged on the way (the table holds live links only).
    """
    from .models import PasswordResetToken

    now = timezone.now()
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    with transaction.atomic():
        PasswordResetToken.objects.filter(user=user).delete()
        PasswordResetToken.objects.filter(expires_at__lte=now).delete()
        PasswordResetToken.objects.create(
            user=user,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_MINUTES),
        )
    return raw


def live_token_queryset(raw):
    """The (0 or 1) usable row for a raw token: right hash, not expired, active account."""
    from .models import PasswordResetToken

    if not isinstance(raw, str) or not raw or len(raw) > TOKEN_MAX_LENGTH:
        return PasswordResetToken.objects.none()
    return PasswordResetToken.objects.filter(
        token_hash=hash_token(raw), expires_at__gt=timezone.now(), user__is_active=True,
    )


def send_reset_email(email):
    """
    Task body: emails a reset link when `email` belongs to an active account,
    and does nothing otherwise. Runs in the Celery worker, so the API request
    does exactly the same work (and takes the same time) for any address.
    """
    from .models import User

    user = User.objects.filter(email=email, is_active=True).first()
    if user is None:
        return False
    raw = issue_token(user)
    context = {
        'display_name': user.display_name or user.username,
        'reset_url': reset_link(raw),
        'minutes': settings.PASSWORD_RESET_TOKEN_MINUTES,
    }
    send_email('password_reset', user.email, context)
    logger.info('Password reset email sent for user_id=%s', user.pk)
    return True


def send_password_changed_email(user_id, how):
    """Task body: tells the account owner that the password changed (`how`: 'reset', 'change' or 'admin')."""
    from .models import User

    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return False
    context = {
        'display_name': user.display_name or user.username,
        'email': user.email,
        'when': format_datetime(timezone.now()),
        'via_reset': how == 'reset',
        'by_staff': how == 'admin',
        'forgot_url': app_url('/forgot-password'),
    }
    send_email('password_changed', user.email, context)
    logger.info('Password changed email sent for user_id=%s', user.pk)
    return True


def queue_password_changed_email(user, how):
    """After the surrounding transaction commits; a broker failure never fails the password change."""
    from .tasks import send_password_changed_email_task

    user_id = str(user.pk)

    def dispatch():
        try:
            send_password_changed_email_task.delay(user_id, how)
        except Exception:
            logger.exception('Could not queue the password changed email for user_id=%s', user_id)

    transaction.on_commit(dispatch)
