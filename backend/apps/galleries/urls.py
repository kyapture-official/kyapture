from django.urls import path
from .views import GalleryListCreateView, GalleryDetailView, DashboardStatsView

urlpatterns = [
    # Route: GET/POST /api/v1/galleries/ [1.1.2]
    path(
        '',
        GalleryListCreateView.as_view(),
        name='gallery-list-create'
    ),
    
    # Static Route: GET /api/v1/galleries/dashboard/stats/
    path(
        'dashboard/stats/',
        DashboardStatsView.as_view(),
        name='dashboard-stats'
    ),
    
    # Route: GET/PUT/DELETE /api/v1/galleries/{slug}/ [1.1.2]
    path(
        '<slug:slug>/',
        GalleryDetailView.as_view(),
        name='gallery-detail'
    ),
]