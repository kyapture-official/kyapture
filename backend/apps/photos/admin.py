from django.contrib import admin
from .models import Photo


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = [
        'original_name', 
        'gallery', 
        'formatted_file_size', 
        'dimensions', 
        'order', 
        'created_at'
    ]
    
    list_filter = ['created_at']
    
    search_fields = [
        'original_name', 
        'gallery__title', 
        'gallery__photographer__email'
    ]
    
    # Performance Optimization: INNER JOIN query execution [1.1.2]
    list_select_related = ['gallery', 'gallery__photographer']
    
    # Performance Isolation: Prevents RAM crashes during ForeignKey rendering [1.1.2]
    raw_id_fields = ['gallery']
    
    # Protection Guard: Makes auto-generated metadata un-editable to admins [1.1.2]
    readonly_fields = [
        'id', 
        'file_size', 
        'width', 
        'height', 
        'original_name', 
        'created_at', 
        'updated_at'
    ]

    # Custom Computed Display Helpers
    @admin.display(description='File Size')
    def formatted_file_size(self, obj):
        """Converts raw bytes to human-readable format inside admin tables [1.1.2]."""
        size_in_bytes = obj.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_in_bytes < 1024.0:
                return f"{size_in_bytes:.2f} {unit}"
            size_in_bytes /= 1024.0
        return f"{size_in_bytes:.2f} TB"

    @admin.display(description='Dimensions (WxH)')
    def dimensions(self, obj):
        """Displays dimensions as a clean layout (e.g., 6000 x 4000 px)."""
        return f"{obj.width} x {obj.height} px"