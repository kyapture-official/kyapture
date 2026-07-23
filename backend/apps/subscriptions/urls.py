from django.urls import path
from .views import (
    PlanListView, 
    MySubscriptionView,
    ManualPaymentView,      
    AdminPendingPaymentsView,  
    AdminPaymentReviewView,   
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

    # ── Admin Pending Review Queue (Admin Staff Only) ─────────────────────────
    path('admin/payments/', AdminPendingPaymentsView.as_view(), name='admin-pending-payments'),

    # ── Admin Decision & Activation Dispatcher (Admin Staff Only) ──────────────
    path('payments/<uuid:payment_id>/review/', AdminPaymentReviewView.as_view(), name='admin-payment-review'),
]