# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/urls.py
from django.urls import path
from .views import (
    PublicGalleryView, 
    GalleryUnlockView, 
    PublicGalleryDownloadView,
    PublicPhotoDownloadView,
    PublicPhotographerPortfolioView,
    PublicVideoStreamView, 
)

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

path(
        '<str:username>/<slug:slug>/video/<uuid:asset_id>/stream/',
        PublicVideoStreamView.as_view(),
        name='public-video-stream'
    ),


    path(
        '<str:username>/<slug:slug>/photo/<uuid:photo_id>/download/',
        PublicPhotoDownloadView.as_view(),
        name='public-photo-download'
    ),


    # ── 2. Plain Dynamic Catch-All Route Last ─────────────────────────────────
    
    # Route: GET /api/v1/public/{username}/{slug}/
    path(
        '<str:username>/<slug:slug>/',
        PublicGalleryView.as_view(),
        name='public-gallery'
    ),
    
    # ── 3. Photographer Public Portfolio Homepage (Single Parameter) ──────────
    
    # Route: GET /api/v1/public/{username}/
    path(
        '<str:username>/',
        PublicPhotographerPortfolioView.as_view(),
        name='public-portfolio'
    ),
]