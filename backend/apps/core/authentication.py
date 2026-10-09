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
            self.refuse_closing_account(request, user)

            # 4. Critical Security Guard: Enforce CSRF checks if the token came from a cookie
            if from_cookie:
                self.enforce_csrf(request)

            return user, validated_token
        except InvalidToken:
            return None

    # 7.5-E: while an account deletion is waiting, the signed-in owner can see who they are, read the deletion
    # status, cancel it and sign out. Every other authenticated route is refused with a clear code, so nothing is
    # created, changed or paid for on an account that is closing. `auth-me` is read-only.
    CLOSING_ACCOUNT_ROUTES = frozenset({
        'auth-me', 'auth-logout', 'auth-logout-all', 'account-deletion-status', 'account-deletion-cancel',
    })

    def refuse_closing_account(self, request, user):
        if user.deletion_requested_at is None:
            return
        match = getattr(request, 'resolver_match', None) or getattr(getattr(request, '_request', None), 'resolver_match', None)
        name = getattr(match, 'url_name', None)
        if name in self.CLOSING_ACCOUNT_ROUTES and (name != 'auth-me' or request.method in ('GET', 'HEAD', 'OPTIONS')):
            return
        raise PermissionDenied(detail={
            'error': 'This account is scheduled for deletion. Cancel the deletion to use it again.',
            'code': 'account_pending_deletion',
        })

    def get_user(self, validated_token):
        """
        7-C: a token minted before the account's sessions were revoked (password
        reset or change, logout-all) carries an older `tv` claim and is refused,
        so revocation reaches access tokens too, not only refresh tokens.
        """
        from apps.users.tokens import token_version_of

        user = super().get_user(validated_token)
        if token_version_of(validated_token) != user.token_version:
            raise InvalidToken('Session revoked.')
        return user

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