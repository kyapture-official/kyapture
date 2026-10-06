# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/admin.py
from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription, ManualPayment, UploadLimits


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
    list_display = ['id_prefix', 'user', 'plan', 'amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['id', 'user__email', 'user__username', 'plan__name']
    
    # Performance JOIN optimizations [1.1.2]
    list_select_related = ['user', 'plan', 'verified_by']
    
    # Scale lookups [1.1.2]
    raw_id_fields = ['user', 'plan', 'verified_by']
    
    # Audit Security: Freeze financial parameters once submitted to prevent internal fraud [1.1.2]
    readonly_fields = [
        'id', 
        'user', 
        'plan', 
        'amount', 
        'payment_proof', 
        'created_at', 
        'updated_at'
    ]

    @admin.display(description='Payment ID')
    def id_prefix(self, obj):
        """Displays a clean truncated UUID (e.g., Payment #9b1deb4d)."""
        return f"#{str(obj.id)[:8]}"