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
JOB_LINK_SALT = 'kyapture.clients.download-job-link'
DEFAULT_DOWNLOAD_ACCESS_TTL_SECONDS = 2 * 60 * 60
DOWNLOAD_RESOLUTIONS = ('download', 'web')


def _effective_downloads(gallery):
    """
    Read-time view of ``Gallery.design_settings.downloads`` with every
    1R.6 key defaulted for a gallery saved before it existed — including
    one storing only the original Task 1R.4 shape ({allowed_sizes,
    require_email}). Never raises: a malformed/corrupt stored value
    degrades to the same safe defaults the serializer itself falls back
    to (apps/galleries/serializers.py::normalize_download_settings),
    never a blank/crashed response.
    """
    design_settings = gallery.design_settings if isinstance(gallery.design_settings, dict) else {}
    raw = design_settings.get('downloads')
    raw = raw if isinstance(raw, dict) else {}

    raw_sizes = raw.get('allowed_sizes')
    legacy_sizes = [
        size for size in raw_sizes if isinstance(size, str) and size in DOWNLOAD_RESOLUTIONS
    ] if isinstance(raw_sizes, list) else None

    high_res = raw.get('high_res') if isinstance(raw.get('high_res'), dict) else {}
    web = raw.get('web') if isinstance(raw.get('web'), dict) else {}

    high_res_enabled = high_res.get('enabled')
    if not isinstance(high_res_enabled, bool):
        high_res_enabled = 'download' in legacy_sizes if legacy_sizes is not None else True
    web_enabled = web.get('enabled')
    if not isinstance(web_enabled, bool):
        web_enabled = 'web' in legacy_sizes if legacy_sizes is not None else True

    allowed_sizes = (['download'] if high_res_enabled else []) + (['web'] if web_enabled else [])
    if not allowed_sizes:
        # Invalid historic JSON must never silently leave a live gallery with
        # no predictable policy. Serializer validation prevents new bad data.
        allowed_sizes = list(DOWNLOAD_RESOLUTIONS)

    mode = high_res.get('mode')
    if mode not in ('3600', 'original'):
        mode = '3600'
    px = web.get('px')
    if px == 1280:  # pre-1R.6-B value for the same medium tier
        px = 1024
    if px not in (2048, 1024, 640):
        px = 2048

    sets_enabled = raw.get('sets_enabled')
    if not (isinstance(sets_enabled, list) and all(isinstance(s, str) for s in sets_enabled)):
        sets_enabled = None

    limit_total = raw.get('limit_total')
    if isinstance(limit_total, bool) or not isinstance(limit_total, int) or limit_total < 1:
        limit_total = None

    allowed_emails = raw.get('allowed_emails')
    allowed_emails = (
        [e.strip().lower() for e in allowed_emails if isinstance(e, str) and e.strip()]
        if isinstance(allowed_emails, list) else []
    )

    return {
        'allowed_sizes': allowed_sizes,
        'require_email': raw.get('require_email') is not False,
        'high_res_enabled': high_res_enabled,
        'high_res_mode': mode,
        'web_enabled': web_enabled,
        'web_px': px,
        'sets_enabled': sets_enabled,
        'limit_total': limit_total,
        'restrict_contacts': bool(raw.get('restrict_contacts', False)),
        'allowed_emails': allowed_emails,
        # 1R.6-A: the Download tab's PIN toggle. Missing = on, so a gallery
        # that already has a PIN keeps enforcing it. Off never deletes the
        # stored hash -- it only stops enforcement.
        'pin_enabled': raw.get('pin_enabled') is not False,
    }


def download_pin_enforced(gallery):
    """
    The ONE definition of "this gallery's download PIN is active": a PIN
    hash is saved AND the Download-tab toggle is not Off. Turning the toggle
    On without saving a PIN enforces nothing.
    """
    return bool(gallery.download_pin_hash) and _effective_downloads(gallery)['pin_enabled']


def get_download_policy(gallery):
    """
    Return the small, PUBLIC-safe download policy for a gallery — read by
    the client gallery payload (apps/clients/serializers.py) to decide
    what the "Choose Photos" / "Choose Download Size" pickers show.

    Deliberately excludes anything private: limit_total, restrict_contacts,
    allowed_emails (the email allow-list must never be revealed to a
    visitor) and the raw high_res mode (a client only ever sees "High
    Resolution" — which bytes that resolves to is a server decision, see
    effective_high_res_mode() below).
    """
    eff = _effective_downloads(gallery)
    return {
        'allowed_sizes': eff['allowed_sizes'],
        # Also effectively required whenever "Restrict Downloads to
        # Specific Contacts" is on -- the allow-list can't be checked
        # without an email to check it against, and this is the client's
        # only signal to show that field. The contact list itself is
        # still never exposed here or anywhere else public.
        'require_email': eff['require_email'] or eff['restrict_contacts'],
        # null = every set may be downloaded (the default); otherwise the
        # client filters its set picker to just these ids.
        'sets_enabled': eff['sets_enabled'],
        'web_px': eff['web_px'],
        # Only the yes/no -- never the limit or the running total -- so the
        # download pages can show "Download limit reached" up front.
        'limit_reached': download_limit_reached(gallery),
    }


