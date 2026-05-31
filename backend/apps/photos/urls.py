from django.urls import path
from .views import PhotoListUploadView, PhotoDetailView

urlpatterns = [
    # Route: GET list / POST upload bulk/single images [1.1.2]
    path(
        '<slug:gallery_slug>/upload/', 
        PhotoListUploadView.as_view(), 
        name='photo-upload'
    ),
    path(
        '<slug:gallery_slug>/', 
        PhotoListUploadView.as_view(), 
        name='photo-list'
    ),
    # Route: GET / DELETE individual photo [1.1.2]
    path(
        'photo/<uuid:photo_id>/', 
        PhotoDetailView.as_view(), 
        name='photo-detail'
    ),
]