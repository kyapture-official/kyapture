# backend/apps/core/request_ip.py
"""
The ONE way the app reads a visitor's address (7-B, SEC-01 / debt row 78).

It is the address DRF's throttles key on (`BaseThrottle.get_ident`), which honours
REST_FRAMEWORK['NUM_PROXIES']: with no proxy (0) the TCP peer (REMOTE_ADDR), behind
N trusted proxies the address the outermost trusted proxy added. A client-sent
X-Forwarded-For value is never taken on its own, so the address stored on a
ClientSession / DownloadLog and the one the lockout counts are the same one the
throttles count, and none of them can be chosen by the client.
"""
import ipaddress

from rest_framework.throttling import BaseThrottle


def client_ip(request):
    """The visitor's address as the throttles see it, or None when it is not a valid IP."""
    try:
        return str(ipaddress.ip_address(BaseThrottle().get_ident(request).strip()))
    except (ValueError, TypeError, AttributeError):
        return None
