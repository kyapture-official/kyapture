from django.urls import path
from .views import (
    PlanListView, 
    MySubscriptionView,
    ManualPaymentSubmitView, 
    ManualPaymentListView,
    AdminPendingPaymentsView,  # Integrated Day 3: Administrative Pending Queue
    AdminPaymentReviewView,    # Integrated Day 3: Stateful Administrative Approval View
)

urlpatterns = [
    # ── Pricing Plans (Public Access) ─────────────────────────────────────────
    path('plans/', PlanListView.as_view(), name='subscription-plans'),

    # ── Subscription Status & Usage Metrics (Photographer) ────────────────────
    path('my-subscription/', MySubscriptionView.as_view(), name='my-subscription'),

    # ── Manual Payment Screenshot Upload (Photographer) ──────────────────────
    path('pay/', ManualPaymentSubmitView.as_view(), name='payment-submit'),

    # ── Personal Payment History Audits (Photographer) ────────────────────────
    path('payments/', ManualPaymentListView.as_view(), name='payment-list'),

    # ── Admin Pending Review Queue (Admin Staff Only) ─────────────────────────
    path('admin/payments/', AdminPendingPaymentsView.as_view(), name='admin-pending-payments'),

    # ── Admin Decision & Activation Dispatcher (Admin Staff Only) ──────────────
    path('payments/<uuid:payment_id>/review/', AdminPaymentReviewView.as_view(), name='admin-payment-review'),
]