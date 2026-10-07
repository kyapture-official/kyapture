# backend/apps/users/tokens.py
"""
JWTs that die with the account's sessions (7-C).

Every refresh token minted here carries the user's current `token_version` as the
`tv` claim; the access token derived from it copies the claim. A token whose `tv`
is not the user's current value is refused by CookieJWTAuthentication (every API
request) and by CookieTokenRefreshView, so `revoke_all_sessions` (bumps the
number) ends every session at once, including access tokens that have not expired
yet. Tokens minted before 7-C have no claim and count as version 0.
"""
from rest_framework_simplejwt.tokens import RefreshToken

TOKEN_VERSION_CLAIM = 'tv'


def token_version_of(token):
    """The version a decoded token was minted for (0 for pre-7-C tokens)."""
    try:
        return int(token.get(TOKEN_VERSION_CLAIM, 0))
    except (TypeError, ValueError):
        return -1


class VersionedRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        token[TOKEN_VERSION_CLAIM] = user.token_version
        return token
