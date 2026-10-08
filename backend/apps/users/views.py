# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/views.py
import hashlib
import logging

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters
from django.utils.decorators import method_decorator
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError


from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenBackendError, TokenError
from .models import User
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
    UserSettingsSerializer,
)
from . import audit
from .password_policy import password_problems
from .tokens import VersionedRefreshToken, token_version_of
from .utils import revoke_all_sessions

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# PRIVATE SECURITY HELPER: HTTPONLY COOKIE INJECTOR
# ─────────────────────────────────────────────────────────────

def set_auth_cookies(response, access_token, refresh_token):
    """
    Surgically injects access and refresh tokens directly into HttpOnly cookies.
    - httponly=True: Blocks browser Javascript (XSS) from reading or stealing tokens.
    - secure=settings.SESSION_COOKIE_SECURE: Enforces HTTPS encryption in production.
    - samesite='Lax': Mitigates Cross-Site Request Forgery (CSRF).
    - domain=settings.SESSION_COOKIE_DOMAIN: Enables wildcard subdomain sharing (.yourdomain.com).
    """
    domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
    secure = getattr(settings, 'SESSION_COOKIE_SECURE', False)

    # Set Access Token Cookie (Short-lived: 15 Minutes)
    response.set_cookie(
        key='access_token',
        value=access_token,
        httponly=True,
        secure=secure,
        samesite='Lax',
        domain=domain,
        max_age=15 * 60  # 15 Minutes
    )

    # Set Refresh Token Cookie (Long-lived: 7 Days)
    response.set_cookie(
        key='refresh_token',
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite='Lax',
        domain=domain,
        max_age=7 * 24 * 60 * 60  # 7 Days
    )


# ─────────────────────────────────────────────────────────────
# VIEW CONTROLLERS
# ─────────────────────────────────────────────────────────────
class RegisterRateThrottle(AnonRateThrottle):
    """7-B: sign-ups per address get their own tight scope (was the shared anon 100/day)."""
    scope = 'register'


@method_decorator(ensure_csrf_cookie, name='dispatch')
class RegisterView(APIView):
    """
    POST /api/v1/auth/register/
    Open access registration. Automatically sets secure cookies upon creation.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RegisterRateThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.save()
            refresh = VersionedRefreshToken.for_user(user)

            # Response body contains ONLY profile metadata—no raw token exposure
            response = Response({
                'user': UserProfileSerializer(user, context={'request': request}).data,
            }, status=status.HTTP_201_CREATED)

            # Inject secure HttpOnly cookies
            set_auth_cookies(response, str(refresh.access_token), str(refresh))
            return response

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginRateThrottle(AnonRateThrottle):
    """
    Limits anonymous login attempts to the custom 'login' rate (5/minute)
    configured in settings. Mirrors the same brute-force protection pattern
    already used by PasswordUnlockRateThrottle for gallery unlocks — the
    photographer's own account credentials deserve at least the same
    protection as a guest-facing gallery password.
    """
    scope = 'login'


class LoginAccountRateThrottle(SimpleRateThrottle):
    """
    7-B: login attempts per ACCOUNT (the typed email), on top of the per-address
    `login` scope, so many addresses together still get only `login_account`
    tries on one account. Keyed on a hash of the normalised email (no address
    is stored in the cache key).
    """
    scope = 'login_account'

    def get_cache_key(self, request, view):
        email = request.data.get('email') if hasattr(request.data, 'get') else None
        if not isinstance(email, str) or not email.strip():
            return None
        return self.cache_format % {
            'scope': self.scope,
            'ident': hashlib.sha256(email.strip().lower().encode('utf-8')).hexdigest(),
        }

    def allow_request(self, request, view):
        allowed = super().allow_request(request, view)
        if not allowed:
            self.audit_lockout(request)
        return allowed

    def audit_lockout(self, request):
        """
        7.5-A: the account is locked out of signing in for the rest of the window. ONE audit
        row per account and window (not one per refused try). The row names the account only
        when it exists; a typed address that is no account is never stored.
        """
        from django.core.cache import cache

        key = self.get_cache_key(request, None)
        if not key or not cache.add(f'audit_once:{key}', 1, timeout=self.duration):
            return
        email = request.data.get('email').strip().lower()
        target = User.objects.filter(email=email).only('id', 'email').first()
        audit.record_event(audit.Action.LOGIN_LOCKOUT, target=target, request=request, reason='account_rate')


@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginView(APIView):
    """
    POST /api/v1/auth/login/
    Authenticates photographer credentials and sets secure session cookies.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle, LoginAccountRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            data = serializer.validated_data

            # Extract credentials and metadata safely
            access_token = data.get('access')
            refresh_token = data.get('refresh')
            user_data = data.get('user')

            # Response contains only the safe user profile structure
            response = Response({
                'user': user_data
            }, status=status.HTTP_200_OK)

            # Inject secure HttpOnly cookies
            set_auth_cookies(response, access_token, refresh_token)
            return response

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Safely blacklists session tokens and purges all active browser cookies.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Automatically extract refresh token from incoming HttpOnly cookies
        refresh_token = request.COOKIES.get('refresh_token')

        response = Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)

        # Purge both cookies from the browser by setting empty values and immediate expirations
        domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
        response.delete_cookie('access_token', domain=domain)
        response.delete_cookie('refresh_token', domain=domain)

        # Blacklist the refresh token inside the database
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass  # Ignore if already blacklisted or expired

        return response


