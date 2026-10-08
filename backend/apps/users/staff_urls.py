# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/staff_urls.py
from django.urls import path

from apps.subscriptions.staff_payments import (
    StaffPaymentApproveView, StaffPaymentListView, StaffPaymentProofLinkView, StaffPaymentProofView,
    StaffPaymentRejectView,
)

from .staff_api import (
    StaffAuditLogView, StaffUserListView, StaffUserReactivateView, StaffUserSuspendView,
)

urlpatterns = [
    path('users/', StaffUserListView.as_view(), name='staff-users'),
    path('users/<uuid:user_id>/suspend/', StaffUserSuspendView.as_view(), name='staff-user-suspend'),
    path('users/<uuid:user_id>/reactivate/', StaffUserReactivateView.as_view(), name='staff-user-reactivate'),
    path('audit/', StaffAuditLogView.as_view(), name='staff-audit'),
    # 7.5-B: manual payment review
    path('payments/', StaffPaymentListView.as_view(), name='staff-payments'),
    path('payments/<uuid:payment_id>/approve/', StaffPaymentApproveView.as_view(), name='staff-payment-approve'),
    path('payments/<uuid:payment_id>/reject/', StaffPaymentRejectView.as_view(), name='staff-payment-reject'),
    path('payments/<uuid:payment_id>/proof-link/', StaffPaymentProofLinkView.as_view(), name='staff-payment-proof-link'),
    path('payments/<uuid:payment_id>/proof/', StaffPaymentProofView.as_view(), name='staff-payment-proof'),
]
