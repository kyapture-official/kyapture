#C:\Users\LENOVO\Desktop\kyapture\backend\apps\galleries\urls.py
from django.urls import path
from .views import (
    GalleryListCreateView, 
    GalleryDetailView,
    GallerySearchView, 
    DashboardStatsView,
    GalleryPublishView,      
    GallerySetPasswordView   
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

    # Route: GET/PUT/DELETE /api/v1/galleries/{slug}/
    path(
        '<slug:slug>/',
        GalleryDetailView.as_view(),
        name='gallery-detail'
    ),
]