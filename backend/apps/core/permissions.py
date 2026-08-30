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

