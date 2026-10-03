# C:/Users/LENOVO/Desktop/kyapture/backend/config/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from apps.users.views import TotalUsersView 


def health_check(request):
    """Unauthenticated liveness/readiness probe for the container."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unhealthy"}, status=503)
    return JsonResponse({"status": "ok"})

# Master URL Routing Table
urlpatterns = [
    path('health/', health_check, name='health-check'),
    # Built-in Django visual administration panel
    path('admin/', admin.site.urls),
    path('api/total-users', TotalUsersView.as_view(), name='total-users'),
    # Version 1.0 SaaS API Endpoints [1.1.2]
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/notifications/', include('apps.users.notification_urls')),
    path('api/v1/galleries/', include('apps.galleries.urls')),
    path('api/v1/photos/', include('apps.photos.urls')),
    path('api/v1/public/', include('apps.clients.urls')),
    path('api/v1/subscriptions/', include('apps.subscriptions.urls')),
]

# Strict Development Safeguard: Serve user uploads locally ONLY in Debug mode [1.1.2]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
