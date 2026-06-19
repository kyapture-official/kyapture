from django.urls import path
from .views import (
    PhotoListUploadView,
    PhotoDetailView,
    PhotoBulkDeleteView,
    PhotoReorderView,
)

urlpatterns = [
    # Route: POST bulk/single image uploads
    path(
        '<slug:gallery_slug>/upload/', 
        PhotoListUploadView.as_view(), 
        name='photo-upload'
    ),
    
    # Route: POST bulk deletion of assets
    path(
        '<slug:gallery_slug>/delete-bulk/', 
        PhotoBulkDeleteView.as_view(), 
        name='photo-bulk-delete'
    ),
    
    # Route: PATCH bulk reordering coordinates (drag-and-drop)
    path(
        '<slug:gallery_slug>/reorder/', 
        PhotoReorderView.as_view(), 
        name='photo-reorder'
    ),
    
    # Route: GET list of gallery assets (images/videos)
    path(
        '<slug:gallery_slug>/', 
        PhotoListUploadView.as_view(), 
        name='photo-list'
    ),
    
    # Route: GET metadata / DELETE individual asset
    path(
        'photo/<uuid:photo_id>/', 
        PhotoDetailView.as_view(), 
        name='photo-detail'
    ),
]