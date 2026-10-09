# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from . import audit
from .models import AccountSettings, StaffAuditLog, User


class KyaptureUserAdmin(UserAdmin):
    def user_change_password(self, request, id, form_url=''):
        """
        7-C: a password a staff member sets here ends every session of the account and
        tells the owner by email, like a reset or a change does. 7.5-A: and it is audited.
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
                audit.record_event(
                    audit.Action.PASSWORD_CHANGE, actor=request.user, target=user, request=request, reason='admin',
                )
        return response

    def save_model(self, request, obj, form, change):
        """7.5-A: switching an account off or on here is a suspension / reactivation, so it is audited too."""
        before = User.objects.filter(pk=obj.pk).values_list('is_active', flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        if before is not None and before != obj.is_active:
            action = audit.Action.REACTIVATE if obj.is_active else audit.Action.SUSPEND
            if not obj.is_active:
                from .utils import revoke_all_sessions
                revoke_all_sessions(obj)
            else:       # a reason / date left by an earlier suspension in the staff area no longer applies
                User.objects.filter(pk=obj.pk).update(suspended_at=None, suspension_reason='')
            audit.record_event(action, actor=request.user, target=obj, request=request, reason='django admin')


@admin.register(AccountSettings)
class AccountSettingsAdmin(admin.ModelAdmin):
    """The one row that tunes account deletion (7.5-E); read at each deletion request, so an edit applies to the next."""
    list_display = ['__str__', 'deletion_cooling_off_days', 'updated_at']
    fields = ['deletion_cooling_off_days']

    def changelist_view(self, request, extra_context=None):
        AccountSettings.load()  # the row always exists, so there is always something to open
        return super().changelist_view(request, extra_context)

    def get_object(self, request, object_id, from_field=None):
        AccountSettings.load()
        return super().get_object(request, object_id, from_field)

    def has_add_permission(self, request):
        return not AccountSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StaffAuditLog)
class StaffAuditLogAdmin(admin.ModelAdmin):
    """Read only: nothing here adds, edits or deletes a row (the model and the database refuse it too)."""
    list_display = ('created_at', 'action', 'actor_email', 'target_email', 'ip', 'reason')
    list_filter = ('action',)
    ordering = ('-created_at', '-id')
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}


admin.site.register(User, KyaptureUserAdmin)
