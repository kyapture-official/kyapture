# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


class KyaptureUserAdmin(UserAdmin):
    def user_change_password(self, request, id, form_url=''):
        """
        7-C: a password a staff member sets here ends every session of the
        account and tells the owner by email, like a reset or a change does.
        Django saves the password and redirects only when the form is valid.
        """
        response = super().user_change_password(request, id, form_url)
        if request.method == 'POST' and response.status_code == 302:
            from .password_reset import queue_password_changed_email
            from .utils import revoke_all_sessions

            user = self.get_object(request, id)
            if user is not None:
                revoke_all_sessions(user)
                queue_password_changed_email(user, 'admin')
        return response


admin.site.register(User, KyaptureUserAdmin)
