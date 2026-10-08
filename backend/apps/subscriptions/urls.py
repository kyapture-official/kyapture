# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/urls.py
from django.urls import path
from .views import (
    PlanListView, 
    MySubscriptionView,
    ManualPaymentView,
    PaymentInstructionsView,
)

urlpatterns = [
    # ── Pricing Plans (Public Access) ─────────────────────────────────────────
    path('plans/', PlanListView.as_view(), name='subscription-plans'),

    # ── Subscription Status & Usage Metrics (Photographer) ────────────────────
    path('my-subscription/', MySubscriptionView.as_view(), name='my-subscription'),
    
    # Self-Healing Route: Intercepts David's broken GET '/subscriptions/me/' calls and maps them to your active view
    path('me/', MySubscriptionView.as_view(), name='subscription-me-redirect'),

    # ── Manual Payment Auditing & Uploads (Photographer) ──────────────────────
    # Unified endpoint: handles both GET listing history and POST receipt uploads
    path('payments/', ManualPaymentView.as_view(), name='payment-list'),

    # Where to send the money: the admin-edited PaymentInstructions row
    path('payment-instructions/', PaymentInstructionsView.as_view(), name='payment-instructions'),

    # The staff review queue, approve / reject and the proof link live under
    # /api/v1/staff/payments/ (apps/subscriptions/staff_payments.py, 7.5-B).
]
