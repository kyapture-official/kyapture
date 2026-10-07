# backend/apps/core/admin_login.py
"""
Throttled Django admin login (7-B, SEC-15 / debt row 90).

DRF throttles never applied to Django admin, so staff passwords could be guessed
at full speed. This wraps the admin's own login view (config/urls.py routes
/admin/login/ here first): failed sign-ins are counted per client address and
per account in the shared cache; past ADMIN_LOGIN_MAX_FAILURES_PER_IP or
ADMIN_LOGIN_MAX_FAILURES_PER_ACCOUNT within ADMIN_LOGIN_WINDOW_SECONDS the form
answers 429 for the rest of the window, even for the right password. A
successful sign-in clears that address's and that account's counts.

MFA for staff is not in the app yet: the plan is in docs/security/secrets.md.
"""
import hashlib
import math
import time

from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.http import HttpResponse
from django.utils.html import escape

from .request_ip import client_ip


def _keys(request):
    account = (request.POST.get('username') or '').strip().lower()
    who = client_ip(request) or 'unknown'
    digest = hashlib.sha256(account.encode('utf-8')).hexdigest()
    return [
        (f'adminlogin:ip:{who}', settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP),
        (f'adminlogin:acct:{digest}', settings.ADMIN_LOGIN_MAX_FAILURES_PER_ACCOUNT),
    ]


def _locked_response(until):
    seconds = max(1, math.ceil(until - time.time()))
    minutes = max(1, math.ceil(seconds / 60))
    body = (
        '<!doctype html><html><head><meta charset="utf-8"><title>Too many sign-in attempts</title></head>'
        f'<body><h1>Too many sign-in attempts</h1><p>{escape(f"Try again in {minutes} minutes.")}</p></body></html>'
    )
    response = HttpResponse(body, status=429)
    response['Retry-After'] = str(seconds)
    return response


def throttled_admin_login(request, extra_context=None):
    if request.method != 'POST':
        return admin.site.login(request, extra_context)

    window = settings.ADMIN_LOGIN_WINDOW_SECONDS
    keys = _keys(request)
    for key, _ in keys:
        until = cache.get(f'{key}:lock')
        if until:
            return _locked_response(until)

    response = admin.site.login(request, extra_context)
    if response.status_code == 302 and request.user.is_authenticated:
        for key, _ in keys:
            cache.delete(key)
        return response

    for key, limit in keys:
        cache.add(key, 0, timeout=window)
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window)
            count = 1
        if count >= limit:
            cache.set(f'{key}:lock', time.time() + window, timeout=window)
            cache.delete(key)
    return response