class TokenRefreshRateThrottle(SimpleRateThrottle):
    """
    7-B (SEC-17 / debt row 92): refreshes are counted per USER, read from the
    refresh cookie's verified signature (a forged id cannot spend another
    user's allowance). Before, refresh fell under the anonymous 100/day bucket
    per address, so a few people behind one NAT (one active tab refreshes
    ~96 times a day) logged each other out. An invalid/expired cookie is
    counted per address instead.
    """
    scope = 'token_refresh'

    def get_cache_key(self, request, view):
        from rest_framework_simplejwt.state import token_backend

        ident = None
        raw = request.COOKIES.get('refresh_token')
        if raw:
            try:
                payload = token_backend.decode(raw, verify=True)
                user_id = payload.get(getattr(settings, 'SIMPLE_JWT', {}).get('USER_ID_CLAIM', 'user_id'))
                if user_id is not None:
                    ident = f'user:{user_id}'
            except TokenBackendError:
                ident = None
        if ident is None:
            ident = f'ip:{self.get_ident(request)}'
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class CookieTokenRefreshView(APIView):
    """
    POST /api/v1/auth/token/refresh/
    Reads refresh token from secure cookies and sets updated access cookies.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [TokenRefreshRateThrottle]

    def post(self, request):
        refresh_token = request.COOKIES.get('refresh_token')
        if not refresh_token:
            return Response({'error': 'Session expired. Please log in again.'}, status=status.HTTP_401_UNAUTHORIZED)

        jwt_settings = getattr(settings, 'SIMPLE_JWT', {})

        try:
            refresh = RefreshToken(refresh_token)

            # Phase 4 (F-36 fix): this previously did `new_refresh_token =
            # str(refresh)` — re-serializing the SAME RefreshToken object,
            # which has the SAME jti as the one just presented. That mints
            # nothing new and blacklists nothing, despite
            # ROTATE_REFRESH_TOKENS/BLACKLIST_AFTER_ROTATION both being
            # True in settings — a stolen refresh cookie stayed valid for
            # its full 7-day life regardless of how many times it (or a
            # copy of it) was used to refresh. Real rotation requires
            # minting a genuinely NEW token, which needs the user — not
            # available from `request.user` here (this view is
            # AllowAny/unauthenticated by design, since all it has is the
            # refresh cookie), so it's read from the token's own verified
            # payload instead.
            user_id_claim = jwt_settings.get('USER_ID_CLAIM', 'user_id')
            user_id = refresh.payload.get(user_id_claim)
            user = User.objects.filter(pk=user_id, is_active=True).first()
            # 7-C: a refresh token minted before a password reset/change or a
            # logout-all carries an older `tv` claim: that session is over.
            if user is None or token_version_of(refresh) != user.token_version:
                return Response(
                    {'error': 'Invalid or expired session.'}, status=status.HTTP_401_UNAUTHORIZED
                )

            if jwt_settings.get('ROTATE_REFRESH_TOKENS', False):
                new_refresh = VersionedRefreshToken.for_user(user)
                new_access_token = str(new_refresh.access_token)
                new_refresh_token = str(new_refresh)

                if jwt_settings.get('BLACKLIST_AFTER_ROTATION', False):
                    try:
                        refresh.blacklist()
                    except AttributeError:
                        # token_blacklist app not installed — rotation
                        # still mints a new token above; the old one just
                        # isn't explicitly revoked (it still expires
                        # naturally at its own REFRESH_TOKEN_LIFETIME).
                        pass
            else:
                # Rotation disabled: same non-rotating behavior as before
                # — reuse the presented refresh token, only the access
                # token is renewed.
                new_access_token = str(refresh.access_token)
                new_refresh_token = None

            response = Response({'message': 'Session refreshed successfully.'}, status=status.HTTP_200_OK)

            domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
            secure = getattr(settings, 'SESSION_COOKIE_SECURE', False)

            # Re-inject refreshed access token
            response.set_cookie(
                key='access_token',
                value=new_access_token,
                httponly=True,
                secure=secure,
                samesite='Lax',
                domain=domain,
                max_age=15 * 60
            )

            if new_refresh_token is not None:
                response.set_cookie(
                    key='refresh_token',
                    value=new_refresh_token,
                    httponly=True,
                    secure=secure,
                    samesite='Lax',
                    domain=domain,
                    max_age=7 * 24 * 60 * 60
                )

            return response
        except TokenError:
            return Response({'error': 'Invalid or expired session.'}, status=status.HTTP_401_UNAUTHORIZED)

@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(APIView):
    """GET/PUT /api/v1/auth/me/ - Requires authenticated cookie authorization"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user, context={'request': request})
        return Response(serializer.data)

    def put(self, request):
        serializer = UserProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordChangeRateThrottle(UserRateThrottle):
    """Per-user limit on change-password attempts: the current-password check is guessable otherwise."""
    scope = 'password_change'