def download_access_required(gallery):
    """Whether a browser must earn a short-lived download token first."""
    eff = _effective_downloads(gallery)
    return eff['require_email'] or download_pin_enforced(gallery) or eff['restrict_contacts']


def resolution_is_allowed(gallery, resolution):
    """
    Apply the photographer's public-size choice. Only 'web' and 'download'
    are ever accepted from a client — apps/clients/views.py::
    _validate_download_resolution rejects a raw resolution=original
    outright (400) before this is ever reached, so there is no legacy
    'original' mapping here any more: an 'original' that somehow arrives
    resolves to a policy key that is never in allowed_sizes and is simply
    denied. 'download' is the single "High Resolution" choice offered to
    clients; which bytes it actually resolves to (the 3600px Download
    Master, or the true original for an entitled Pro photographer who
    chose it) is decided at serve time by effective_high_res_mode() below
    — never by the client.
    """
    return resolution in get_download_policy(gallery)['allowed_sizes']


def effective_high_res_mode(gallery):
    """
    'original' only when the photographer chose it AND currently holds
    the Pro+ Original-download entitlement; otherwise (Free, or a lapsed
    Pro) falls back to '3600' automatically. Never mutates the stored
    design_settings.downloads.high_res.mode — only the EFFECTIVE mode used
    for THIS request falls back, exactly like watermark/branding lapsing.
    """
    eff = _effective_downloads(gallery)
    if eff['high_res_mode'] != 'original':
        return '3600'
    from apps.subscriptions.entitlements import ORIGINAL_DOWNLOAD, has_feature
    return 'original' if has_feature(gallery.photographer, ORIGINAL_DOWNLOAD) else '3600'


def web_px_for_gallery(gallery):
    return _effective_downloads(gallery)['web_px']


def set_is_enabled_for_download(gallery, photo_set):
    """
    Whether a download covering `photo_set` (None = the whole gallery) is
    allowed under "Photo Sets Available for Download". sets_enabled=None
    (the default) means every set, and the whole gallery, may be
    downloaded. Once restricted to a subset, a whole-gallery download is
    refused outright rather than silently shipping a partial ZIP that
    drops the disabled sets' photos without being asked to.
    """
    sets_enabled = _effective_downloads(gallery)['sets_enabled']
    if sets_enabled is None:
        return True
    if photo_set is None:
        return False
    return str(photo_set.id) in sets_enabled


def asset_set_is_enabled_for_download(gallery, asset):
    """Same gate as set_is_enabled_for_download, for a single-photo/video download."""
    sets_enabled = _effective_downloads(gallery)['sets_enabled']
    if sets_enabled is None:
        return True
    return asset.photo_set_id is not None and str(asset.photo_set_id) in sets_enabled


def email_is_allowed(gallery, email):
    """"Restrict Downloads to Specific Contacts" — true whenever the gate is off."""
    eff = _effective_downloads(gallery)
    if not eff['restrict_contacts']:
        return True
    return bool(email) and email.strip().lower() in eff['allowed_emails']


def download_limit_reached(gallery):
    """
    "Limit Photo Downloads" (total, shared by all visitors), counted in
    PHOTOS: each DownloadLog row (one per prepared ZIP actually served, one
    per single-photo/video GET) counts its photo_count, or 1 when that is
    unknown (a single file, or a row written before photo_count existed).
    The same rows back the photographer's Download Activity feed, so there is
    no separate counter to keep in sync. Once the total has reached the limit
    nothing new starts; a ZIP that started below it is allowed to finish.
    """
    limit_total = _effective_downloads(gallery)['limit_total']
    if not limit_total:
        return False
    from django.db.models import Sum
    from django.db.models.functions import Coalesce
    from .models import DownloadLog
    used = DownloadLog.objects.filter(gallery=gallery).aggregate(
        total=Sum(Coalesce('photo_count', 1))
    )['total'] or 0
    return used >= limit_total


def pin_limit_reached(gallery):
    """"Limit PIN Usage" (Privacy tab, Advanced). None/0 = unlimited."""
    design_settings = gallery.design_settings if isinstance(gallery.design_settings, dict) else {}
    privacy = design_settings.get('privacy') if isinstance(design_settings.get('privacy'), dict) else {}
    limit = privacy.get('pin_limit')
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return False
    count = privacy.get('pin_use_count', 0)
    count = count if isinstance(count, int) and not isinstance(count, bool) else 0
    return count >= limit


