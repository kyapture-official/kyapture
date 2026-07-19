from django.urls import path
from .views import PublicGalleryView, GalleryUnlockView, PublicGalleryDownloadView

urlpatterns = [
    # ── 1. Suffixed Routes First (Prevents routing collisions) ────────────────
    
    # Route: POST /api/v1/public/{username}/{slug}/unlock/
    path(
        '<str:username>/<slug:slug>/unlock/',
        GalleryUnlockView.as_view(),
        name='gallery-unlock'
    ),

    # Route: POST /api/v1/public/{username}/{slug}/download/
    path(
        '<str:username>/<slug:slug>/download/',
        PublicGalleryDownloadView.as_view(),
        name='gallery-download'
    ),

    # ── 2. Plain Dynamic Catch-All Route Last ─────────────────────────────────
    
    # Route: GET /api/v1/public/{username}/{slug}/
    path(
        '<str:username>/<slug:slug>/',
        PublicGalleryView.as_view(),
        name='public-gallery'
    ),
]