# backend/apps/users/password_policy.py
"""
The one password policy (7-C): registration, password change and password reset
all call `password_problems`, so a password one of them refuses is refused by all.

Django's AUTH_PASSWORD_VALIDATORS (length 8, common, numeric, similarity to the
account's attributes) plus two explicit rules: never the account's email, and
never the password the account has now.
"""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

SAME_AS_EMAIL = "Your password can't be your email address."
SAME_AS_CURRENT = 'Choose a password different from your current one.'


def password_problems(password, user):
    """A list of messages (empty when the password is acceptable for `user`)."""
    problems = []
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        problems.extend(exc.messages)
    email = (getattr(user, 'email', '') or '').strip().lower()
    if email and password.strip().lower() == email:
        problems.append(SAME_AS_EMAIL)
    # Only a saved account has a current password (an account with no usable
    # password, e.g. a future social login, simply has none to compare with).
    if not user._state.adding and user.has_usable_password() and user.check_password(password):
        problems.append(SAME_AS_CURRENT)
    return problems
