# backend/apps/subscriptions/staff_payments.py
"""
Staff review of manual payments (chunk 7.5-B), under the 7.5-A staff area. Staff is `is_staff` and
nothing else (apps/core/permissions.py::IsStaffUser): 401 anonymous, 403 anyone who is not staff.

  GET   /api/v1/staff/payments/?status=pending|approved|rejected|all&page=   the queue (default: pending, oldest first)
  POST  /api/v1/staff/payments/{id}/approve/                                 flips the entitlement
  POST  /api/v1/staff/payments/{id}/reject/        {"reason": "..."}         the plan stays as it was
  POST  /api/v1/staff/payments/{id}/proof-link/                              a signed link, valid a few minutes, bound to this staff member
  GET   /api/v1/staff/payments/{id}/proof/?s=<signed link>                   the proof file (staff cookie AND the signed link)

The rules are in payments.py (row lock, idempotence, the period, the audit row); these views only
translate them to HTTP. A refused or repeated call writes nothing. No storage path or storage URL is
ever returned: the only way to a proof is the signed link.
"""
import logging

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsStaffUser
from apps.users import audit
from apps.users.staff_api import StaffActionThrottle, StaffListThrottle, StaffPagination, error, read_reason

from . import payments
from .models import ManualPayment, UserSubscription

logger = logging.getLogger(__name__)

Status = ManualPayment.VerificationStatus
QUEUE_FILTERS = ('pending', 'approved', 'rejected', 'all')


class StaffPaymentSerializer(serializers.Serializer):
    """An explicit allowlist of keys for a staff reviewer. Never the storage path, a URL, a hash or a token."""

    def to_representation(self, payment):
        staff = self.context['staff']
        user = payment.user
        subscription = getattr(user, 'subscription', None)
        live = bool(subscription and subscription.status == UserSubscription.SubscriptionStatus.ACTIVE
                    and subscription.expires_at > self.context['now'])
        return {
            'id': str(payment.pk),
            'user_id': str(user.pk),
            'email': user.email,
            'name': user.display_name or user.username,
            'plan': payment.plan.key,
            'plan_name': payment.plan.name,
            'plan_price': str(payment.plan_price),
            'amount': str(payment.amount),
            'currency': payment.currency,
            'reference': payment.reference,
            'notes': payment.notes,
            'status': payment.status,
            'created_at': payment.created_at,
            'reviewed_at': payment.reviewed_at,
            'reviewed_by': payment.verified_by.email if payment.verified_by_id else None,
            'rejection_reason': payment.rejection_reason,
            'period_start': payment.period_start,
            'period_end': payment.period_end,
            'has_proof': bool(payment.payment_proof),
            'proof_type': payment.proof_type,
            'proof_size': int(payment.proof_size or 0),
            'current_plan_name': subscription.plan.name if live else None,
            'current_period_end': subscription.expires_at if live else None,
            'can_review': payment.user_id != staff.pk,
        }


def serialize(payments_, request, many=False):
    from django.utils import timezone
    return StaffPaymentSerializer(payments_, many=many, context={'staff': request.user, 'now': timezone.now()}).data


def refusal(problem):
    return error(problem.message, problem.code, problem.http_status)


def review_failed(payment_id):
    """An unexpected failure: everything rolled back; the detail (SQL, driver text) goes to the server log only."""
    logger.exception('Payment review failed for payment %s', payment_id)
    return error('Could not complete the review. No changes were saved.', 'review_failed',
                 status.HTTP_500_INTERNAL_SERVER_ERROR)


class StaffPaymentListView(APIView):
    permission_classes = [IsStaffUser]
    throttle_classes = [StaffListThrottle]

    def get(self, request):
        state = request.query_params.get('status') or 'pending'
        if state not in QUEUE_FILTERS:
            return error('Invalid status.', 'invalid_filter', status.HTTP_400_BAD_REQUEST)
        rows = ManualPayment.objects.select_related('plan', 'user', 'verified_by', 'user__subscription__plan')
        if state != 'all':
            rows = rows.filter(status=state)
        # A fair queue: the oldest waiting payment first; history newest first.
        rows = rows.order_by('created_at' if state == 'pending' else '-created_at', '-id')
        paginator = StaffPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        # Every staff read of payment data is itself audited (fail closed: no row, no data).
        audit.record(audit.Action.INBOX_VIEW, actor=request.user, request=request, reason=f'payments status={state}')
        return paginator.get_paginated_response(serialize(page, request, many=True))


