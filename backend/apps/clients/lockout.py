# backend/apps/clients/lockout.py
"""
Failed-attempt lockout for the two client secrets of a gallery: the gallery
password and the download PIN (7-B, SEC-04 / debt row 81).

The per-address throttle (5/min) alone let one address try ~7,200 PINs a day and
a pool of addresses try them all. On top of it, failures are now counted:

  - per gallery + client address: GATE_CLIENT_MAX_FAILURES wrong values within
    GATE_CLIENT_WINDOW_SECONDS lock that client out of that gate for the window
    (even the right value is refused while locked); a success clears its count.
  - per gallery: GATE_GALLERY_MAX_FAILURES wrong values (from anyone) within
    GATE_GALLERY_WINDOW_SECONDS lock the gate for everyone for that window and
    tell the photographer (bell). This bounds a distributed guess.

Safe reset: every key includes a fingerprint of the stored hash, so changing the
PIN or password (a new bcrypt hash) starts all counts from zero, and nothing has
to be deleted by hand. Counts live in the shared cache (Redis, debt row 108), so
every worker process sees the same numbers.

7F (reviewer F6): a try is COUNTED before the value is checked (begin_attempt,
one atomic cache increment), not after. Before, every request already in flight
when the 5th failure was written had passed check() and got its own guess, so a
burst of parallel requests got far more than 5. Now the 6th of any burst is
refused before bcrypt runs. A third gate, EMAIL_CODE, counts wrong one-time
download codes ("Restrict Downloads to Specific Contacts") the same way.
"""
import hashlib
import math
import time

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response

from apps.core.request_ip import client_ip

PIN = 'pin'
PASSWORD = 'password'
EMAIL_CODE = 'email_code'

_GATE_NOUN = {PIN: 'download PIN', PASSWORD: 'password', EMAIL_CODE: 'download code'}


def _stored_hash(gallery, gate):
    if gate == EMAIL_CODE:
        return ''                           # codes are one-time: there is no secret to change
    return (gallery.download_pin_hash if gate == PIN else gallery.password_hash) or ''


def _prefix(gallery, gate):
    fingerprint = hashlib.sha256(_stored_hash(gallery, gate).encode()).hexdigest()[:12]
    return f'gate:{gate}:{gallery.pk}:{fingerprint}'


def _keys(gallery, gate, request):
    prefix = _prefix(gallery, gate)
    who = client_ip(request) or 'unknown'
    return {
        'client_count': f'{prefix}:c:{who}',
        'client_lock': f'{prefix}:cl:{who}',
        'gallery_count': f'{prefix}:g',
        'gallery_lock': f'{prefix}:gl',
    }


def _count(key, window):
    cache.add(key, 0, timeout=window)
    try:
        return cache.incr(key)
    except ValueError:                      # expired between add and incr
        cache.set(key, 1, timeout=window)
        return 1


def _lock(key, window):
    cache.set(key, time.time() + window, timeout=window)


def _seconds_left(lock_value):
    return max(1, math.ceil(float(lock_value) - time.time()))


def _studio(gallery):
    photographer = gallery.photographer
    return photographer.display_name or photographer.username


def check(gallery, gate, request):
    """A 429 Response when this client (or the whole gate) is locked, else None. Call before checking the value."""
    keys = _keys(gallery, gate, request)
    gallery_lock = cache.get(keys['gallery_lock'])
    if gallery_lock:
        what = 'This gallery is' if gate == PASSWORD else 'Downloads from this gallery are'
        return Response(
            {
                'error': f'{what} paused after too many incorrect {_GATE_NOUN[gate]} attempts. '
                         f'Contact {_studio(gallery)}.',
                'code': 'gallery_locked',
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={'Retry-After': str(_seconds_left(gallery_lock))},
        )
    client_lock = cache.get(keys['client_lock'])
    if client_lock:
        seconds = _seconds_left(client_lock)
        minutes = max(1, math.ceil(seconds / 60))
        return Response(
            {
                'error': f'Too many incorrect attempts. Try again in {minutes} minute{"s" if minutes != 1 else ""}.',
                'code': 'too_many_attempts',
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={'Retry-After': str(seconds)},
        )
    return None


def begin_attempt(gallery, gate, request):
    """
    Counts this try BEFORE the value is checked (one atomic increment) and
    returns a 429 Response when it is over GATE_CLIENT_MAX_FAILURES, else None.
    Call it after check() and right before comparing the value; then call
    record_failure() or record_success(). However many requests arrive at
    once, at most GATE_CLIENT_MAX_FAILURES of them reach the comparison.
    """
    keys = _keys(gallery, gate, request)
    window = settings.GATE_CLIENT_WINDOW_SECONDS
    if _count(keys['client_count'], window) > settings.GATE_CLIENT_MAX_FAILURES:
        cache.add(keys['client_lock'], time.time() + window, timeout=window)
        return check(gallery, gate, request) or Response(
            {'error': 'Too many incorrect attempts. Try again later.', 'code': 'too_many_attempts'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    return None


def record_failure(gallery, gate, request):
    """A wrong value. The client's try was already counted by begin_attempt()."""
    keys = _keys(gallery, gate, request)
    client_window = settings.GATE_CLIENT_WINDOW_SECONDS
    gallery_window = settings.GATE_GALLERY_WINDOW_SECONDS
    if (cache.get(keys['client_count']) or 0) >= settings.GATE_CLIENT_MAX_FAILURES:
        _lock(keys['client_lock'], client_window)
    if _count(keys['gallery_count'], gallery_window) >= settings.GATE_GALLERY_MAX_FAILURES:
        # add() succeeds once per window, so the photographer is told once.
        if cache.add(keys['gallery_lock'], time.time() + gallery_window, timeout=gallery_window):
            cache.delete(keys['gallery_count'])
            _notify_photographer(gallery, gate)


def record_success(gallery, gate, request):
    keys = _keys(gallery, gate, request)
    cache.delete(keys['client_count'])


def _notify_photographer(gallery, gate):
    from apps.users.notification_service import Kind, record_notification
    minutes = settings.GATE_GALLERY_WINDOW_SECONDS // 60
    noun = {PIN: 'download PIN', PASSWORD: 'gallery password', EMAIL_CODE: 'emailed download code'}[gate]
    reset = {PIN: '; changing the PIN unlocks it now.', PASSWORD: '; changing the password unlocks it now.',
             EMAIL_CODE: '.'}[gate]
    record_notification(
        gallery.photographer, Kind.SECURITY, gallery,
        message=(
            f'"{gallery.title}": the {noun} was locked after {settings.GATE_GALLERY_MAX_FAILURES} incorrect '
            f'attempts. It unlocks by itself in {minutes} minutes{reset}'
        ),
    )
