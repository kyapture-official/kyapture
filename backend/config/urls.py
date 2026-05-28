from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

# Master URL Routing Table
urlpatterns = [
    # Built-in Django visual administration panel
    path('admin/', admin.site.urls),
    
    # Version 1.0 SaaS API Endpoints [1.1.2]
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/galleries/', include('apps.galleries.urls')),
    path('api/v1/photos/', include('apps.photos.urls')),
    path('api/v1/public/', include('apps.clients.urls')),
    path('api/v1/subscriptions/', include('apps.subscriptions.urls')),
]

# Strict Development Safeguard: Serve user uploads locally ONLY in Debug mode [1.1.2]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)