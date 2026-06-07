from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.parsers import MultiPartParser, FormParser


from datetime import timedelta
from .models import SubscriptionPlan, UserSubscription, ManualPayment
from .serializers import (
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
    ManualPaymentSubmitSerializer,
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


class AdminPaymentApprovalView(APIView):
    """
    POST /api/v1/subscriptions/payments/{payment_id}/review/
    Permits admins to approve or reject pending manual payments.
    On approval: automatically calculates expirations, updates plan details,
    and flips is_active_plan status inside a transaction block [1.1.2].
    """
    permission_classes = [IsAdminUser]  # Hard-locked to Django administrators [1.1.2]

    def post(self, request, payment_id):
        payment = get_object_or_404(ManualPayment, id=payment_id)
        
        # Enforce that we do not process already approved/rejected transactions
        if payment.status != ManualPayment.VerificationStatus.PENDING:
            return Response(
                {"error": "This payment has already been reviewed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        action = request.data.get('action', '').strip().lower()
        if action not in ['approve', 'reject']:
            return Response(
                {"error": "Invalid action. Must be 'approve' or 'reject'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Wrap database operations in an atomic block [1.1.2]
        try:
            with transaction.atomic():
                if action == 'approve':
                    payment.status = ManualPayment.VerificationStatus.APPROVED
                    payment.verified_by = request.user
                    payment.save(update_fields=['status', 'verified_by'])

                    # Dynamically calculate plan activation dates (30-day window) [1.1.2]
                    starts_at = timezone.now()
                    expires_at = starts_at + timedelta(days=30)

                    # Create or update active subscription record [1.1.2]
                    UserSubscription.objects.update_or_create(
                        user=payment.user,
                        defaults={
                            'plan': payment.plan,
                            'status': UserSubscription.SubscriptionStatus.ACTIVE,
                            'starts_at': starts_at,
                            'expires_at': expires_at,
                            'payment_method': UserSubscription.PaymentMethod.MANUAL
                        }
                    )

                    # Authorize the photographer's global billing permission flag [1.1.2]
                    photographer = payment.user
                    photographer.is_active_plan = True
                    photographer.save(update_fields=['is_active_plan'])

                elif action == 'reject':
                    payment.status = ManualPayment.VerificationStatus.REJECTED
                    payment.verified_by = request.user
                    payment.save(update_fields=['status', 'verified_by'])

        except Exception as e:
            return Response({"error": f"Transaction failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {"message": f"Payment successfully {payment.get_status_display().lower()}."},
            status=status.HTTP_200_OK
        )    