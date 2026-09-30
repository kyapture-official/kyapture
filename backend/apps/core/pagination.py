# C:/Users/LENOVO/Desktop/kyapture/backend/apps/core/pagination.py
from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class LargeResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class GalleryMediaPagination(PageNumberPagination):
    """
    Phase 2 (large-gallery performance): shared pagination for gallery
    photo/video grids — both the photographer's own dashboard gallery
    manager and the public client-facing gallery. 60 is a "thumbnail
    grid page" — enough to fill several screens at typical column counts
    (2-5 columns) before the client needs to scroll for more, without
    ever shipping a 500/1000/2000-asset gallery as one giant JSON
    response or signing/serializing URLs for media nobody has scrolled
    to yet.
    """
    page_size = 60
    page_size_query_param = 'page_size'
    max_page_size = 150
