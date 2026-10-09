# backend/apps/users/account_api.py
"""
Account deletion API (7.5-E). Everything acts on `request.user`: there is no user id anywhere in these routes, so
one account can never delete (or cancel the deletion of) another. The rules are in account_deletion.py.

  GET   /api/v1/auth/account/deletion/                  state, cooling-off days, what blocks a request
  POST  /api/v1/auth/account/deletion/code/             email a one-time code (accounts with no password only)
  POST  /api/v1/auth/account/deletion/request/          {password | code, email}  -> pending; every session ends
  POST  /api/v1/auth/account/deletion/cancel/           the signed-in owner cancels a waiting deletion
  POST  /api/v1/auth/account/deletion/cancel-link/      {token}  the emailed link (no sign-in needed)

While a deletion is waiting the API refuses every other authenticated route (apps/core/authentication.py), so
only the status and cancel routes above, /auth/me/ (read) and sign-out answer.
"""
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from . import account_deletion as deletion


class DeletionRequestThrottle(UserRateThrottle):
    scope = 'account_deletion'


class DeletionCodeThrottle(UserRateThrottle):
    scope = 'account_deletion_code'


class DeletionCancelThrottle(UserRateThrottle):
    scope = 'account_deletion_cancel'


class DeletionCancelLinkThrottle(AnonRateThrottle):
    """The emailed link needs no sign-in, so it is counted per client address (trusted-proxy aware, 7-B)."""
    scope = 'account_deletion_cancel_link'


def refusal(problem):
    return Response({'error': problem.message, 'code': problem.code}, status=problem.http_status)


def posted_str(request, key):
    value = request.data.get(key) if hasattr(request.data, 'get') else None
    return value if isinstance(value, str) else ''


def clear_session_cookies(response):
    domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
    response.delete_cookie('access_token', domain=domain)
    response.delete_cookie('refresh_token', domain=domain)


class DeletionStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(deletion.status_payload(request.user))


class DeletionCodeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [DeletionCodeThrottle]

    def post(self, request):
        try:
            deletion.send_confirmation_code(request.user)
        except deletion.DeletionError as problem:
            return refusal(problem)
        return Response(
            {'message': f'We sent a code to your email. It works for {settings.ACCOUNT_DELETION_CODE_MINUTES} minutes.'},
            status=status.HTTP_200_OK,
        )


@method_decorator(sensitive_post_parameters('password', 'code'), name='dispatch')
class DeletionRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [DeletionRequestThrottle]

    def post(self, request):
        try:
            payload = deletion.request_deletion(
                request.user,
                password=posted_str(request, 'password'),
                code=posted_str(request, 'code'),
                typed_email=posted_str(request, 'email'),
            )
        except deletion.DeletionError as problem:
            return refusal(problem)
        # Every session ended inside the request: this browser's cookies go too.
        response = Response(payload, status=status.HTTP_200_OK)
        clear_session_cookies(response)
        return response


class DeletionCancelView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [DeletionCancelThrottle]

    def post(self, request):
        try:
            payload = deletion.cancel_deletion(user=request.user)
        except deletion.DeletionError as problem:
            return refusal(problem)
        return Response(payload, status=status.HTTP_200_OK)


@method_decorator(sensitive_post_parameters('token'), name='dispatch')
class DeletionCancelLinkView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [DeletionCancelLinkThrottle]

    def post(self, request):
        try:
            deletion.cancel_deletion(token=posted_str(request, 'token'))
        except deletion.DeletionError as problem:
            return refusal(problem)
        return Response(
            {'message': 'The deletion is cancelled. Sign in to carry on.', 'cancelled': True},
            status=status.HTTP_200_OK,
        )
