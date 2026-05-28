from rest_framework import status
from rest_framework.exceptions import PermissionDenied
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


class IsSubscribed(BasePermission):
    """
    Enforces that the photographer has an active, paid tier plan.
    Administrative staff and superusers bypass this check for testing [1.1.2].
    """
    message = "An active subscription plan is required to access this feature."

    def has_permission(self, request, view):
        # 1. Enforce active authentication first
        if not request.user or not request.user.is_authenticated:
            return False
        
        # 2. Master Bypass: Allow staff/superusers to bypass billing checks for support [1.1.2]
        if request.user.is_superuser or request.user.is_staff:
            return True
            
        # 3. Verify payment flag status
        if not request.user.is_active_plan:
            # Raise a custom detailed exception containing a machine-readable code
            raise PermissionDenied(
                detail={
                    "error": self.message,
                    "code": "subscription_required"
                },
                code=status.HTTP_403_FORBIDDEN
            )
            
        return True