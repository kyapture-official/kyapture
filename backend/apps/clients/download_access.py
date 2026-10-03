# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/download_access.py
"""
Server-side download authorization for the public client gallery.

Gallery password and download PIN are two separate gates (see
Gallery.download_pin_hash). Opening/browsing a gallery needs only the gallery
password (when set); an actual download additionally needs the PIN (when set).
This module owns the second gate and the short-lived "download access token"
that lets a client avoid re-entering email/PIN for every photo.

The token is a Django-signed (HMAC), time-limited blob — not a database row
and not a bearer secret that outlives its purpose:

  - bound to ONE gallery (a token for gallery A never authorizes gallery B)
  - bound to a fingerprint of the gallery's current PIN hash, so changing or
    clearing the PIN invalidates every outstanding token
  - expires after DOWNLOAD_ACCESS_TTL_SECONDS (default 2 hours)
  - never replaces the gallery-password session: a password-protected gallery
    still requires its own unlock token on every download request
"""
import hashlib
import logging

import bcrypt
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

DOWNLOAD_TOKEN_SALT = 'kyapture.clients.download-access'
FILE_TOKEN_SALT = 'kyapture.clients.download-job-file'
DEFAULT_DOWNLOAD_ACCESS_TTL_SECONDS = 2 * 60 * 60
DOWNLOAD_RESOLUTIONS = ('download', 'web')


def get_download_policy(gallery):
    """Return the small, validated public-download policy for a gallery.

    The policy lives under ``Gallery.design_settings.downloads`` so it travels
    with the collection's other photographer-controlled settings.  Existing
    galleries that predate it deliberately default to email-required and both
    safe client sizes: permissive downloads must be an explicit choice.
    """
    design_settings = gallery.design_settings if isinstance(gallery.design_settings, dict) else {}
    raw_policy = design_settings.get('downloads')
    raw_policy = raw_policy if isinstance(raw_policy, dict) else {}

    raw_sizes = raw_policy.get('allowed_sizes')
    allowed_sizes = [
        size for size in raw_sizes
        if isinstance(size, str) and size in DOWNLOAD_RESOLUTIONS
    ] if isinstance(raw_sizes, list) else list(DOWNLOAD_RESOLUTIONS)
    if not allowed_sizes:
        # Invalid historic JSON must never silently leave a live gallery with
        # no predictable policy. Serializer validation prevents new bad data.
        allowed_sizes = list(DOWNLOAD_RESOLUTIONS)

    return {
        'allowed_sizes': allowed_sizes,
        'require_email': raw_policy.get('require_email') is not False,
    }


def download_access_required(gallery):
    """Whether a browser must earn a short-lived download token first."""
    return get_download_policy(gallery)['require_email'] or bool(gallery.download_pin_hash)


def resolution_is_allowed(gallery, resolution):
    """Apply the photographer's public-size choice to every download URL.

    ``original`` remains a legacy API value, but is governed by the same
    High Resolution switch as the Download Master. It is never offered by the
    client UI and cannot bypass a photographer who disabled High Resolution.
    """
    policy_resolution = 'download' if resolution == 'original' else resolution
    return policy_resolution in get_download_policy(gallery)['allowed_sizes']
MAX_EMAIL_LENGTH = 254


def download_access_ttl():
    return int(getattr(settings, 'DOWNLOAD_ACCESS_TTL_SECONDS', DEFAULT_DOWNLOAD_ACCESS_TTL_SECONDS))


def as_clean_str(value):
    """
    Request bodies are untrusted JSON: a field may be null, a number or a
    list. Returns a stripped string for str/int input and '' for anything
    else, so a malformed value yields a clean 4xx instead of an
    AttributeError/500.
    """
    if isinstance(value, bool):
        return ''
    if isinstance(value, (str, int)):
        return str(value).strip()
    return ''


def error_response(message, code, http_status):
    """The project's existing error shape: {'error': <message>, 'code': <slug>}."""
    return Response({'error': message, 'code': code}, status=http_status)


def validate_client_email(raw_email):
    """Returns (email, error_response). A missing/malformed email is a 400."""
    email = as_clean_str(raw_email)
    if not email:
        return None, error_response(
            'A valid email address is required to download.', 'email_required',
            status.HTTP_400_BAD_REQUEST,
        )
    try:
        if len(email) > MAX_EMAIL_LENGTH:
            raise ValidationError('too long')
        validate_email(email)
    except ValidationError:
        return None, error_response(
            'Please enter a valid email address.', 'invalid_email',
            status.HTTP_400_BAD_REQUEST,
        )
    return email, None


