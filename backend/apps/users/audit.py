# backend/apps/users/audit.py
"""
The one way to write the staff / security audit log (7.5-A; model: StaffAuditLog).

  record(...)        STRICT. For a staff action: call it inside the same transaction
                     as the change, so a change without its audit row cannot commit.
  record_event(...)  SAFE. For a security event raised inside login, lockout or
                     reset code: a failure to write is logged and swallowed, because
                     the audit must never be the reason a sign-in or a reset breaks.

Never pass a password, PIN, code, token, key or hash: `reason` is a coarse code
("pin", "reset", "admin") or the plain text a staff member typed for a
suspend/reactivate. The address always comes from `apps.core.request_ip.client_ip`
(the trusted-proxy setup of 7-B); there is no parameter that takes a header.
"""
import logging
import re

from django.db import transaction

from apps.core.request_ip import client_ip

from .models import StaffAuditLog

logger = logging.getLogger(__name__)

Action = StaffAuditLog.Action
REASON_MAX = StaffAuditLog._meta.get_field('reason').max_length
_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f-\x9f  ]')


def one_line(text):
    """Plain text on one line: control characters and line breaks become spaces. Not capped."""
    if not isinstance(text, str):
        return ''
    return ' '.join(_CONTROL_CHARS.sub(' ', text).split())


def clean_reason(text):
    """one_line(), capped at REASON_MAX."""
    return one_line(text)[:REASON_MAX]


def record(action, *, actor=None, target=None, request=None, reason=''):
    """Writes one audit row and returns it. `actor` / `target` are User objects (or None)."""
    return StaffAuditLog.objects.create(
        action=action,
        actor_id=getattr(actor, 'pk', None),
        actor_email=getattr(actor, 'email', '') or '',
        target_id=getattr(target, 'pk', None),
        target_email=getattr(target, 'email', '') or '',
        ip=client_ip(request) if request is not None else None,
        reason=clean_reason(reason),
    )


def masked_email(email):
    """`k***@gmail.com`: a non-secret snapshot that tells staff which kind of address it was, not whose."""
    local, _, domain = (email or '').strip().partition('@')
    if not local or not domain:
        return ''
    return f'{local[0]}***@{domain}'


def record_account_event(action, user_id, email, *, reason):
    """
    Account-deletion trail (7.5-E): the account's own id and a MASKED address, a coarse reason code, nothing
    else (no IP, no full address, no name). The id is a plain value, not a foreign key, so the row outlives the
    account without any cascade. Strict like record(): call it inside the transaction of the change.
    """
    return StaffAuditLog.objects.create(
        action=action,
        actor_id=user_id,
        actor_email='',
        target_id=user_id,
        target_email=masked_email(email),
        ip=None,
        reason=clean_reason(reason),
    )


def record_event(action, *, actor=None, target=None, request=None, reason=''):
    """Like record(), but never raises: returns the row, or None when it could not be written."""
    try:
        with transaction.atomic():      # a savepoint: a failed insert must not poison the caller's transaction
            return record(action, actor=actor, target=target, request=request, reason=reason)
    except Exception:
        logger.exception('Could not write the audit row for %s', action)
        return None
