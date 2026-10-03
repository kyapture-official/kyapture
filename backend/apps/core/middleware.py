"""HTTP safeguards shared by the JSON API.

DRF's exception handler formats expected API exceptions, but an unexpected
exception raised before DRF can build a response would otherwise be rendered
by Django's DEBUG technical-response page during local development.  API
consumers must always receive JSON, regardless of DEBUG.
"""

import logging

from django.http import JsonResponse
from django.middleware.gzip import GZipMiddleware


logger = logging.getLogger(__name__)


class JsonGZipMiddleware(GZipMiddleware):
    """
    Gzip for JSON API bodies ONLY.

    Django's stock GZipMiddleware compresses any response over 200 bytes,
    which includes streamed file downloads and ZIPs — wasted CPU on data that
    is already compressed, and it would strip the Content-Length those
    downloads rely on. The big wins are the JSON payloads (a 150-asset media
    list or a 60-photo public page is ~40–110 KB of highly repetitive text),
    so only application/json is compressed and everything else passes through
    untouched. Django's implementation already varies on Accept-Encoding,
    skips clients that don't ask for gzip, and randomizes the stream header
    to blunt BREACH-style length probing.
    """

    def process_response(self, request, response):
        if getattr(response, 'streaming', False):
            return response
        if not response.get('Content-Type', '').startswith('application/json'):
            return response
        return super().process_response(request, response)


class ApiExceptionMiddleware:
    """Convert unexpected API exceptions to a non-sensitive JSON response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not request.path.startswith("/api/"):
            return None

        logger.exception("Unhandled API exception for %s", request.path)
        return JsonResponse(
            {
                "error": "The server could not complete that request. Please try again.",
                "code": "internal_server_error",
            },
            status=500,
        )
