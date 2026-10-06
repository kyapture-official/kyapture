#C:\Users\LENOVO\Desktop\kyapture\backend\apps\galleries\urls.py
from django.urls import path
from .views import (
    GalleryListCreateView,
    GalleryDetailView,
    GallerySearchView,
    DashboardStatsView,
    GalleryPublishView,
    GallerySetPasswordView,
    GallerySetDownloadPinView,
    GalleryFavoriteActivityView,
    GalleryDownloadLogsView,
    TypographyStylesView,
)

urlpatterns = [
    # Route: GET/POST /api/v1/galleries/ 
    path(
        '',
        GalleryListCreateView.as_view(),
        name='gallery-list-create'
    ),
    
    # Static Route: GET /api/v1/galleries/search/?q=<query>
    path(
        'search/',
        GallerySearchView.as_view(),
        name='gallery-search'
    ),
    
    # Static Route: GET /api/v1/galleries/typography-styles/
    path(
        'typography-styles/',
        TypographyStylesView.as_view(),
        name='typography-styles'
    ),

    # Static Route: GET /api/v1/galleries/dashboard/stats/
    path(
        'dashboard/stats/',
        DashboardStatsView.as_view(),
        name='dashboard-stats'
    ),
    
    
    path(
        '<slug:slug>/publish/',
        GalleryPublishView.as_view(),
        name='gallery-publish'
    ),
    path(
        '<slug:slug>/set-password/',
        GallerySetPasswordView.as_view(),
        name='gallery-set-password'
    ),
    path(
        '<slug:slug>/set-download-pin/',
        GallerySetDownloadPinView.as_view(),
        name='gallery-set-download-pin'
    ),
    path(
        '<slug:slug>/favorites/',
        GalleryFavoriteActivityView.as_view(),
        name='gallery-favorite-activity'
    ),
    path(
        '<slug:slug>/download-logs/',
        GalleryDownloadLogsView.as_view(),
        name='gallery-download-logs'
    ),

    # Route: GET/PUT/DELETE /api/v1/galleries/{slug}/
    path(
        '<slug:slug>/',
        GalleryDetailView.as_view(),
        name='gallery-detail'
    ),
]