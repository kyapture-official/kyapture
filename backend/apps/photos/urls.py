# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/urls.py
from django.urls import path
from .views import (
    PhotoListUploadView,
    PhotoDetailView,
    PhotoBulkDeleteView,
    PhotoReorderView,
    PhotoBatchStatusView,
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
    
    # Route: GET batched processing-status lookup for polling
    # (Phase 2 — replaces the old per-asset polling storm)
    path(
        '<slug:gallery_slug>/status/',
        PhotoBatchStatusView.as_view(),
        name='photo-batch-status'
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