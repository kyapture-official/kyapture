# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/urls.py
from django.urls import path
from .views import (
    PhotoListUploadView,
    PhotoDetailView,
    PhotoBulkDeleteView,
    PhotoReorderView,
    PhotoBatchStatusView,
    VideoPreflightView,
    PhotoSetListCreateView,
    PhotoSetDetailView,
    PhotoSetReorderView,
    PhotoSetAssignView,
    PhotoFavoriteView,
    PhotographerFavoritesView,
)

urlpatterns = [
    # Route: POST pre-upload video-length check. Listed before the
    # '<slug:gallery_slug>/' catch-all, which would otherwise take this path.
    path(
        'video-preflight/',
        VideoPreflightView.as_view(),
        name='video-preflight'
    ),

    # ── Suffixed routes first (prevents routing collisions with the
    #    plain '<slug:gallery_slug>/' catch-all at the bottom) ────────────

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

    # ── Photo Sets (Phase 3) ──────────────────────────────────────────────
    path(
        '<slug:gallery_slug>/move/',
        PhotoSetAssignView.as_view(),
        name='photo-set-move'
    ),
    path(
        '<slug:gallery_slug>/sets/reorder/',
        PhotoSetReorderView.as_view(),
        name='photo-set-reorder'
    ),
    path(
        '<slug:gallery_slug>/sets/<uuid:set_id>/',
        PhotoSetDetailView.as_view(),
        name='photo-set-detail'
    ),
    path(
        '<slug:gallery_slug>/sets/',
        PhotoSetListCreateView.as_view(),
        name='photo-set-list'
    ),

    # Route: GET list of gallery assets (images/videos)
    path(
        '<slug:gallery_slug>/',
        PhotoListUploadView.as_view(),
        name='photo-list'
    ),

    # Route: PUT the photographer's own favorite mark on one asset
    path(
        'photo/<uuid:photo_id>/favorite/',
        PhotoFavoriteView.as_view(),
        name='photo-favorite'
    ),

    # Route: GET every favorited photo of the signed-in photographer (Favorites page)
    path(
        'favorites/all/',
        PhotographerFavoritesView.as_view(),
        name='photographer-favorites'
    ),

    # Route: GET metadata / DELETE individual asset
    path(
        'photo/<uuid:photo_id>/',
        PhotoDetailView.as_view(),
        name='photo-detail'
    ),
]
