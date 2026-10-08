# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/admin.py
from django import forms
from django.contrib import admin
from django.core.files.uploadedfile import UploadedFile
from apps.core.branding import InvalidLogo, sanitize_image_upload
from .models import (
    LifecycleSettings, ManualPayment, PaymentInstructions, SubscriptionPlan, UploadLimits, UserSubscription,
)


@admin.register(SubscriptionPlan)
class PlanAdmin(admin.ModelAdmin):
    """The owner edits plans here: changes show on Billing immediately (no deploy)."""
    list_display = [
        'name', 'key', 'price', 'storage_gb', 'max_collections', 'video_minutes',
        'original_download', 'watermark', 'branding', 'is_active',
    ]
    list_editable = ['price', 'storage_gb', 'max_collections', 'video_minutes', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'key']
    fieldsets = [
        (None, {'fields': ['name', 'key', 'price', 'is_active']}),
        ('Limits (empty = unlimited; video minutes: 0 = no video)', {'fields': ['storage_gb', 'max_collections', 'video_minutes']}),
        ('Features', {'fields': ['original_download', 'watermark', 'branding']}),
    ]

    def get_readonly_fields(self, request, obj=None):
        # The key is how code finds the Free tier; freeze it once a row exists.
        return ['key'] if obj else []

    def has_delete_permission(self, request, obj=None):
        # The Free-tier row backs every unpaid account — never deletable.
        if obj is not None and obj.is_free:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(UploadLimits)
class UploadLimitsAdmin(admin.ModelAdmin):
    """The one row of per-file upload limits; read at request time, so an edit applies to the next upload."""
    list_display = ['__str__', 'max_image_mb', 'max_image_pixels', 'max_video_mb', 'updated_at']
    fields = ['max_image_mb', 'max_image_pixels', 'max_video_mb']

    def changelist_view(self, request, extra_context=None):
        UploadLimits.load()  # the row always exists, so there is always something to open
        return super().changelist_view(request, extra_context)

    def get_object(self, request, object_id, from_field=None):
        UploadLimits.load()
        return super().get_object(request, object_id, from_field)

    def has_add_permission(self, request):
        return not UploadLimits.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LifecycleSettings)
class LifecycleSettingsAdmin(admin.ModelAdmin):
    """The one row that tunes the daily subscription job (7.5-C); read at each run, so an edit applies to the next."""
    list_display = ['__str__', 'reminder_days', 'grace_days', 'updated_at']
    fields = ['reminder_days', 'grace_days']

    def changelist_view(self, request, extra_context=None):
        LifecycleSettings.load()  # the row always exists, so there is always something to open
        return super().changelist_view(request, extra_context)

    def get_object(self, request, object_id, from_field=None):
        LifecycleSettings.load()
        return super().get_object(request, object_id, from_field)

    def has_add_permission(self, request):
        return not LifecycleSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserSubscription)
class SubAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'status', 'starts_at', 'expires_at']
    list_filter = ['status', 'expires_at']
    search_fields = ['user__email', 'user__username', 'plan__name']
    
    # Scale Protection: JOINs relationship queries to avoid N+1 bottlenecks [1.1.2]
    list_select_related = ['user', 'plan']
    
    # Scale Protection: Prevents dropdown lists from freezing the browser [1.1.2]
    raw_id_fields = ['user', 'plan']
    
    # Security: Auditable parameters cannot be modified after registration [1.1.2]
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ManualPayment)
class PaymentAdmin(admin.ModelAdmin):
    """
    Read-only on purpose (7.5-B). A payment is approved or rejected in the staff page only: that is the
    one path that locks the row, applies the plan, writes the audit row and tells the user. A status
    edited here would skip all of it.
    """
    list_display = ['id_prefix', 'user', 'plan', 'amount', 'currency', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['id', 'user__email', 'user__username', 'plan__name']
    list_select_related = ['user', 'plan', 'verified_by']
    raw_id_fields = ['user', 'plan', 'verified_by']

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in ManualPayment._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Payment ID')
    def id_prefix(self, obj):
        """Displays a clean truncated UUID (e.g., Payment #9b1deb4d)."""
        return f"#{str(obj.id)[:8]}"


class PaymentInstructionsForm(forms.ModelForm):
    class Meta:
        model = PaymentInstructions
        fields = ['account_name', 'esewa_id', 'bank_name', 'bank_account_number', 'bank_branch', 'qr_image', 'note']

    def clean_qr_image(self):
        image = self.cleaned_data.get('qr_image')
        # A new upload is validated by what Pillow can decode and re-encoded (no metadata, no
        # trailing payload, no SVG); an existing file or a cleared box passes through.
        if isinstance(image, UploadedFile):
            try:
                return sanitize_image_upload(image, label='QR image', basename='qr')
            except InvalidLogo as error:
                raise forms.ValidationError(str(error))
        return image


@admin.register(PaymentInstructions)
class PaymentInstructionsAdmin(admin.ModelAdmin):
    """The one row shown on the Billing page: public information only, never a secret."""
    form = PaymentInstructionsForm
    list_display = ['__str__', 'account_name', 'esewa_id', 'bank_name', 'updated_at']

    def changelist_view(self, request, extra_context=None):
        PaymentInstructions.load()  # the row always exists, so there is always something to open
        return super().changelist_view(request, extra_context)

    def get_object(self, request, object_id, from_field=None):
        PaymentInstructions.load()
        return super().get_object(request, object_id, from_field)

    def has_add_permission(self, request):
        return not PaymentInstructions.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
