from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from .models import User
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
)


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


class LoginView(APIView):
    """
    POST /api/v1/auth/login/
    Authenticates photographer credentials and sets secure session cookies.
    """
    permission_classes = [AllowAny]
    authentication_classes = [] 

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

        try:
            refresh = RefreshToken(refresh_token)
            new_access_token = str(refresh.access_token)
            
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
            
            # Optional: Rotate refresh token if enabled in settings
            if getattr(settings, 'SIMPLE_JWT', {}).get('ROTATE_REFRESH_TOKENS', False):
                new_refresh_token = str(refresh)
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
    

class TotalUsersView(APIView):
    """GET /api/total-users - Public count metrics"""
    permission_classes = [AllowAny]
    authentication_classes = [] 

    def get(self, request):
        count = User.objects.filter(is_superuser=False, is_staff=False).count()
        return Response({
            "total_count": count,
            "latest_users": []
        }, status=status.HTTP_200_OK)

class PasswordResetRequestView(APIView):
    """
    POST /api/v1/auth/password/reset/
    
    Processes photographer password reset requests.
    To prevent malicious email harvesting attacks, this view always returns 
    a successful generic message, concealing whether the email exists.
    
    If the email is registered, it compiles a secure password-reset link 
    and prints it directly to your Django server console.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response(
                {'error': 'A valid email address is required to reset passwords.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Query active users only
            user = User.objects.get(email=email, is_active=True)
            
            # Generate standard Django cryptographic tokens and base64 UID
            token = default_token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Construct the target local Vite React frontend route for confirmation
            reset_url = f"http://localhost:5173/auth/password/reset/confirm/{uidb64}/{token}/"
            
            # Print the terminal alert (simulating safe local development SMTP)
            print("\n" + "═"*80)
            print(f"AWS SES SMTP IN-MEMORY SPOOL: PASSWORD RESET REQUEST FOR {user.email}")
            print(f"Click the link below to configure your new credentials:")
            print(reset_url)
            print("═"*80 + "\n")
            
        except User.DoesNotExist:
            # Catch silently to block user enumeration hacking
            pass

        return Response({
            'message': 'If an active account is registered with that email, a secure password reset link has been compiled.'
        }, status=status.HTTP_200_OK)