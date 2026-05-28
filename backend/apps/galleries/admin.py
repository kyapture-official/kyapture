from django.contrib import admin
from .models import Gallery


@admin.register(Gallery)
class GalleryAdmin(admin.ModelAdmin):
    # Expanded displays for better business auditing
    list_display = [
        'title', 
        'photographer', 
        'slug', 
        'is_published', 
        'allow_download', 
        'is_password_protected',
        'created_at'
    ]
    
    list_filter = ['is_published', 'allow_download', 'is_password_protected']
    
    # Enables quick admin searching across strings, emails, and subdomains
    search_fields = [
        'title', 
        'slug', 
        'photographer__email', 
        'photographer__username'
    ]
    
    # JavaScript auto-completion on creation
    prepopulated_fields = {'slug': ('title',)}
    
    # Performance Optimization: INNER JOIN relations in single query [1.1.2]
    list_select_related = ['photographer', 'cover_photo']
    
    # Performance Isolation: Replaces database-heavy select dropdowns [1.1.2]
    raw_id_fields = ['photographer', 'cover_photo']