def verify_pin(gallery, raw_pin):
    """Constant-time bcrypt check of a client-supplied PIN against the gallery's hash."""
    pin = as_clean_str(raw_pin)
    if not pin or not gallery.download_pin_hash:
        return False
    try:
        return bcrypt.checkpw(pin.encode('utf-8'), gallery.download_pin_hash.encode('utf-8'))
    except Exception:
        return False


def _pin_fingerprint(gallery):
    if not gallery.download_pin_hash:
        return ''
    return hashlib.sha256(gallery.download_pin_hash.encode('utf-8')).hexdigest()[:16]


def issue_download_token(gallery, email, pin_verified):
    return signing.dumps(
        {
            'g': str(gallery.id),
            'e': email or '',
            'p': bool(pin_verified),
            'f': _pin_fingerprint(gallery),
        },
        salt=DOWNLOAD_TOKEN_SALT,
        compress=True,
    )


def read_download_token(token, gallery):
    """Returns the token payload if it is genuine, fresh and for THIS gallery; else None."""
    token = as_clean_str(token)
    if not token:
        return None
    try:
        payload = signing.loads(token, salt=DOWNLOAD_TOKEN_SALT, max_age=download_access_ttl())
    except signing.BadSignature:  # includes SignatureExpired
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get('g') != str(gallery.id):
        return None
    # PIN changed, cleared, or newly set since this token was issued.
    if payload.get('f') != _pin_fingerprint(gallery):
        return None
    # A gallery that now has a PIN only honors tokens that actually passed it.
    if gallery.download_pin_hash and not payload.get('p'):
        return None
    if get_download_policy(gallery)['require_email'] and not payload.get('e'):
        return None
    return payload


def download_file_url_ttl():
    return int(getattr(settings, 'DOWNLOAD_FILE_URL_TTL_SECONDS', 600))


def issue_file_token(job, gallery, index):
    """
    Short-lived signed grant for ONE file of ONE prepared download job.

    Minted only by the job-status endpoint, i.e. only for a caller that just
    presented a valid download access token, so it is tied to that verified
    visitor: it carries the job, the gallery, the file index, the verified
    email and the PIN fingerprint, and the file endpoint re-checks all of
    them. It expires in minutes (DOWNLOAD_FILE_URL_TTL_SECONDS) — long before
    the access token itself — so a link copied out of the address bar or a
    history entry stops working almost immediately.
    """
    return signing.dumps(
        {
            'j': str(job.id),
            'g': str(gallery.id),
            'i': int(index),
            'e': job.email or '',
            'f': _pin_fingerprint(gallery),
        },
        salt=FILE_TOKEN_SALT,
        compress=True,
    )


def file_token_is_valid(token, job, gallery, index):
    token = as_clean_str(token)
    if not token:
        return False
    try:
        payload = signing.loads(token, salt=FILE_TOKEN_SALT, max_age=download_file_url_ttl())
    except signing.BadSignature:  # includes SignatureExpired
        return False
    return (
        isinstance(payload, dict)
        and payload.get('j') == str(job.id)
        and payload.get('g') == str(gallery.id)
        and payload.get('i') == int(index)
        and payload.get('e') == (job.email or '')
        # PIN changed or cleared since the grant was issued.
        and payload.get('f') == _pin_fingerprint(gallery)
    )


class DownloadAuthorization:
    """Outcome of a passed download gate: who (email) and whether a PIN was verified."""

    def __init__(self, pin_verified=False, email=None):
        self.pin_verified = pin_verified
        self.email = email


def authorize_download(gallery, *, pin, download_token, denied_status=status.HTTP_401_UNAUTHORIZED):
    """
    The single download gate shared by every public download endpoint
    (single file, ZIP POST, direct ZIP GET). Call it AFTER the gallery,
    allow_download and gallery-password checks.

    A valid download access token is mandatory whenever the gallery requires
    an email or PIN. A presented-but-invalid token is rejected outright rather
    than silently downgraded, so an expired session makes the client
    re-authorize instead of quietly losing its email in the activity log.

    Returns (DownloadAuthorization | None, error Response | None).
    """
    if as_clean_str(download_token):
        payload = read_download_token(download_token, gallery)
        if payload is None:
            return None, error_response(
                'Your download session has expired. Please try again.',
                'download_access_expired', denied_status,
            )
        return DownloadAuthorization(
            pin_verified=bool(payload.get('p')),
            email=payload.get('e') or None,
        ), None

    if not download_access_required(gallery):
        return DownloadAuthorization(), None
    return None, error_response(
        'Confirm your download details before downloading.', 'download_access_required', denied_status,
    )
