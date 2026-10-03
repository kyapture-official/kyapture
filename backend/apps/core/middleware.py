"""HTTP safeguards shared by the JSON API.

DRF's exception handler formats expected API exceptions, but an unexpected
exception raised before DRF can build a response would otherwise be rendered
by Django's DEBUG technical-response page during local development.  API
consumers must always receive JSON, regardless of DEBUG.
"""

import logging

from django.http import JsonResponse


logger = logging.getLogger(__name__)


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
