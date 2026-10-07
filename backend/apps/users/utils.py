# backend/apps/users/utils.py
import hashlib
import logging

logger = logging.getLogger(__name__)


def blacklist_all_outstanding_tokens_for_user(user):
    """
    Phase 4 (auth hardening) — "logout everywhere" for a user whose
    password just changed (self-service change OR reset-via-email).
    Neither path previously touched any issued token at all: a session
    hijacked before the password change (stolen refresh cookie, a
    forgotten logged-in device) stayed fully valid afterward, defeating
    much of the point of changing the password in the first place.

    Walks every OutstandingToken the token_blacklist app has recorded for
    this user (one row per refresh token ever issued via
    RefreshToken()/`.for_user()` while that app is installed — it is,
    see INSTALLED_APPS) and blacklists each one. A bare access token
    can't be revoked this way (JWTs are stateless and simplejwt's
    blacklist only covers refresh tokens) — that's a fundamental
    property of the JWT approach already in use here, not something this
    fix can close, so the short ACCESS_TOKEN_LIFETIME (15 minutes,
    config/settings/base.py) is what actually bounds how long an
    already-issued access token can outlive this call.

    Never raises: this always runs as a side effect of a password change
    that must still succeed even if, for some reason, blacklisting a
    specific row fails (e.g. a concurrent delete) — a password change
    must never appear to fail because of a housekeeping step.

    Lives in its own module (not apps/users/views.py or serializers.py)
    specifically so both can import it without a circular dependency —
    views.py already imports from serializers.py.
    """
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

    try:
        outstanding = OutstandingToken.objects.filter(user=user)
        for token in outstanding:
            try:
                BlacklistedToken.objects.get_or_create(token=token)
            except Exception:
                logger.exception(
                    "Failed to blacklist outstanding token id=%s for user_id=%s", token.id, user.id
                )
    except Exception:
        logger.exception("Failed to enumerate outstanding tokens for user_id=%s", user.id)


def revoke_all_sessions(user):
    """
    7-C: ends EVERY session of `user` at once. Used by password reset, password
    change and logout-all.

    - bumps `user.token_version`: every access AND refresh token already issued
      (cookie or bearer) carries the old number in its `tv` claim and is refused
      on its next use (apps/core/authentication.py, CookieTokenRefreshView), so
      no access token outlives this call, not even for its remaining 15 minutes;
    - blacklists the outstanding refresh tokens too (belt and braces, and it keeps
      the token_blacklist tables meaning what they say);
    - deletes every pending password-reset link of the account;
    - clears the per-account login and admin-login failure counters (keyed on the
      email), so the owner is not locked out of the account they just secured.

    Django admin sessions need nothing extra: Django drops a session whose stored
    password hash no longer matches. `user` is refreshed in place, so tokens minted
    afterwards for this same object (the device that changed the password) carry
    the new version.
    """
    from django.core.cache import cache
    from django.db.models import F

    from .models import PasswordResetToken, User

    User.objects.filter(pk=user.pk).update(token_version=F('token_version') + 1)
    user.refresh_from_db(fields=['token_version'])
    PasswordResetToken.objects.filter(user=user).delete()
    blacklist_all_outstanding_tokens_for_user(user)

    digest = hashlib.sha256((user.email or '').strip().lower().encode('utf-8')).hexdigest()
    try:
        cache.delete_many([
            f'throttle_login_account_{digest}',
            f'adminlogin:acct:{digest}',
            f'adminlogin:acct:{digest}:lock',
        ])
    except Exception:
        logger.exception('Could not clear the login failure counters for user_id=%s', user.pk)
