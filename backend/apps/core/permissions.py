# C:/Users/LENOVO/Desktop/kyapture/backend/apps/core/permissions.py
from rest_framework.permissions import BasePermission


class IsPhotographer(BasePermission):
    """
    Enforces that the user is logged in, authenticated, and has an active account.
    Customized to provide explicit error messages.
    """
    message = "Authentication credentials were not provided or are invalid."

    def has_permission(self, request, view):
        return bool(
            request.user 
            and request.user.is_authenticated 
            and request.user.is_active
        )


class IsStaffUser(BasePermission):
    """Django is_staff on an active account. The only staff notion in the product (no separate role)."""
    message = 'Staff access required.'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_staff)
