# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/urls.py
from django.urls import path
from .views import (
    PublicGalleryView,
    GalleryUnlockView,
    PublicDownloadAccessView,
    PublicGalleryDownloadView,
    PublicGalleryDirectDownloadView,
    PublicDownloadJobStatusView,
    PublicDownloadJobFileView,
    PublicPhotoDownloadView,
    PublicPhotographerPortfolioView,
    PublicVideoStreamView,
    PublicGalleryPhotosView,
    GalleryFavoritesView,
    GalleryFavoriteListsView,
    GalleryFavoriteListDetailView,
)

urlpatterns = [
    # ── 1. Suffixed Routes First (Prevents routing collisions) ────────────────
    
    # Route: POST /api/v1/public/{username}/{slug}/unlock/
    path(
        '<str:username>/<slug:slug>/unlock/',
        GalleryUnlockView.as_view(),
        name='gallery-unlock'
    ),

    # Route: POST /api/v1/public/{username}/{slug}/download-access/
    # Explicit-download step one: verifies PIN/email, returns a short-lived
    # download_token. Never called while merely browsing a gallery.
    path(
        '<str:username>/<slug:slug>/download-access/',
        PublicDownloadAccessView.as_view(),
        name='gallery-download-access'
    ),

    # Route: POST /api/v1/public/{username}/{slug}/download/
    path(
        '<str:username>/<slug:slug>/download/',
        PublicGalleryDownloadView.as_view(),
        name='gallery-download'
    ),

    # Route: GET /api/v1/public/{username}/{slug}/download-jobs/{job_id}/
    # Status of a background-prepared gallery/set ZIP (+ signed file URLs when ready).
    path(
        '<str:username>/<slug:slug>/download-jobs/<uuid:job_id>/',
        PublicDownloadJobStatusView.as_view(),
        name='gallery-download-job-status'
    ),

    # Route: GET /api/v1/public/{username}/{slug}/download-jobs/{job_id}/files/{index}/?file_token=...
    path(
        '<str:username>/<slug:slug>/download-jobs/<uuid:job_id>/files/<int:index>/',
        PublicDownloadJobFileView.as_view(),
        name='gallery-download-job-file'
    ),

    # Route: GET /api/v1/public/{username}/{slug}/download-all/ — RETIRED (410):
    # gallery downloads are prepared in the background now.
    path(
        '<str:username>/<slug:slug>/download-all/',
        PublicGalleryDirectDownloadView.as_view(),
        name='gallery-download-all'
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

    # Route: GET /api/v1/public/{username}/{slug}/photos/?page=2
    # Phase 2 large-gallery pagination continuation — see PublicGalleryPhotosView.
    path(
        '<str:username>/<slug:slug>/photos/',
        PublicGalleryPhotosView.as_view(),
        name='public-gallery-photos'
    ),

    # Routes: the visitor's own favorite lists (listed BEFORE the plain favorites route)
    path(
        '<str:username>/<slug:slug>/favorites/lists/<uuid:list_id>/',
        GalleryFavoriteListDetailView.as_view(),
        name='public-gallery-favorite-list'
    ),
    path(
        '<str:username>/<slug:slug>/favorites/lists/',
        GalleryFavoriteListsView.as_view(),
        name='public-gallery-favorite-lists'
    ),

    # Route: GET/POST/DELETE /api/v1/public/{username}/{slug}/favorites/
    path(
        '<str:username>/<slug:slug>/favorites/',
        GalleryFavoritesView.as_view(),
        name='public-gallery-favorites'
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
