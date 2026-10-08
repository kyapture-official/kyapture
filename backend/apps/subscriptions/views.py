# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/views.py
import logging
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from . import payments
from .entitlements import get_feature_entitlements
from .models import ManualPayment, PaymentInstructions, SubscriptionPlan, UserSubscription
from .serializers import (
    ManualPaymentSubmitSerializer,
    OwnPaymentSerializer,
    PaymentInstructionsSerializer,
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
)

logger = logging.getLogger(__name__)


class PlanListView(APIView):
    """
    GET /api/v1/subscriptions/plans/
    Exposes active platform subscription tiers ordered by price.
    Accessible publicly without authentication (AllowAny) [1.1.2].
    """
    permission_classes = [AllowAny]
    authentication_classes = []
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
                'entitlements': get_feature_entitlements(request.user),
            }, status=status.HTTP_200_OK)

        serializer = UserSubscriptionSerializer(subscription, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    
class PaymentSubmitThrottle(UserRateThrottle):
    """Receipts submitted, per user id (settings rate `payment_submit`)."""
    scope = 'payment_submit'


def payment_refusal(error):
    """The 400 body for a refused submit: one clear message, a stable code, the field when there is one."""
    body = {'error': error.message, 'code': error.code}
    if error.field:
        body['errors'] = {error.field: [error.message]}
    return Response(body, status=error.http_status)


class ManualPaymentView(APIView):
    """
        GET  /api/v1/subscriptions/payments/
        The signed-in user's OWN payments (Billing history), newest first. Staff get the
        same: the review queue is /api/v1/staff/payments/ (7.5-B).
        POST /api/v1/subscriptions/payments/
        Submits a manual bank / eSewa payment: plan, amount, transaction ID, proof file.
    """
    permission_classes = [IsAuthenticated]

    def get_parsers(self):
        """
        Dynamically applies MultiPartParser only to POST requests, 
        ensuring secure multipart binary stream parsing for receipts 
        while keeping GET requests running under lightweight default JSON parsers.
        """
        if self.request.method == 'POST':
            return [MultiPartParser(), FormParser()]
        return super().get_parsers() 

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method == 'POST':
            throttles.append(PaymentSubmitThrottle())
        return throttles

    def get(self, request):
        rows = ManualPayment.objects.select_related('plan').filter(user=request.user)
        return Response(OwnPaymentSerializer(rows, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ManualPaymentSubmitSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(self.first_error(serializer.errors), status=status.HTTP_400_BAD_REQUEST)
        try:
            payment = serializer.save()
        except payments.PaymentError as error:
            return payment_refusal(error)
        return Response(
            {
                "message": "Payment submitted. We will review it shortly.",
                "payment": OwnPaymentSerializer(payment).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def first_error(errors):
        """{'error': first message, 'code': its code, 'errors': every field's messages}."""
        field, details = next(iter(errors.items()))
        first = details[0] if isinstance(details, (list, tuple)) else details
        return {
            'error': str(first),
            'code': getattr(first, 'code', None) or 'invalid',
            'errors': {name: [str(item) for item in (value if isinstance(value, (list, tuple)) else [value])]
                       for name, value in errors.items()},
        }


class PaymentInstructionsView(APIView):
    """
    GET /api/v1/subscriptions/payment-instructions/
    Where to send the money (account name, eSewa / bank details, optional QR, a note): the single
    admin-edited PaymentInstructions row. Signed-in users only; nothing here is in code or the frontend.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            PaymentInstructionsSerializer(PaymentInstructions.load(), context={'request': request}).data,
            status=status.HTTP_200_OK,
        )