def record_pin_use(gallery):
    """
    One successful PIN verification used up — incremented only at the one
    place a PIN is actually checked against the client-supplied value
    (PublicDownloadAccessView), never when a previously-issued download
    token merely carries an earlier verification forward.
    """
    design_settings = dict(gallery.design_settings or {})
    privacy = dict(design_settings.get('privacy') or {})
    count = privacy.get('pin_use_count', 0)
    count = count if isinstance(count, int) and not isinstance(count, bool) else 0
    privacy['pin_use_count'] = count + 1
    design_settings['privacy'] = privacy
    gallery.design_settings = design_settings
    gallery.save(update_fields=['design_settings'])


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
    if not pin or not download_pin_enforced(gallery):
        return False
    try:
        return bcrypt.checkpw(pin.encode('utf-8'), gallery.download_pin_hash.encode('utf-8'))
    except Exception:
        return False


def _pin_fingerprint(gallery):
    # Not enforced (no PIN, or toggled Off) fingerprints as '' so flipping
    # the toggle invalidates every outstanding token, like changing the PIN.
    if not download_pin_enforced(gallery):
        return ''
    return hashlib.sha256(gallery.download_pin_hash.encode('utf-8')).hexdigest()[:16]


def _password_fingerprint(gallery):
    # The emailed ready link and its file links skip the unlock session, so
    # they carry the password they were issued under: a new password (or a
    # password added later) ends them, like it ends every unlock session.
    if not gallery.is_password_protected or not gallery.password_hash:
        return ''
    return hashlib.sha256(gallery.password_hash.encode('utf-8')).hexdigest()[:16]


def _gates_unchanged(payload, gallery):
    """7-A: a grant that bypasses the unlock session never outlives a password or PIN change."""
    if gallery.is_password_protected and payload.get('w', '') != _password_fingerprint(gallery):
        return False
    if download_pin_enforced(gallery) and payload.get('f', '') != _pin_fingerprint(gallery):
        return False
    return True


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
    if download_pin_enforced(gallery) and not payload.get('p'):
        return None
    if get_download_policy(gallery)['require_email'] and not payload.get('e'):
        return None
    # "Restrict Downloads to Specific Contacts": a contact removed from the
    # list after their token was issued loses access immediately.
    if not email_is_allowed(gallery, payload.get('e')):
        return None
    return payload


def issue_job_link_token(job, gallery):
    """
    The key in the "your photos are ready" link (/download/file/{job}?key=...).
    Bound to ONE job of ONE gallery and nothing else: it carries no email and
    no PIN, never authorizes another job, and is only ever handed out by the
    authorized prepare POST (or the ready email built from that job). It does
    not expire on its own -- the job does (job.expires_at, then the purge) --
    but it does end when the photographer changes the gallery password or the
    download PIN (fingerprints 'w' / 'f', see _gates_unchanged).
    """
    return signing.dumps(
        {'j': str(job.id), 'g': str(gallery.id), 'w': _password_fingerprint(gallery), 'f': _pin_fingerprint(gallery)},
        salt=JOB_LINK_SALT, compress=True,
    )


def job_link_token_is_valid(token, job, gallery):
    token = as_clean_str(token)
    if not token:
        return False
    try:
        payload = signing.loads(token, salt=JOB_LINK_SALT)
    except signing.BadSignature:
        return False
    return (
        isinstance(payload, dict)
        and payload.get('j') == str(job.id)
        and payload.get('g') == str(gallery.id)
        and _gates_unchanged(payload, gallery)
    )


def download_file_url_ttl():
    return int(getattr(settings, 'DOWNLOAD_FILE_URL_TTL_SECONDS', 600))


def issue_file_token(job, gallery, index):
    """
    Short-lived signed grant for ONE file of ONE prepared download job.

    Minted only by the job-status endpoint, i.e. only for a caller that just
    presented a valid download access token, so it is tied to that verified
    visitor: it carries the job, the gallery, the file index, the verified
    email and the PIN fingerprint, and the file endpoint re-checks all of
    them. It expires after DOWNLOAD_FILE_URL_TTL_SECONDS (1 hour since 7-B;
    the ready page fetches a fresh one per click) and works for that one job only.
    """
    return signing.dumps(
        {
            'j': str(job.id),
            'g': str(gallery.id),
            'i': int(index),
            'e': job.email or '',
            'f': _pin_fingerprint(gallery),
            'w': _password_fingerprint(gallery),
        },
        salt=FILE_TOKEN_SALT,
        compress=True,
    )


