# C:/Users/LENOVO/Desktop/kyapture/backend/apps/galleries/admin.py
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

    # 7-B (SEC-15): the bcrypt hashes of the gallery password and download PIN
    # are never shown or editable here; the photographer sets them in the app
    # (set-password / set-download-pin), which also ends old sessions.
    exclude = ['password_hash', 'download_pin_hash']

    # 7G (7R-2 R4): design_settings is also written by visitors (the "Limit PIN
    # Usage" counter) and by the owner's settings screen, each under a row lock.
    # The admin shows it read-only and writes back only the fields its form
    # edits, so a save never restores the settings as they were when the form
    # (or this request) loaded the row.
    readonly_fields = ['design_settings']

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        concrete = {field.name for field in obj._meta.concrete_fields}
        obj.save(update_fields=[name for name in form.cleaned_data if name in concrete])