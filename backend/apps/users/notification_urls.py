# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/notification_urls.py
from django.urls import path

from .notification_api import (
    NotificationListView,
    NotificationReadAllView,
    NotificationReadView,
    NotificationUnreadCountView,
)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('read-all/', NotificationReadAllView.as_view(), name='notification-read-all'),
    path('<uuid:notification_id>/read/', NotificationReadView.as_view(), name='notification-read'),
]
