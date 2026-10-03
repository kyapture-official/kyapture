# backend/apps/users/utils.py
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
