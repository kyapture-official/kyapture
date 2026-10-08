# backend/apps/subscriptions/payments.py
"""
Manual payments (chunk 7.5-B): every rule of the submit -> review -> entitlement flow
lives here, so the views stay thin and a test can call one function.

  validate_reference / check_reference   a transaction id is unique across all payments (after
                                         trimming and lower-casing); only a REJECTED one can be
                                         reused, and only by the same user
  sniff_proof                            a proof is a JPEG, PNG, WEBP or PDF judged by its bytes
  create_payment                         the submit, under the user's lock: pending cap, reference,
                                         money frozen at submission, audit row, staff bell
  approve_payment / reject_payment       the review: the PAYMENT row is locked (FOR NO KEY UPDATE,
                                         as in 7G), its status is re-read inside the lock and
                                         flipped once; a repeat changes nothing and says so
  proof_link / read_proof_link           the signed, short-lived, staff-bound link to one proof

The plan the user paid for is applied through the SubscriptionPlan row (no plan name, price
or limit in code); who may use which feature is still decided by entitlements.py alone.
"""
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone
from PIL import Image as PILImage

from apps.users import audit
from apps.users.models import User
from apps.users.notification_service import notify_payment_event, notify_staff_payment_submitted
from apps.users.notifications import notify_payment_reviewed

from .models import ManualPayment, UserSubscription, normalize_reference

logger = logging.getLogger(__name__)

Status = ManualPayment.VerificationStatus

REFERENCE_MIN, REFERENCE_MAX = 4, 64
# A transaction id: letters, digits and . _ / - only, starting and ending with a letter or digit.
REFERENCE_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/-]{2,62}[A-Za-z0-9]$')
NOTES_MAX = 500

# What a proof may be. The extension of the stored name comes from this table, never from the upload.
PROOF_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'application/pdf': '.pdf',
}
_PILLOW_FORMATS = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}

PROOF_LINK_SALT = 'kyapture.payments.proof-link'
MB = 1024 * 1024


class PaymentError(Exception):
    """A refusal with a stable `code`, a message safe to show, an HTTP status and (optionally) the form field."""

    def __init__(self, code, message, http_status=400, field=None):
        super().__init__(message)
        self.code, self.message, self.http_status, self.field = code, message, http_status, field


# ─── reference ───────────────────────────────────────────────────────────────

def validate_reference(raw):
    """The reference as typed, trimmed; PaymentError(400, reference_invalid) when it is not a plain transaction id."""
    text = audit.one_line(raw if isinstance(raw, str) else '')
    if not text:
        raise PaymentError('reference_required', 'Enter the transaction ID from your payment.', field='reference')
    if len(text) < REFERENCE_MIN or len(text) > REFERENCE_MAX or not REFERENCE_RE.match(text):
        raise PaymentError(
            'reference_invalid',
            f'The transaction ID must be {REFERENCE_MIN}-{REFERENCE_MAX} characters: letters, numbers, '
            'and . _ / - only (no spaces).',
            field='reference',
        )
    return text


def reference_taken_error(own):
    if own:
        return PaymentError('reference_already_submitted', 'You already submitted this transaction ID.', field='reference')
    return PaymentError(
        'reference_taken',
        'This transaction ID was already submitted. Check it and try again, or contact support.',
        field='reference',
    )


def check_reference(user, reference):
    """
    Raises PaymentError unless `reference` is free for `user`. Taken = any payment holds it,
    except a REJECTED payment of the SAME user (a rejected reference may be re-submitted by
    its owner, e.g. with a better screenshot, and by nobody else).
    """
    key = normalize_reference(reference)
    holders = ManualPayment.objects.filter(reference_key=key).values_list('user_id', 'status')
    for holder_id, status in holders:
        if holder_id == user.pk and status == Status.REJECTED:
            continue
        raise reference_taken_error(own=holder_id == user.pk)


# ─── proof of payment ────────────────────────────────────────────────────────

def proof_max_bytes():
    return settings.MANUAL_PAYMENT_PROOF_MAX_MB * MB