class ChangePasswordView(APIView):
    """
    PUT /api/v1/auth/change-password/ - Requires authenticated cookie authorization

    On success every session of the account ends (ChangePasswordSerializer.save
    -> revoke_all_sessions): every access and refresh token already issued, on
    every device, stops working on its next use. The device that made the
    change is then given a fresh session so it stays signed in, and the owner
    gets a "your password was changed" email.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [PasswordChangeRateThrottle]

    def put(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            user = serializer.save()
            response = Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)
            refresh = VersionedRefreshToken.for_user(user)
            set_auth_cookies(response, str(refresh.access_token), str(refresh))
            return response
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutAllView(APIView):
    """
    POST /api/v1/auth/logout-all/
    Signs the account out everywhere (revoke_all_sessions, apps/users/utils.py):
    every access and refresh token already issued, this device's included,
    stops working on its next use, and this browser's cookies are cleared.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        revoke_all_sessions(request.user)
        response = Response({'message': 'Signed out of all sessions.'}, status=status.HTTP_200_OK)
        domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
        response.delete_cookie('access_token', domain=domain)
        response.delete_cookie('refresh_token', domain=domain)
        return response


class UserSettingsView(APIView):
    """
    GET/PATCH /api/v1/auth/settings/
    Notification preferences, privacy, and Collection Defaults for the
    signed-in photographer. Scoped to request.user — there is no id anywhere
    in the request to manipulate. Unknown keys are rejected (400), so a typo or
    a probe for a privileged field is never silently "saved".
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSettingsSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSettingsSerializer(
            request.user, data=request.data, partial=True, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSettingsSerializer(request.user).data)


class PublicMetricsRateThrottle(AnonRateThrottle):
    """
    Phase 4 (F-41 fix) — shares the same 'public_gallery_browse' scope as
    apps.clients.views.PublicGalleryBrowseThrottle (same rate, defined
    once in settings.DEFAULT_THROTTLE_RATES) rather than the blanket
    'anon: 100/day' — a busy landing page can legitimately call this on
    every load, easily exceeding 100/day across a handful of visitors
    sharing one IP.
    """
    scope = 'public_gallery_browse'


class TotalUsersView(APIView):
    """GET /api/total-users - Public count metrics and recent user avatars"""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicMetricsRateThrottle]

    def get(self, request):
        queryset = User.objects.filter(is_superuser=False, is_staff=False)
        count = queryset.count()

        # Fetch the latest 5 registered photographers for the landing page avatar row
        latest = queryset.order_by('-date_joined')[:5]

        # Muted aesthetic color palette matching frontend expectations
        color_palette = ['#8c6d4f', '#4a7c6f', '#5c6b73', '#7b5c8c', '#8c5c5c']

        latest_users = []
        for index, user in enumerate(latest):
            name = user.display_name or user.username or 'U'
            initial = name[0].upper()
            color = color_palette[index % len(color_palette)]
            latest_users.append({
                "initial": initial,
                "color": color
            })

        return Response({
            "total_count": count,
            "latest_users": latest_users
        }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────
# PASSWORD RESET (7-C)
# ─────────────────────────────────────────────────────────────
# Forgot -> emailed one-time link (apps/users/password_reset.py) -> new password
# -> link dead -> every session of the account revoked -> "password changed" email.

RESET_LINK_INVALID = 'This reset link is invalid or has expired. Request a new one.'


class PasswordResetRateThrottle(AnonRateThrottle):
    """Reset requests per client address (`password_reset`). Answered with a 429, which says nothing about any account."""
    scope = 'password_reset'


class PasswordResetEmailThrottle(SimpleRateThrottle):
    """
    Reset emails per typed address (`password_reset_email`), counted whether or
    not an account uses it. NOT a throttle class of the view: past the limit the
    view still answers the same 200 and simply sends nothing, so nobody can fill
    an inbox and the answer never changes.
    """
    scope = 'password_reset_email'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': hashlib.sha256(view.reset_email.encode('utf-8')).hexdigest(),
        }


class PasswordResetConfirmRateThrottle(AnonRateThrottle):
    """Link checks and new-password submissions per client address (`password_reset_confirm`)."""
    scope = 'password_reset_confirm'


def _reset_link_invalid():
    return Response({'error': RESET_LINK_INVALID, 'code': 'reset_link_invalid'}, status=status.HTTP_400_BAD_REQUEST)


def _posted_str(request, key):
    value = request.data.get(key) if hasattr(request.data, 'get') else None
    return value if isinstance(value, str) else ''


class PasswordResetRequestView(APIView):
    """
    POST /api/v1/auth/password/reset/  {"email": "..."}

    The same 200 and the same body for every well-formed address, known or not,
    and the same work: the request only counts the address and queues a Celery
    task (no user lookup here), so its timing does not depend on the account
    existing either. The task looks the account up and sends the link. A
    malformed address is a 400 (true for any address of that shape).
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetRateThrottle]

    def generic_message(self):
        return (
            'If an account uses that email, we have sent it a link to reset the password. '
            f'The link works once and expires in {settings.PASSWORD_RESET_TOKEN_MINUTES} minutes.'
        )

    def post(self, request):
        from .tasks import send_password_reset_email_task

        email = _posted_str(request, 'email').strip().lower()
        try:
            if len(email) > 254:
                raise DjangoValidationError('too long')
            validate_email(email)
        except DjangoValidationError:
            return Response(
                {'error': 'Enter a valid email address.', 'code': 'email_invalid'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        self.reset_email = email
        if PasswordResetEmailThrottle().allow_request(request, self):
            def dispatch():
                try:
                    send_password_reset_email_task.delay(email)
                except Exception:
                    logger.exception('Could not queue a password reset email')

            transaction.on_commit(dispatch)

        return Response({'message': self.generic_message()}, status=status.HTTP_200_OK)


class PasswordResetCheckView(APIView):
    """
    POST /api/v1/auth/password/reset/check/  {"token": "..."}

    Lets the reset page show "invalid or expired link" before the person types a
    new password. Does not use the link up. 200 {"valid": true} or 400
    `reset_link_invalid` (unknown, expired, already used or replaced: one answer).
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetConfirmRateThrottle]

    def post(self, request):
        from .password_reset import live_token_queryset

        if not live_token_queryset(_posted_str(request, 'token')).exists():
            return _reset_link_invalid()
        return Response({'valid': True}, status=status.HTTP_200_OK)


@method_decorator(sensitive_post_parameters('token', 'new_password', 'new_password2'), name='dispatch')
class PasswordResetConfirmView(APIView):
    """
    POST /api/v1/auth/password/reset/confirm/  {"token", "new_password", "new_password2"}

    The new password must pass the one policy (apps/users/password_policy.py:
    the registration validators, not the email, not the current password). A
    refused password leaves the link usable so the person can try another one.
    On success, in one transaction: the password is set, the link and every
    other pending link of the account are deleted, every session (access and
    refresh tokens, cookie or bearer) is revoked, and a "password changed"
    email is queued. This browser's auth cookies are cleared too.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetConfirmRateThrottle]

    def post(self, request):
        from .password_reset import live_token_queryset, queue_password_changed_email

        token = _posted_str(request, 'token')
        new_password = _posted_str(request, 'new_password')
        new_password2 = _posted_str(request, 'new_password2')

        if not token:
            return _reset_link_invalid()
        if not new_password:
            return Response({'new_password': ['Enter a new password.']}, status=status.HTTP_400_BAD_REQUEST)
        if new_password != new_password2:
            return Response({'new_password2': ['Passwords do not match.']}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # The row lock makes a link usable exactly once, even for two
            # simultaneous submissions: the second one finds no row.
            row = live_token_queryset(token).select_for_update().select_related('user').first()
            if row is None:
                return _reset_link_invalid()
            user = row.user
            problems = password_problems(new_password, user)
            if problems:
                return Response({'new_password': problems}, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(new_password)
            user.save(update_fields=['password'])
            revoke_all_sessions(user)
            queue_password_changed_email(user, 'reset')
            audit.record_event(audit.Action.PASSWORD_RESET, target=user, request=request, reason='reset')

        logger.info('Password reset completed for user_id=%s', user.pk)
        response = Response(
            {'message': 'Your password has been reset. Sign in with your new password.'},
            status=status.HTTP_200_OK,
        )
        domain = getattr(settings, 'SESSION_COOKIE_DOMAIN', None)
        response.delete_cookie('access_token', domain=domain)
        response.delete_cookie('refresh_token', domain=domain)
        return response
