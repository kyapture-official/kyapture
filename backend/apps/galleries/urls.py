from django.urls import path
from .views import GalleryListCreateView, GalleryDetailView

urlpatterns = [
    # Route: GET/POST /api/v1/galleries/ [1.1.2]
    path(
        '',
        GalleryListCreateView.as_view(),
        name='gallery-list-create'
    ),
    # Route: GET/PUT/DELETE /api/v1/galleries/{slug}/ [1.1.2]
    path(
        '<slug:slug>/',
        GalleryDetailView.as_view(),
        name='gallery-detail'
    ),
]