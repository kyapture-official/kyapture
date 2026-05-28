from django.contrib import admin
from .models import ClientSession


@admin.register(ClientSession)
class ClientSessionAdmin(admin.ModelAdmin):
    # Comprehensive layout for auditing anonymous client logins
    list_display = [
        'id', 
        'gallery', 
        'email', 
        'ip_address', 
        'has_download_access', 
        'created_at'
    ]
    
    list_filter = ['has_download_access', 'created_at']
    
    # Allows admins to search sessions by email, IP, or parent gallery parameters
    search_fields = [
        'email', 
        'ip_address', 
        'gallery__title', 
        'gallery__photographer__email'
    ]
    
    # Performance Optimization: INNER JOIN relations in single query [1.1.2]
    list_select_related = ['gallery', 'gallery__photographer']
    
    # Scale safety: Replaces database-heavy select dropdowns [1.1.2]
    raw_id_fields = ['gallery']
    
    # Protection Guard: Freezes cryptographic session tokens and audit parameters [1.1.2]
    readonly_fields = [
        'id', 
        'access_token', 
        'ip_address', 
        'created_at', 
        'updated_at'
    ]
    @admin.display(description='Session ID')
    def id_prefix(self, obj):
        """Displays a clean truncated UUID."""
        return f"#{str(obj.id)[:8]}"