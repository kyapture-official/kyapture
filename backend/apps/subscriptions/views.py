from datetime import timedelta
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SubscriptionPlan, UserSubscription, ManualPayment
from .serializers import (
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
    ManualPaymentSubmitSerializer,
    AdminPaymentListSerializer,   # Integrated Day 3 Serializer
    AdminPaymentReviewSerializer, # Integrated Day 3 Serializer
)


class PlanListView(APIView):
    """
    GET /api/v1/subscriptions/plans/
    Exposes active platform subscription tiers ordered by price.
    Accessible publicly without authentication (AllowAny) [1.1.2].
    """
    permission_classes = [AllowAny]

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(
            is_active=True
        ).order_by('price')

        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MySubscriptionView(APIView):
    """
    GET /api/v1/subscriptions/my-subscription/
    Returns the requesting photographer's active plan status and usage footprints [1.1.2].
    Implements a self-healing database check to automatically rotate expired plans [1.1.2].
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # JOIN parent relations in a single query to eliminate N+1 bottlenecks [1.1.2]
            subscription = (
                UserSubscription.objects
                .select_related('plan', 'user')
                .get(user=request.user)
            )

            # Self-Healing Safeguard: Auto-expire active plan if timestamp has passed [1.1.2]
            if subscription.status == 'active' and subscription.expires_at < timezone.now():
                # Enforce transaction-safe status update
                subscription.status = 'expired'
                subscription.save(update_fields=['status'])
                
                # De-authorize the photographer's billing access flag [1.1.2]
                user = request.user
                if user.is_active_plan:
                    user.is_active_plan = False
                    user.save(update_fields=['is_active_plan'])

        except UserSubscription.DoesNotExist:
            # Return standard non-crashing schema response for clean React parsing [1.1.2]
            return Response({
                'status': 'no_subscription',
                'message': 'No subscription found. Select a plan to get started.',
                'plan': None,
                'expires_at': None,
            }, status=status.HTTP_200_OK)

        serializer = UserSubscriptionSerializer(subscription, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    
class ManualPaymentSubmitView(APIView):
    """
    POST /api/v1/subscriptions/pay/
    Handles photographer manual payment screenshot submissions.
    Enforces multipart/form-data parsing [1.1.2].
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ManualPaymentSubmitSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Payment receipt submitted successfully. Admin review pending."},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ManualPaymentListView(APIView):
    """
    GET /api/v1/subscriptions/payments/
    Lists payments. 
    - Standard photographers see their own submission history [1.1.2].
    - Administrative staff (is_staff=True) see all globally pending payments [1.1.2].
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.is_staff:
            # Admins see the complete global pending queue [1.1.2]
            payments = ManualPayment.objects.select_related('user', 'plan').all()
        else:
            # Photographers are strictly isolated to their own history [1.1.2]
            payments = ManualPayment.objects.select_related('plan').filter(user=request.user)

        # Basic inline serialization for quick audit list
        data = [{
            'id': pay.id,
            'email': pay.user.email,
            'plan_name': pay.plan.name,
            'amount': str(pay.amount),
            'status': pay.status,
            'created_at': pay.created_at,
            'payment_proof': request.build_absolute_uri(pay.payment_proof.url) if pay.payment_proof else None,
            'notes': pay.notes
        } for pay in payments]

        return Response(data, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────
# 7. ADMIN PENDING PAYMENTS VIEW (Admin Staff Only)
# GET /api/v1/subscriptions/admin/payments/
# ─────────────────────────────────────────────────────────────
class AdminPendingPaymentsView(APIView):
    """
    GET /api/v1/subscriptions/admin/payments/
    Lists all pending manual payments waiting for administrative review.
    IsAdminUser — Restricts access strictly to staff. Non-staff receives 403 [1.1.2].
    Orders entries chronologically (oldest first) to enable a fair processing queue.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        # select_related avoids N+1 query loops when resolving related user & plan data
        payments = (
            ManualPayment.objects
            .filter(status=ManualPayment.VerificationStatus.PENDING)
            .select_related('plan', 'user')
            .order_by('created_at')
        )
        serializer = AdminPaymentListSerializer(
            payments,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────
# 8. ADMIN PAYMENT REVIEW VIEW (Admin Staff Only)
# POST /api/v1/subscriptions/payments/{payment_id}/review/
# ─────────────────────────────────────────────────────────────
class AdminPaymentReviewView(APIView):
    """
    POST /api/v1/subscriptions/payments/{payment_id}/review/
    Allows platform administrators to approve or reject manual payment claims.
    
    Guarantees strict transaction safety (all or nothing) during multi-table writes:
    - On Approve:
        1. ManualPayment status transitions to APPROVED.
        2. UserSubscription row is fetched or generated, and extended by 30 days.
        3. User model global flag 'is_active_plan' is set to True.
    - On Reject:
        1. ManualPayment status transitions to REJECTED. (User billing status unchanged).
    """
    permission_classes = [IsAdminUser]

    def post(self, request, payment_id):
        payment = get_object_or_404(
            ManualPayment.objects.select_related('plan', 'user'), 
            id=payment_id
        )

        # Utilize serializer validation to assert context-specific checks
        serializer = AdminPaymentReviewSerializer(
            data=request.data,
            context={
                'request': request,
                'payment': payment
            }
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action = serializer.validated_data['action']
        admin_note = serializer.validated_data.get('admin_note', '').strip()

        # Wrap all structural multi-table modifications in a single SQL transaction
        try:
            with transaction.atomic():
                if action == 'approve':
                    # 1. Update verification state
                    payment.status = ManualPayment.VerificationStatus.APPROVED
                    payment.verified_by = request.user
                    if admin_note:
                        payment.notes = admin_note
                    payment.save(update_fields=['status', 'verified_by', 'notes'])

                    # 2. Stateful Create-or-Extend Math for Subscription Expirations
                    now = timezone.now()
                    subscription, created = UserSubscription.objects.get_or_create(
                        user=payment.user,
                        defaults={
                            'plan': payment.plan,
                            'status': UserSubscription.SubscriptionStatus.ACTIVE,
                            'starts_at': now,
                            'expires_at': now + timedelta(days=30),
                            'payment_method': UserSubscription.PaymentMethod.MANUAL
                        }
                    )

                    if not created:
                        # Photographer is renewing. Calculate base date sequentially:
                        # If active: extend from future expiration. If expired: start from now.
                        base_date = max(subscription.expires_at, now)
                        subscription.plan = payment.plan
                        subscription.status = UserSubscription.SubscriptionStatus.ACTIVE
                        subscription.payment_method = UserSubscription.PaymentMethod.MANUAL
                        subscription.expires_at = base_date + timedelta(days=30)
                        subscription.save(update_fields=['plan', 'status', 'payment_method', 'expires_at'])

                    # 3. Elevate user billing permission
                    photographer = payment.user
                    photographer.is_active_plan = True
                    photographer.save(update_fields=['is_active_plan'])

                    # Serialize the successful active state to match API specs
                    return Response({
                        "message": "Payment approved. Subscription activated.",
                        "payment": AdminPaymentListSerializer(payment, context={'request': request}).data,
                        "subscription": UserSubscriptionSerializer(subscription, context={'request': request}).data
                    }, status=status.HTTP_200_OK)

                elif action == 'reject':
                    # Rejections only modify the payment status log—no subscription or permission adjustments are made
                    payment.status = ManualPayment.VerificationStatus.REJECTED
                    payment.verified_by = request.user
                    if admin_note:
                        payment.notes = admin_note
                    payment.save(update_fields=['status', 'verified_by', 'notes'])

                    return Response({
                        "message": "Payment rejected.",
                        "payment": AdminPaymentListSerializer(payment, context={'request': request}).data,
                        "subscription": None
                    }, status=status.HTTP_200_OK)

        except Exception as e:
            # PostgreSQL rolls back any changes inside the context block on exception raised
            return Response(
                {"error": f"State machine transition aborted due to internal server error: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )