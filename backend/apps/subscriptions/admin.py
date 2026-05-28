from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription, ManualPayment


@admin.register(SubscriptionPlan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'max_galleries', 'max_photos_per_gallery', 'storage_gb', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']


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