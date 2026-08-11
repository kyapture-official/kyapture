# C:/Users/LENOVO/Desktop/kyapture/backend/apps/core/authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied


class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication class for Kaypture.
    
    Extends SimpleJWT's native authentication to extract tokens 
    from secure HttpOnly cookies ('access_token') and enforces
    strict CSRF verification for state-mutating requests.
    """

    def authenticate(self, request):
        # 1. Attempt to read the access token from incoming cookies
        raw_token = request.COOKIES.get('access_token')
        from_cookie = True

        # 2. Fallback: If no cookie exists, check standard Authorization header 
        if not raw_token:
            header = self.get_header(request)
            if header is not None:
                raw_token = self.get_raw_token(header)
                from_cookie = False

        if raw_token is None:
            return None

        try:
            # 3. Validate the token and return the associated user model
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)

            # 4. Critical Security Guard: Enforce CSRF checks if the token came from a cookie
            if from_cookie:
                self.enforce_csrf(request)

            return user, validated_token
        except InvalidToken:
            return None

    def enforce_csrf(self, request):
        """
        Enforces Django's native, battle-tested CSRF validation.
        Optimized to bypass read-only safe HTTP methods.
        """
        # Performance Bypass: Read-only methods do not require CSRF protection
        if request.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            return

        check = CSRFCheck(request)
        
        # 1. Populates request.META['CSRF_COOKIE'] from the browser cookie jar
        check.process_request(request)
        
        # 2. Validates the client-submitted header token against the S3/domain cookie
        reason = check.process_view(request, None, (), {})
        
        if reason:
            # CSRF validation failed - block the execution path immediately
            raise PermissionDenied(f"CSRF Failed: {reason}")