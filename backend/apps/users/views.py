# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/views.py
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.template.loader import render_to_string


from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from .models import User
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
)
from .utils import blacklist_all_outstanding_tokens_for_user

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
@method_decorator(ensure_csrf_cookie, name='dispatch')
class RegisterView(APIView):
    """
    POST /api/v1/auth/register/
    Open access registration. Automatically sets secure cookies upon creation.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)

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


@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginView(APIView):
    """
    POST /api/v1/auth/login/
    Authenticates photographer credentials and sets secure session cookies.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

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


class CookieTokenRefreshView(APIView):
    """
    POST /api/v1/auth/token/refresh/
    Reads refresh token from secure cookies and sets updated access cookies.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

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
            if jwt_settings.get('ROTATE_REFRESH_TOKENS', False):
                user_id_claim = jwt_settings.get('USER_ID_CLAIM', 'user_id')
                user_id = refresh.payload.get(user_id_claim)
                try:
                    user = User.objects.get(pk=user_id, is_active=True)
                except User.DoesNotExist:
                    return Response(
                        {'error': 'Invalid or expired session.'}, status=status.HTTP_401_UNAUTHORIZED
                    )

                new_refresh = RefreshToken.for_user(user)
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


class ChangePasswordView(APIView):
    """PUT /api/v1/auth/change-password/ - Requires authenticated cookie authorization"""
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
# THROTTLES & PASSWORD RESET VIEWS
# ─────────────────────────────────────────────────────────────

# 1. Define the throttle class FIRST so Python registers it
class PasswordResetRateThrottle(AnonRateThrottle):
    """
    Limits anonymous password-reset requests to the 'password_reset' rate
    configured in REST_FRAMEWORK.DEFAULT_THROTTLE_RATES.
    """
    scope = 'password_reset'


# 2. Define the view SECOND after its dependencies are declared
class PasswordResetRequestView(APIView):
    """
    POST /api/v1/auth/password/reset/

    Anti-enumeration contract: this endpoint returns the SAME 200 response,
    with the SAME generic message, whether or not `email` matches a real
    account — and it does so unconditionally, regardless of what happens
    while trying to build/send the actual email. That second half used to
    be the weak point: template rendering and send_mail() ran inside a
    try/except that only caught User.DoesNotExist, so a missing template
    (or any other send-path failure) propagated as an uncaught 500 for
    real accounts while a non-existent email still quietly returned 200 —
    an exception-shaped way to find out which emails have accounts. Every
    failure past "does this user exist" is now caught, logged, and
    swallowed behind the identical response below.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetRateThrottle]

    GENERIC_MESSAGE = (
        'If an active account is registered with that email, a secure '
        'password reset link has been sent.'
    )

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response(
                {'error': 'A valid email address is required to reset passwords.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        generic_response = Response(
            {'message': self.GENERIC_MESSAGE}, status=status.HTTP_200_OK
        )

        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            # No account for this email — return the exact same response as
            # the success path below. Nothing here should ever distinguish
            # "no such account" from "account exists, email dispatch failed".
            return generic_response

        # From here on, everything is best-effort. A template bug, an SES
        # outage, or any other failure while composing/sending the email
        # must never surface as a 500 and must never change the response
        # shape — that would defeat the whole point of the identical
        # generic_response above. Log it and move on.
        try:
            token = default_token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))

            reset_url = f"{settings.FRONTEND_URL}/auth/password/reset/confirm/{uidb64}/{token}/"

            email_context = {
                'display_name': user.display_name or user.username,
                'reset_url': reset_url,
            }
            text_body = render_to_string('users/emails/password_reset_email.txt', email_context)
            html_body = render_to_string('users/emails/password_reset_email.html', email_context)

            send_mail(
                subject='Reset your Kyapture password',
                message=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_body,
                fail_silently=False,
            )
            logger.info('Password reset email dispatched for user_id=%s', user.id)
        except Exception:
            logger.exception(
                'Password reset email failed to send for user_id=%s — request '
                'still reports success to the caller (anti-enumeration contract).',
                user.id,
            )

        return generic_response


class PasswordResetConfirmView(APIView):
    """
    POST /api/v1/auth/password/reset/confirm/
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        uidb64 = request.data.get('uidb64', '').strip()
        token = request.data.get('token', '').strip()
        new_password = request.data.get('new_password', '')
        new_password2 = request.data.get('new_password2', '')

        if not (uidb64 and token and new_password):
            return Response(
                {'error': 'UID, token, and new password parameters are all required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_password != new_password2:
            return Response(
                {'error': 'Passwords do not match.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {'error': 'Invalid reset link. The user associated with this token does not exist.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {'error': 'This password reset link has expired or is invalid.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as e:
            return Response(
                {'error': list(e.messages)[0], 'details': list(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        # Phase 4 (auth hardening): invalidate every outstanding refresh
        # token for this user — see blacklist_all_outstanding_tokens_for_user's
        # own docstring for why this matters specifically for a password
        # reset (anyone with a still-valid session before the reset must
        # not keep it afterward).
        blacklist_all_outstanding_tokens_for_user(user)

        return Response({
            'message': 'Password changed successfully. Please log in with your new credentials.'
        }, status=status.HTTP_200_OK)
