from django.urls import path
from .views import PublicGalleryView, GalleryUnlockView

urlpatterns = [
    # Route: GET /api/v1/public/{username}/{slug}/ [1.1.2]
    # Replaces the standard /api/v1/public/{slug}/ to prevent database duplicate crashes
    path(
        '<str:username>/<slug:slug>/',
        PublicGalleryView.as_view(),
        name='public-gallery'
    ),

    # Route: POST /api/v1/public/{username}/{slug}/unlock/ [1.1.2]
    path(
        '<str:username>/<slug:slug>/unlock/',
        GalleryUnlockView.as_view(),
        name='gallery-unlock'
    ),
]