class StaffPaymentApproveView(APIView):
    permission_classes = [IsStaffUser]
    throttle_classes = [StaffActionThrottle]

    def post(self, request, payment_id):
        try:
            payment, changed = payments.approve_payment(payment_id, request.user, request)
        except payments.PaymentError as problem:
            return refusal(problem)
        except Exception:
            return review_failed(payment_id)
        payment = reload(payment.pk)
        return Response({
            'changed': changed,
            'code': 'approved' if changed else 'already_approved',
            'message': 'Payment approved. The plan is active.' if changed
                       else 'This payment was already approved. Nothing was changed.',
            'payment': serialize(payment, request),
        })


class StaffPaymentRejectView(APIView):
    permission_classes = [IsStaffUser]
    throttle_classes = [StaffActionThrottle]

    def post(self, request, payment_id):
        reason, problem = read_reason(request)
        if problem:
            return problem
        try:
            payment, changed = payments.reject_payment(payment_id, request.user, reason, request)
        except payments.PaymentError as refused:
            return refusal(refused)
        except Exception:
            return review_failed(payment_id)
        payment = reload(payment.pk)
        return Response({
            'changed': changed,
            'code': 'rejected' if changed else 'already_rejected',
            'message': 'Payment rejected. The user has been told why.' if changed
                       else 'This payment was already rejected. Nothing was changed.',
            'payment': serialize(payment, request),
        })


def reload(payment_id):
    return ManualPayment.objects.select_related(
        'plan', 'user', 'verified_by', 'user__subscription__plan').get(pk=payment_id)


class StaffPaymentProofLinkView(APIView):
    """Mints the signed link to ONE proof. Audited: who opened which payment's proof, when."""
    permission_classes = [IsStaffUser]
    throttle_classes = [StaffListThrottle]

    def post(self, request, payment_id):
        payment = get_object_or_404(ManualPayment.objects.select_related('plan', 'user'), pk=payment_id)
        if not payment.payment_proof:
            return error('This payment has no proof file.', 'proof_missing', status.HTTP_404_NOT_FOUND)
        audit.record(audit.Action.PAYMENT_PROOF_VIEW, actor=request.user, target=payment.user, request=request,
                     reason=payments.audit_summary(payment))
        from django.conf import settings
        return Response({
            'url': payments.proof_link(payment, request.user, request),
            'expires_in': settings.MANUAL_PAYMENT_PROOF_LINK_SECONDS,
            'content_type': payment.proof_type,
        })


class StaffPaymentProofView(APIView):
    """
    The proof file itself. Needs the staff sign-in AND a link minted for this payment and this staff
    member a few minutes ago; the bytes are streamed through the API, so no storage URL ever leaves
    the server. Served with nosniff, no caching and no referrer.
    """
    permission_classes = [IsStaffUser]
    throttle_classes = [StaffListThrottle]

    def get(self, request, payment_id):
        if not payments.read_proof_link(request.query_params.get('s', ''), payment_id, request.user):
            return error('This link has expired. Open the proof again from the payment.', 'proof_link_invalid',
                         status.HTTP_403_FORBIDDEN)
        payment = get_object_or_404(ManualPayment, pk=payment_id)
        if not payment.payment_proof:
            return error('This payment has no proof file.', 'proof_missing', status.HTTP_404_NOT_FOUND)
        try:
            handle = payment.payment_proof.open('rb')
        except (FileNotFoundError, OSError):
            return error('The proof file is missing.', 'proof_missing', status.HTTP_404_NOT_FOUND)
        extension = payments.PROOF_TYPES.get(payment.proof_type, '')
        response = FileResponse(handle, content_type=payment.proof_type or 'application/octet-stream',
                                as_attachment=False, filename=f'payment-proof{extension}')
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Referrer-Policy'] = 'no-referrer'
        response['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
        return response
