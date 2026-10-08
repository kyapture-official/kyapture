# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/staff_urls.py
from django.urls import path

from .staff_api import (
    StaffAuditLogView, StaffUserListView, StaffUserReactivateView, StaffUserSuspendView,
)

urlpatterns = [
    path('users/', StaffUserListView.as_view(), name='staff-users'),
    path('users/<uuid:user_id>/suspend/', StaffUserSuspendView.as_view(), name='staff-user-suspend'),
    path('users/<uuid:user_id>/reactivate/', StaffUserReactivateView.as_view(), name='staff-user-reactivate'),
    path('audit/', StaffAuditLogView.as_view(), name='staff-audit'),
]