def sniff_proof(file):
    """
    The content type of an uploaded proof, judged by its BYTES (never its name or the client's
    content type): a JPEG/PNG/WEBP that Pillow reads within the pixel limit, or a PDF. Returns
    one of PROOF_TYPES; raises PaymentError(400) for anything else.
    """
    limit_mb = settings.MANUAL_PAYMENT_PROOF_MAX_MB
    if not file.size:
        raise PaymentError('proof_empty', 'The proof file is empty.', field='payment_proof')
    if file.size > proof_max_bytes():
        raise PaymentError('proof_too_large', f'The proof must be {limit_mb} MB or smaller.', field='payment_proof')
    file.seek(0)
    head = file.read(8)
    file.seek(0)
    if head.startswith(b'%PDF-'):
        return 'application/pdf'
    try:
        with PILImage.open(file) as img:
            image_format = (img.format or '').upper()
            width, height = img.size
            if image_format in _PILLOW_FORMATS and getattr(img, 'is_animated', False):
                raise PaymentError('proof_invalid', 'Animated images are not accepted.', field='payment_proof')
            if width * height > settings.MANUAL_PAYMENT_PROOF_MAX_PIXELS:
                raise PaymentError('proof_too_large', 'The proof image has too many pixels.', field='payment_proof')
        file.seek(0)
        with PILImage.open(file) as img:
            img.verify()
    except PaymentError:
        raise
    except Exception:       # unreadable, truncated, a bomb, any other format
        raise PaymentError('proof_invalid', 'Upload a JPEG, PNG or WEBP image, or a PDF.', field='payment_proof')
    finally:
        file.seek(0)
    if image_format not in _PILLOW_FORMATS:
        raise PaymentError('proof_invalid', 'Upload a JPEG, PNG or WEBP image, or a PDF.', field='payment_proof')
    return _PILLOW_FORMATS[image_format]


# ─── audit text ──────────────────────────────────────────────────────────────

def audit_summary(payment):
    """The audit reason: ids and money only. Never the proof, the reference or the user's notes."""
    return f'payment={payment.pk} plan={payment.plan.key} amount={payment.amount} {payment.currency}'


# ─── submit ──────────────────────────────────────────────────────────────────

def create_payment(*, user, plan, amount, reference, proof, proof_type, notes='', request=None):
    """
    Records one submitted payment. Runs under the USER's row lock so two parallel submits of
    one account cannot slip past the pending cap, and relies on the database constraint for two
    different accounts submitting the same reference at once.
    """
    reference = validate_reference(reference)
    stored_name = None
    try:
        with transaction.atomic():
            User.objects.select_for_update(no_key=True).get(pk=user.pk)
            pending = ManualPayment.objects.filter(user=user, status=Status.PENDING)
            if pending.count() >= settings.MANUAL_PAYMENT_MAX_PENDING:
                raise PaymentError(
                    'too_many_pending',
                    f'You already have {settings.MANUAL_PAYMENT_MAX_PENDING} payments waiting for review. '
                    'Wait for a decision before sending another.',
                )
            if pending.filter(plan=plan).exists():
                raise PaymentError(
                    'duplicate_pending',
                    'You already have a pending payment for this plan. Please wait for the review.',
                    field='plan',
                )
            check_reference(user, reference)
            payment = ManualPayment(
                user=user, plan=plan, amount=amount, plan_price=plan.price, currency=ManualPayment.CURRENCY,
                reference=reference, proof_type=proof_type, proof_size=proof.size, notes=notes,
                status=Status.PENDING,
            )
            payment.payment_proof.save(f'proof{PROOF_TYPES[proof_type]}', proof, save=False)
            stored_name = payment.payment_proof.name
            payment.save()
            audit.record(audit.Action.PAYMENT_SUBMIT, actor=user, target=user, request=request,
                         reason=audit_summary(payment))
            notify_staff_payment_submitted(payment)
    except Exception as exc:
        # The database rolled back; the private file must not outlive the row it belonged to.
        if stored_name:
            try:
                ManualPayment._meta.get_field('payment_proof').storage.delete(stored_name)
            except Exception:
                logger.exception('Could not remove the orphaned proof file of a failed submit')
        # Two accounts sent the same new reference in the same instant: the unique constraint let one in.
        if isinstance(exc, IntegrityError) and 'uniq_manual_pay_reference' in str(exc):
            raise reference_taken_error(own=False)
        raise
    return payment


# ─── review ──────────────────────────────────────────────────────────────────

def _lock_payment(payment_id):
    """The payment row, locked FOR NO KEY UPDATE (the lock 7G uses; it does not block foreign-key checks on it)."""
    return (
        ManualPayment.objects.select_for_update(no_key=True, of=('self',))
        .select_related('plan', 'user').filter(pk=payment_id).first()
    )


def _ensure_reviewable(payment, staff):
    if payment is None:
        raise PaymentError('not_found', 'Payment not found.', 404)
    if payment.user_id == staff.pk:
        raise PaymentError('cannot_review_own', 'You cannot review your own payment.', 403)


