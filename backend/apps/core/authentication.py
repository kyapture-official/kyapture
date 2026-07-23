from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication class for Kaypture.
    Extends SimpleJWT's native authentication to extract tokens 
    from secure HttpOnly cookies ('access_token') instead of 
    client-side Authorization headers.
    """

    def authenticate(self, request):
        # 1. Attempt to read the access token from incoming cookies
        raw_token = request.COOKIES.get('access_token')

        # 2. Fallback: If no cookie exists, check standard Authorization header 
        # (Useful for API testing tools like Postman or third-party webhooks)
        if not raw_token:
            header = self.get_header(request)
            if header is not None:
                raw_token = self.get_raw_token(header)

        # 3. If no token found anywhere in cookies or headers, return None (unauthenticated)
        if raw_token is None:
            return None

        try:
            # 4. Validate the token and return the associated user model
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        except InvalidToken:
            # Invalid or expired token inside cookie
            return None