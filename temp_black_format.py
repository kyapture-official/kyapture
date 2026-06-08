# backend/apps/subscriptions/urls.py
from django.urls import path
from .views import (
    PlanListView, 
    MySubscriptionView,
    ManualPaymentSubmitView, 
    ManualPaymentListView,
    AdminPaymentApprovalView,
)

urlpatterns = [
    # Pricing Plans (Public)
    path('plans/', PlanListView.as_view(), name='subscription-plans'),

    # Current Subscription Status (Photographer)
    path('my-subscription/', MySubscriptionView.as_view(), name='my-subscription'),

    # Submit Payment Screenshot (Photographer) [1.1.2]
    path('pay/', ManualPaymentSubmitView.as_view(), name='payment-submit'),

    # Payment Auditing History (Photographer / Admin Queue) [1.1.2]
    path('payments/', ManualPaymentListView.as_view(), name='payment-list'),

    # Admin Review and Plan Activation (Admin Only) [1.1.2]
    path('payments/<uuid:payment_id>/review/', AdminPaymentApprovalView.as_view(), name='payment-review'),
]