def approve_payment(payment_id, staff, request=None):
    """
    Approves a PENDING payment: (payment, changed). The payment row is locked and its status
    re-read inside the lock, so a double click or two staff at once flip it exactly once; the
    repeat gets (payment, False) and changes, mails and logs nothing. A REJECTED payment cannot
    be approved (409): the user submits a new one.
    """
    with transaction.atomic():
        payment = _lock_payment(payment_id)
        _ensure_reviewable(payment, staff)
        if payment.status == Status.APPROVED:
            return payment, False
        if payment.status == Status.REJECTED:
            raise PaymentError('already_rejected', 'This payment was already rejected. Nothing was changed.', 409)

        # One writer per account's billing: payments of the same user, approved together, queue here.
        user = User.objects.select_for_update(no_key=True).get(pk=payment.user_id)
        now = timezone.now()
        period = timedelta(days=settings.MANUAL_PAYMENT_PERIOD_DAYS)
        subscription = UserSubscription.objects.select_for_update().filter(user=user).first()
        if subscription is None:
            start, end = now, now + period
            subscription = UserSubscription.objects.create(
                user=user, plan=payment.plan, status=UserSubscription.SubscriptionStatus.ACTIVE,
                payment_method=UserSubscription.PaymentMethod.MANUAL, starts_at=start, expires_at=end,
            )
        else:
            live_on_same_plan = (
                subscription.plan_id == payment.plan_id
                and subscription.status == UserSubscription.SubscriptionStatus.ACTIVE
                and subscription.expires_at > now
            )
            # Already on this plan: add the period to the current end date. Anything else
            # (another plan, lapsed, none): the paid plan starts now.
            start = subscription.starts_at if live_on_same_plan else now
            end = (subscription.expires_at if live_on_same_plan else now) + period
            subscription.plan = payment.plan
            subscription.status = UserSubscription.SubscriptionStatus.ACTIVE
            subscription.payment_method = UserSubscription.PaymentMethod.MANUAL
            subscription.starts_at, subscription.expires_at = start, end
            # A new period: the reminder / downgrade markers of the old one are cleared (7.5-C; they are also
            # keyed to the old end date, so they would read "not done" for the new one either way).
            for marker in UserSubscription.LIFECYCLE_MARKERS:
                setattr(subscription, marker, None)
            subscription.save(update_fields=[
                'plan', 'status', 'payment_method', 'starts_at', 'expires_at', 'updated_at',
                *UserSubscription.LIFECYCLE_MARKERS,
            ])
        if not user.is_active_plan:
            user.is_active_plan = True
            user.save(update_fields=['is_active_plan'])

        payment.status = Status.APPROVED
        payment.verified_by = staff
        payment.reviewed_at = now
        payment.period_start, payment.period_end = start, end
        payment.save(update_fields=['status', 'verified_by', 'reviewed_at', 'period_start', 'period_end', 'updated_at'])

        audit.record(audit.Action.PAYMENT_APPROVE, actor=staff, target=payment.user, request=request,
                     reason=audit_summary(payment))
        notify_payment_reviewed(payment)
        notify_payment_event(payment)
    return payment, True


def reject_payment(payment_id, staff, reason, request=None):
    """
    Rejects a PENDING payment with a reason the user will see: (payment, changed). The plan and
    the subscription are not touched. A repeat reject changes nothing; rejecting an APPROVED
    payment is refused (409) and changes nothing.
    """
    with transaction.atomic():
        payment = _lock_payment(payment_id)
        _ensure_reviewable(payment, staff)
        if payment.status == Status.REJECTED:
            return payment, False
        if payment.status == Status.APPROVED:
            raise PaymentError('already_approved', 'This payment was already approved. Nothing was changed.', 409)

        payment.status = Status.REJECTED
        payment.verified_by = staff
        payment.reviewed_at = timezone.now()
        payment.rejection_reason = reason
        payment.save(update_fields=['status', 'verified_by', 'reviewed_at', 'rejection_reason', 'updated_at'])

        audit.record(audit.Action.PAYMENT_REJECT, actor=staff, target=payment.user, request=request,
                     reason=audit_summary(payment))
        notify_payment_reviewed(payment)
        notify_payment_event(payment)
    return payment, True


# ─── the staff link to one proof ─────────────────────────────────────────────

def proof_link(payment, staff, request):
    """A signed link to ONE payment's proof, valid for MANUAL_PAYMENT_PROOF_LINK_SECONDS and bound to this staff member."""
    token = signing.TimestampSigner(salt=PROOF_LINK_SALT).sign(f'{payment.pk}:{staff.pk}')
    path = f'/api/v1/staff/payments/{payment.pk}/proof/'
    return request.build_absolute_uri(path) + f'?s={token}'


def read_proof_link(token, payment_id, staff):
    """True when `token` was minted for this payment and this staff member and has not expired."""
    if not token:
        return False
    try:
        value = signing.TimestampSigner(salt=PROOF_LINK_SALT).unsign(
            token, max_age=settings.MANUAL_PAYMENT_PROOF_LINK_SECONDS)
    except signing.BadSignature:      # includes SignatureExpired
        return False
    return value == f'{payment_id}:{staff.pk}'
