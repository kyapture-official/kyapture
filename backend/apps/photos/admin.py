# C:\Users\LENOVO\Desktop\kyapture\backend\apps\photos\admin.py

from django.contrib import admin
from .models import MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = [
        'original_name', 
        'gallery', 
        'media_type',  # Identifies whether the asset is an image or a video
        'formatted_file_size', 
        'dimensions', 
        'processing_status',  # Displays transcoding states for videos (null for images)
        'order', 
        'created_at'
    ]
    
    list_filter = ['media_type', 'processing_status', 'created_at']
    
    search_fields = [
        'original_name', 
        'gallery__title', 
        'gallery__photographer__email'
    ]
    
    # Performance Optimization: INNER JOIN query execution to prevent N+1 queries
    list_select_related = ['gallery', 'gallery__photographer']
    
    # Performance Isolation: Prevents RAM crashes during ForeignKey rendering
    raw_id_fields = ['gallery']
    
    # Protection Guard: Makes auto-generated metadata un-editable to admins
    readonly_fields = [
        'id', 
        'file_size', 
        'width', 
        'height', 
        'original_name',
        'duration',
        'processing_status',
        'created_at', 
        'updated_at'
    ]

    # Custom Computed Display Helpers
    @admin.display(description='File Size')
    def formatted_file_size(self, obj):
        """Converts raw bytes to human-readable format inside admin tables."""
        size_in_bytes = obj.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_in_bytes < 1024.0:
                return f"{size_in_bytes:.2f} {unit}"
            size_in_bytes /= 1024.0
        return f"{size_in_bytes:.2f} TB"

    @admin.display(description='Dimensions (WxH)')
    def dimensions(self, obj):
        """Displays dimensions as a clean layout, safely handling null cases."""
        if obj.width and obj.height:
            return f"{obj.width} x {obj.height} px"
        return "N/A"