def file_token_state(token, job, gallery, index):
    """
    'ok'        genuine, fresh and issued for exactly this job/gallery/file
    'mismatch'  genuine but issued for ANOTHER job, gallery, file or visitor
    'expired'   genuine but past DOWNLOAD_FILE_URL_TTL_SECONDS
    'invalid'   missing, malformed or tampered
    """
    token = as_clean_str(token)
    if not token:
        return 'invalid'
    try:
        payload = signing.loads(token, salt=FILE_TOKEN_SALT, max_age=download_file_url_ttl())
    except signing.SignatureExpired:
        return 'expired'
    except signing.BadSignature:
        return 'invalid'
    if not isinstance(payload, dict):
        return 'invalid'
    if (
        payload.get('j') != str(job.id)
        or payload.get('g') != str(gallery.id)
        or payload.get('i') != int(index)
        or payload.get('e') != (job.email or '')
    ):
        return 'mismatch'
    # PIN changed or cleared since the grant was issued.
    if payload.get('f') != _pin_fingerprint(gallery):
        return 'invalid'
    # Gallery password changed (or added) since the grant was issued.
    if not _gates_unchanged(payload, gallery):
        return 'invalid'
    # A contact removed from the allow-list no longer holds a working link.
    if not email_is_allowed(gallery, job.email):
        return 'invalid'
    return 'ok'


def file_token_is_valid(token, job, gallery, index):
    return file_token_state(token, job, gallery, index) == 'ok'


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


# ─── "Restrict Downloads to Specific Contacts": prove the address (7-B, row 80) ─
# The allow-list used to trust a typed email, so anyone who knew one listed
# address got that contact's downloads. Now an allowed address first receives a
# one-time 6-digit code by email; only the code earns a download token. The code
# lives in the shared cache as a hash, for EMAIL_CODE_TTL_SECONDS, and dies after
# EMAIL_CODE_MAX_TRIES wrong entries; at most EMAIL_CODE_MAX_SENDS codes are sent
# to one address for one gallery per TTL (no mail-bombing through the form).
EMAIL_CODE_TTL_SECONDS = 10 * 60
EMAIL_CODE_MAX_TRIES = 5
EMAIL_CODE_MAX_SENDS = 3


def contacts_restricted(gallery):
    return _effective_downloads(gallery)['restrict_contacts']


def _email_code_key(gallery, email):
    digest = hashlib.sha256(email.strip().lower().encode('utf-8')).hexdigest()
    return f'dlcode:{gallery.pk}:{digest}'


def _code_digest(code):
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


def send_email_code(gallery, email):
    """
    Emails a new one-time code to `email`. Returns 'sent', 'too_many' (send limit
    for this address and gallery reached) or 'failed' (mail could not be sent).
    """
    import re
    import secrets

    from django.core.cache import cache
    from django.core.mail import send_mail

    key = _email_code_key(gallery, email)
    sends_key = f'{key}:sends'
    cache.add(sends_key, 0, timeout=EMAIL_CODE_TTL_SECONDS)
    if cache.incr(sends_key) > EMAIL_CODE_MAX_SENDS:
        return 'too_many'
    code = f'{secrets.randbelow(10 ** 6):06d}'
    cache.set(key, {'h': _code_digest(code), 'tries': 0}, timeout=EMAIL_CODE_TTL_SECONDS)
    photographer = gallery.photographer
    studio = re.sub(r'[\x00-\x1f\x7f]+', ' ', photographer.display_name or photographer.username).strip()
    title = re.sub(r'[\x00-\x1f\x7f]+', ' ', gallery.title).strip()
    minutes = EMAIL_CODE_TTL_SECONDS // 60
    try:
        send_mail(
            f'Your download code: {code}',
            (
                f'Your code to download photos from "{title}" by {studio} is:\n\n    {code}\n\n'
                f'It works for {minutes} minutes. If you did not ask to download these photos, '
                'you can ignore this email.\n'
            ),
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )
    except Exception:
        logger.exception('Download code email could not be sent for gallery %s', gallery.pk)
        cache.delete(key)
        return 'failed'
    return 'sent'


def check_email_code(gallery, email, code):
    """True once for the right, fresh code for this address and gallery (it is then used up)."""
    from django.core.cache import cache
    from django.utils.crypto import constant_time_compare

    code = as_clean_str(code)
    key = _email_code_key(gallery, email)
    entry = cache.get(key)
    if not code or not isinstance(entry, dict):
        return False
    if entry.get('tries', 0) >= EMAIL_CODE_MAX_TRIES:
        cache.delete(key)
        return False
    if constant_time_compare(_code_digest(code), entry.get('h', '')):
        cache.delete(key)
        cache.delete(f'{key}:sends')
        return True
    entry['tries'] = entry.get('tries', 0) + 1
    cache.set(key, entry, timeout=EMAIL_CODE_TTL_SECONDS)
    return False
