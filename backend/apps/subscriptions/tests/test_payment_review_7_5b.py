# backend/apps/subscriptions/tests/test_payment_review_7_5b.py
"""
CHUNK 7.5-B - manual payment review (submit -> staff approve / reject -> entitlement).

  - One payment model. The money (amount, currency NPR, the plan price) is frozen at submission, so a
    later price edit cannot change a pending payment.
  - The transaction ID is unique across all payments after trimming and lower-casing (a database
    constraint); a REJECTED one can be re-submitted by the same user only.
  - A proof is an image or a PDF judged by its bytes, kept in private storage, opened by staff through a
    signed, short-lived link bound to that staff member; it never appears in a URL, a payload or a log.
  - Approve / reject are staff only (401 / 403), lock the PAYMENT row and re-read its status inside the
    lock: a double click or two staff at once change it once; a repeat says so and changes nothing; staff
    cannot review their own payment.
  - Approve applies the plan the user paid for through the plan table for MANUAL_PAYMENT_PERIOD_DAYS
    (from the current end date when already on that plan); a rejected or lapsed payment unlocks nothing,
    at request time, with no job having run, and nothing is deleted.
"""
import io
import logging
import shutil
import tempfile
import threading
import time
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib import admin as django_admin
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connections, transaction
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from apps.clients.download_access import effective_high_res_mode
from apps.core.storage import PrivateMediaStorage
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.subscriptions import entitlements, payments
from apps.subscriptions.admin import PaymentAdmin, PaymentInstructionsAdmin, PaymentInstructionsForm
from apps.subscriptions.entitlements import GB, get_feature_entitlements, storage_figures
from apps.subscriptions.models import (
    ManualPayment, PaymentInstructions, SubscriptionPlan, UserSubscription, normalize_reference,
)
from apps.subscriptions.testing import ensure_seed_plans, grant_plan
from apps.subscriptions.views import PaymentSubmitThrottle
from apps.users.audit import Action
from apps.users.models import Notification, StaffAuditLog, User
from apps.users.notifications import deliver_notification

PASSWORD = 'Sturdy-Pass-8842!'
PAYMENTS = '/api/v1/subscriptions/payments/'
INSTRUCTIONS = '/api/v1/subscriptions/payment-instructions/'
STAFF = '/api/v1/staff/payments/'
Status = ManualPayment.VerificationStatus
PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n'


def make_user(name, **extra):
    return User.objects.create_user(email=f'{name}@example.com', password=PASSWORD, username=name, **extra)


def image_bytes(fmt='PNG', size=(40, 30)):
    buf = io.BytesIO()
    Image.new('RGB', size, 'white').save(buf, fmt)
    return buf.getvalue()


def upload(data=None, name='receipt.png', content_type='image/png'):
    return SimpleUploadedFile(name, image_bytes() if data is None else data, content_type=content_type)


def audit_rows(action=None, **filters):
    rows = StaffAuditLog.objects.filter(**filters)
    return rows.filter(action=action) if action else rows


class MediaSandbox:
    """Proof files of the tests go to a temporary MEDIA_ROOT, never into the dev media volume."""

    @classmethod
    def enter(cls):
        cls._media = tempfile.mkdtemp(prefix='kyapture-pay-')
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def leave(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)


class PaymentBase(APITestCase):
    @classmethod
    def setUpClass(cls):
        MediaSandbox.enter.__func__(cls)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        MediaSandbox.leave.__func__(cls)

    def setUp(self):
        cache.clear()
        self.staff = make_user('staffer', is_staff=True)
        self.staff2 = make_user('staffer2', is_staff=True)
        self.owner = make_user('payer')
        self.other = make_user('payer2')
        self.pro = SubscriptionPlan.objects.get(key='pro')
        self.basic = SubscriptionPlan.objects.get(key='basic')
        patcher = mock.patch('apps.users.tasks.send_notification_email.delay',
                             side_effect=lambda *args: deliver_notification(*args))
        patcher.start()
        self.addCleanup(patcher.stop)

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def submit(self, user=None, plan=None, reference='TX-1001', proof=None, amount=None, **extra):
        plan = plan or self.pro
        data = {
            'plan': str(plan.id), 'amount': str(plan.price if amount is None else amount),
            'reference': reference, 'payment_proof': proof or upload(),
        }
        data.update(extra)
        return self.as_user(user or self.owner).post(PAYMENTS, data, format='multipart')

    def make_payment(self, user=None, plan=None, reference=None, status=Status.PENDING, data=None, ext='png'):
        plan = plan or self.pro
        payment = ManualPayment(
            user=user or self.owner, plan=plan, amount=plan.price, plan_price=plan.price,
            reference=reference if reference is not None else f'REF-{ManualPayment.objects.count() + 1:04d}',
            status=status, proof_type='image/png', proof_size=1)
        payment.payment_proof.save(f'proof.{ext}', ContentFile(data or image_bytes()), save=False)
        payment.save()
        return payment

    def review(self, payment, action, client=None, **body):
        client = client or self.as_user(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            return client.post(f'{STAFF}{payment.pk}/{action}/', body, format='json')

    def approve(self, payment, client=None):
        return self.review(payment, 'approve', client)

    def reject(self, payment, reason='The amount on the receipt is wrong', client=None):
        return self.review(payment, 'reject', client, reason=reason)

    def subscription(self, user=None):
        return UserSubscription.objects.filter(user=user or self.owner).first()


# ─── the transaction reference ───────────────────────────────────────────────

class ReferenceTests(PaymentBase):
    def test_a_reference_is_required_and_must_be_a_plain_transaction_id(self):
        for reference, code in (
            ('', 'blank'), ('   ', 'blank'), ('ab', 'reference_invalid'),
            ('x' * 65, 'reference_invalid'), ('<script>alert(1)</script>', 'reference_invalid'),
            ('has space 1', 'reference_invalid'), ('-leading-dash', 'reference_invalid'),
        ):
            response = self.submit(reference=reference)
            self.assertEqual(response.status_code, 400, reference)
            self.assertEqual(response.data['code'], code, reference)
            self.assertIn('reference', response.data['errors'], reference)
        self.assertEqual(ManualPayment.objects.count(), 0)

    def test_the_reference_is_stored_trimmed_and_compared_lowercased(self):
        self.assertEqual(self.submit(reference='  FT24-ABC/9  ').status_code, 201)
        payment = ManualPayment.objects.get()
        self.assertEqual((payment.reference, payment.reference_key), ('FT24-ABC/9', 'ft24-abc/9'))
        self.assertEqual(normalize_reference('  FT24-ABC/9 '), 'ft24-abc/9')

    def test_a_second_submit_with_the_same_reference_is_a_clear_400(self):
        self.assertEqual(self.submit(user=self.owner, reference='TX-AAA1').status_code, 201)
        for variant in ('TX-AAA1', 'tx-aaa1', ' Tx-AaA1 '):
            response = self.submit(user=self.other, plan=self.basic, reference=variant)
            self.assertEqual(response.status_code, 400, variant)
            self.assertEqual(response.data['code'], 'reference_taken')
            self.assertIn('already submitted', response.data['error'])
        self.assertEqual(ManualPayment.objects.count(), 1)

    def test_the_same_user_sending_it_again_is_told_so(self):
        self.assertEqual(self.submit(plan=self.pro, reference='TX-AAA2').status_code, 201)
        response = self.submit(plan=self.basic, reference='tx-aaa2')
        self.assertEqual((response.status_code, response.data['code']), (400, 'reference_already_submitted'))

    def test_an_approved_reference_is_never_free_again(self):
        payment = self.make_payment(reference='TX-AAA3')
        self.assertEqual(self.approve(payment).status_code, 200)
        for user in (self.owner, self.other):
            response = self.submit(user=user, plan=self.basic, reference='TX-AAA3')
            self.assertEqual(response.status_code, 400, user)

    def test_a_rejected_reference_can_be_reused_by_the_same_user_only(self):
        payment = self.make_payment(reference='TX-AAA4')
        self.assertEqual(self.reject(payment).status_code, 200)
        other = self.submit(user=self.other, plan=self.basic, reference='tx-aaa4')
        self.assertEqual((other.status_code, other.data['code']), (400, 'reference_taken'))
        again = self.submit(user=self.owner, reference='TX-AAA4')
        self.assertEqual(again.status_code, 201, again.data)
        # ... and now the live claim is the owner's again: nobody else gets it.
        self.assertEqual(self.submit(user=self.other, plan=self.basic, reference='TX-AAA4').status_code, 400)

    def test_the_database_itself_refuses_two_live_claims_of_one_reference(self):
        self.make_payment(reference='TX-DB-1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_payment(user=self.other, plan=self.basic, reference='tx-db-1')
        # a rejected row does not take part in the constraint
        self.make_payment(user=self.other, plan=self.basic, reference='TX-DB-2', status=Status.REJECTED)
        self.make_payment(user=self.owner, reference='tx-db-2')

    def test_rows_from_before_7_5b_without_a_reference_do_not_collide(self):
        self.make_payment(reference='')
        self.make_payment(user=self.other, plan=self.basic, reference='')
        self.assertEqual(ManualPayment.objects.filter(reference_key='').count(), 2)


# ─── submit: money at submission, proof, cap, audit, bell ────────────────────

class SubmitTests(PaymentBase):
    def test_the_money_is_frozen_at_submission(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.data)
        payment = ManualPayment.objects.get()
        self.assertEqual((payment.amount, payment.currency, payment.plan_price, payment.status),
                         (self.pro.price, 'NPR', self.pro.price, 'pending'))
        original_price = self.pro.price
        self.pro.price = original_price + 500
        self.pro.save(update_fields=['price'])
        payment.refresh_from_db()
        self.assertEqual((payment.amount, payment.plan_price), (original_price, original_price))
        # staff see the frozen figures, and approving still applies the plan that was paid for
        row = self.as_user(self.staff).get(STAFF).data['results'][0]
        self.assertEqual((row['amount'], row['plan_price'], row['currency']), (str(original_price), str(original_price), 'NPR'))
        self.assertEqual(self.approve(payment).status_code, 200)
        self.assertEqual(self.subscription().plan_id, self.pro.id)

    def test_the_amount_must_equal_the_plan_price_right_now(self):
        response = self.submit(amount='1')
        self.assertEqual((response.status_code, response.data['code']), (400, 'amount_mismatch'))
        self.assertEqual(ManualPayment.objects.count(), 0)

    def test_the_free_plan_cannot_be_bought_and_anonymous_is_401(self):
        free = SubscriptionPlan.get_free()
        self.assertEqual(self.submit(plan=free, amount='0').status_code, 400)
        self.assertEqual(APIClient().post(PAYMENTS, {}, format='multipart').status_code, 401)

    def test_accepted_proof_types_are_judged_by_their_bytes(self):
        for index, (data, name, kind, ext) in enumerate((
            (image_bytes('PNG'), 'a.png', 'image/png', '.png'),
            (image_bytes('JPEG'), 'b.jpg', 'image/jpeg', '.jpg'),
            (image_bytes('WEBP'), 'c.webp', 'image/webp', '.webp'),
            (PDF, 'd.pdf', 'application/pdf', '.pdf'),
            (image_bytes('PNG'), 'misnamed.pdf', 'image/png', '.png'),     # name lies, bytes win
        )):
            user = make_user(f'proofer{index}')
            response = self.submit(user=user, reference=f'PROOF-{index:03d}', proof=upload(data, name))
            self.assertEqual(response.status_code, 201, (name, response.data))
            payment = ManualPayment.objects.get(user=user)
            self.assertEqual(payment.proof_type, kind, name)
            self.assertTrue(payment.payment_proof.name.endswith(ext), (name, payment.payment_proof.name))
            self.assertTrue(payment.payment_proof.name.startswith(f'payment_proofs/{user.pk}/'))

    def test_other_files_are_refused_and_nothing_is_stored(self):
        for name, data in (
            ('a.gif', image_bytes('GIF')), ('b.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
            ('c.png', b'MZ\x90\x00 not an image at all'), ('d.pdf', b'<html>%PDF-</html>'),
            ('e.txt', b'hello'), ('f.png', b''),
        ):
            response = self.submit(proof=upload(data, name), reference=f'BAD-{name}')
            self.assertEqual(response.status_code, 400, name)
            self.assertIn('payment_proof', response.data['errors'], name)
        self.assertEqual(ManualPayment.objects.count(), 0)

    def test_size_and_pixel_limits(self):
        with override_settings(MANUAL_PAYMENT_PROOF_MAX_MB=1):
            big = image_bytes('BMP', size=(700, 700))      # not an accepted type either way
            self.assertEqual(self.submit(proof=upload(PDF + b'0' * (1024 * 1024 + 1), 'big.pdf')).status_code, 400)
            self.assertEqual(self.submit(proof=upload(big, 'big.png'), reference='BIG-0001').status_code, 400)
        with override_settings(MANUAL_PAYMENT_PROOF_MAX_PIXELS=100):
            response = self.submit(proof=upload(image_bytes('PNG', size=(40, 30))), reference='PIX-0001')
            self.assertEqual((response.status_code, response.data['code']), (400, 'proof_too_large'))
        exact = payments.proof_max_bytes()
        self.assertEqual(exact, settings.MANUAL_PAYMENT_PROOF_MAX_MB * 1024 * 1024)
        self.assertEqual(self.submit(proof=upload(PDF + b'0' * (exact - len(PDF)), 'edge.pdf'), reference='EDGE-001').status_code, 201)

    def test_the_proof_sits_in_private_storage_and_is_not_in_any_response(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        payment = ManualPayment.objects.get()
        self.assertIsInstance(ManualPayment._meta.get_field('payment_proof').storage, PrivateMediaStorage)
        body = str(response.data)
        self.assertNotIn(payment.payment_proof.name, body)
        self.assertNotIn('payment_proofs', body)
        history = str(self.as_user(self.owner).get(PAYMENTS).data)
        self.assertNotIn('payment_proofs', history)
        self.assertNotIn('payment_proof', self.as_user(self.owner).get(PAYMENTS).data[0])
        self.assertTrue(self.as_user(self.owner).get(PAYMENTS).data[0]['has_proof'])

    def test_at_most_a_few_pending_payments_and_one_per_plan(self):
        studio = SubscriptionPlan.objects.get(key='studio')
        with override_settings(MANUAL_PAYMENT_MAX_PENDING=2):
            self.assertEqual(self.submit(plan=self.pro, reference='CAP-0001').status_code, 201)
            duplicate = self.submit(plan=self.pro, reference='CAP-0002')
            self.assertEqual((duplicate.status_code, duplicate.data['code']), (400, 'duplicate_pending'))
            self.assertEqual(self.submit(plan=self.basic, reference='CAP-0003').status_code, 201)
            capped = self.submit(plan=studio, reference='CAP-0004')
            self.assertEqual((capped.status_code, capped.data['code']), (400, 'too_many_pending'))
            self.assertEqual(self.submit(user=self.other, plan=studio, reference='CAP-0005').status_code, 201)
            # a decision frees a slot
            self.assertEqual(self.reject(ManualPayment.objects.get(reference='CAP-0001')).status_code, 200)
            self.assertEqual(self.submit(plan=studio, reference='CAP-0006').status_code, 201)

    def test_submits_are_rate_limited_per_user(self):
        with mock.patch.dict(PaymentSubmitThrottle.THROTTLE_RATES, {'payment_submit': '2/hour'}):
            client = self.as_user(self.owner)
            self.assertEqual(client.post(PAYMENTS, {}, format='multipart').status_code, 400)
            self.assertEqual(client.post(PAYMENTS, {}, format='multipart').status_code, 400)
            self.assertEqual(client.post(PAYMENTS, {}, format='multipart').status_code, 429)
            self.assertEqual(self.as_user(self.other).post(PAYMENTS, {}, format='multipart').status_code, 400)

    def test_notes_are_plain_text(self):
        self.submit(notes='<b>paid</b> <script>x()</script> from eSewa')
        self.assertEqual(ManualPayment.objects.get().notes, 'paid x() from eSewa')

    def test_submit_writes_one_audit_row_and_tells_every_active_staff_account(self):
        make_user('retired', is_staff=True, is_active=False)
        response = self.submit(reference='AUD-SEC-77')
        self.assertEqual(response.status_code, 201)
        payment = ManualPayment.objects.get()
        row = audit_rows(Action.PAYMENT_SUBMIT).get()
        self.assertEqual((row.actor_id, row.target_id), (self.owner.pk, self.owner.pk))
        self.assertEqual(row.reason, f'payment={payment.pk} plan=pro amount={self.pro.price} NPR')
        self.assertNotIn('AUD-SEC-77', row.reason)
        self.assertNotIn('proof', row.reason)
        bells = Notification.objects.filter(kind='payment_review')
        self.assertEqual(set(bells.values_list('user_id', flat=True)), {self.staff.pk, self.staff2.pk})
        self.assertIn('Pro', bells.first().message)
        self.assertNotIn('AUD-SEC-77', bells.first().message)
        from apps.users.notification_service import notification_link
        self.assertEqual(notification_link(bells.first()), '/dashboard/staff/payments')
        self.assertFalse(Notification.objects.filter(user=self.owner).exists())

    def test_a_failed_submit_leaves_no_row_no_file_no_audit_no_bell(self):
        with mock.patch('apps.subscriptions.payments.audit.record', side_effect=RuntimeError('audit down')):
            with self.assertLogs(level='ERROR'):
                response = self.submit()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(ManualPayment.objects.count(), 0)
        self.assertEqual(audit_rows().count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        import os
        leftovers = [name for _root, _dirs, names in os.walk(settings.MEDIA_ROOT) for name in names]
        self.assertEqual(leftovers, [])                         # the private file did not outlive the rolled-back row


# ─── what a user may see ─────────────────────────────────────────────────────

class OwnPaymentsTests(PaymentBase):
    def test_a_user_sees_only_their_own_payments_with_the_reject_reason(self):
        mine = self.make_payment(reference='OWN-0001')
        theirs = self.make_payment(user=self.other, plan=self.basic, reference='OWN-0002')
        self.reject(mine, reason='Wrong account name')
        rows = self.as_user(self.owner).get(PAYMENTS).data
        self.assertEqual([row['id'] for row in rows], [str(mine.pk)])
        self.assertEqual((rows[0]['status'], rows[0]['rejection_reason']), ('rejected', 'Wrong account name'))
        self.assertNotIn(str(theirs.pk), str(rows))
        self.assertEqual(set(rows[0]), {
            'id', 'plan_name', 'amount', 'currency', 'reference', 'status', 'created_at', 'reviewed_at',
            'rejection_reason', 'period_end', 'has_proof', 'notes'})

    def test_staff_calling_the_user_route_see_only_their_own(self):
        self.make_payment(reference='OWN-0003')
        self.assertEqual(self.as_user(self.staff).get(PAYMENTS).data, [])

    def test_instructions_come_from_the_admin_row_and_need_a_signed_in_user(self):
        self.assertEqual(APIClient().get(INSTRUCTIONS).status_code, 401)
        row = PaymentInstructions.load()
        row.account_name, row.esewa_id, row.bank_name = 'Kyapture Pvt Ltd', '9800000000', 'Nabil Bank'
        row.bank_account_number, row.note = '0123456789', 'Reviews take about a day.'
        row.save()
        data = self.as_user(self.owner).get(INSTRUCTIONS).data
        self.assertEqual((data['account_name'], data['esewa_id'], data['bank_name'], data['bank_account_number'],
                          data['note'], data['qr_url'], data['currency']),
                         ('Kyapture Pvt Ltd', '9800000000', 'Nabil Bank', '0123456789', 'Reviews take about a day.', None, 'NPR'))
        self.assertEqual((data['period_days'], data['proof_max_mb'], data['max_pending']),
                         (settings.MANUAL_PAYMENT_PERIOD_DAYS, settings.MANUAL_PAYMENT_PROOF_MAX_MB,
                          settings.MANUAL_PAYMENT_MAX_PENDING))
        with override_settings(MANUAL_PAYMENT_PERIOD_DAYS=45, MANUAL_PAYMENT_MAX_PENDING=2):
            changed = self.as_user(self.owner).get(INSTRUCTIONS).data
        self.assertEqual((changed['period_days'], changed['max_pending']), (45, 2))

    def test_instructions_text_is_plain_and_the_row_holds_no_secret_field(self):
        row = PaymentInstructions.load()
        row.account_name = '<img src=x onerror=alert(1)>Kyapture'
        row.note = '<script>steal()</script>Send NPR only.'
        row.save()
        row.refresh_from_db()
        self.assertEqual(row.account_name, 'Kyapture')
        self.assertEqual(row.note, 'steal()Send NPR only.')
        names = {field.name for field in PaymentInstructions._meta.fields}
        self.assertEqual(names, {'id', 'account_name', 'esewa_id', 'bank_name', 'bank_account_number', 'bank_branch',
                                 'qr_image', 'note', 'updated_at'})
        self.assertEqual(PaymentInstructions.objects.count(), 1)

    def test_the_qr_is_a_re_encoded_public_image(self):
        form = PaymentInstructionsForm(
            data={'account_name': 'K'}, files={'qr_image': upload(image_bytes('PNG', (64, 64)), 'qr.png')},
            instance=PaymentInstructions.load())
        self.assertTrue(form.is_valid(), form.errors)
        row = form.save()
        self.assertRegex(row.qr_image.name, r'^payment_instructions/qr_[0-9a-f]{16}\.png$')
        self.assertTrue(self.as_user(self.owner).get(INSTRUCTIONS).data['qr_url'].endswith(row.qr_image.name))
        from apps.core.media import is_public_path
        self.assertTrue(is_public_path(row.qr_image.name))
        bad = PaymentInstructionsForm(
            data={'account_name': 'K'}, files={'qr_image': upload(b'<svg/>', 'qr.svg')}, instance=PaymentInstructions.load())
        self.assertFalse(bad.is_valid())

    def test_the_payment_admin_is_read_only_and_instructions_are_one_row(self):
        request = RequestFactory().get('/admin/')
        request.user = make_user('boss', is_staff=True, is_superuser=True)
        model_admin = PaymentAdmin(ManualPayment, django_admin.site)
        payment = self.make_payment()
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, payment))
        self.assertFalse(model_admin.has_delete_permission(request, payment))
        self.assertIn('status', model_admin.get_readonly_fields(request, payment))
        instructions = PaymentInstructionsAdmin(PaymentInstructions, django_admin.site)
        PaymentInstructions.load()
        self.assertFalse(instructions.has_add_permission(request))
        self.assertFalse(instructions.has_delete_permission(request))


# ─── staff only, and nobody reads another user's payment ─────────────────────

class StaffOnlyTests(PaymentBase):
    def routes(self, payment):
        return [
            ('get', STAFF, None), ('get', f'{STAFF}?status=all', None),
            ('post', f'{STAFF}{payment.pk}/approve/', {}),
            ('post', f'{STAFF}{payment.pk}/reject/', {'reason': 'x'}),
            ('post', f'{STAFF}{payment.pk}/proof-link/', {}),
            ('get', f'{STAFF}{payment.pk}/proof/?s=whatever', None),
        ]

    def call(self, client, method, url, body):
        return client.get(url) if method == 'get' else client.post(url, body, format='json')

    def test_anonymous_is_401_and_a_normal_user_is_403_everywhere_and_nothing_changes(self):
        payment = self.make_payment()
        for method, url, body in self.routes(payment):
            self.assertEqual(self.call(APIClient(), method, url, body).status_code, 401, url)
            for user in (self.other, self.owner):               # the payer too: it is their own payment
                response = self.call(self.as_user(user), method, url, body)
                self.assertEqual(response.status_code, 403, f'{method} {url}')
                self.assertNotIn(self.owner.email, response.content.decode(), url)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')
        self.assertIsNone(self.subscription())
        self.assertEqual(audit_rows(Action.PAYMENT_APPROVE).count() + audit_rows(Action.PAYMENT_REJECT).count()
                         + audit_rows(Action.PAYMENT_PROOF_VIEW).count() + audit_rows(Action.INBOX_VIEW).count(), 0)

    def test_a_superuser_who_is_not_staff_is_refused(self):
        boss = make_user('bossman', is_superuser=True)
        self.assertEqual(self.as_user(boss).get(STAFF).status_code, 403)

    def test_the_old_unlocked_review_routes_are_gone(self):
        payment = self.make_payment()
        staff = self.as_user(self.staff)
        self.assertEqual(staff.post(f'/api/v1/subscriptions/payments/{payment.pk}/review/', {'action': 'approve'},
                                    format='json').status_code, 404)
        self.assertEqual(staff.get('/api/v1/subscriptions/admin/payments/').status_code, 404)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')

    def test_the_queue_is_oldest_first_paginated_filterable_and_audited(self):
        first = self.make_payment(reference='Q-0001')
        second = self.make_payment(user=self.other, plan=self.basic, reference='Q-0002')
        self.reject(second)
        staff = self.as_user(self.staff)
        data = staff.get(STAFF).data
        self.assertEqual([row['id'] for row in data['results']], [str(first.pk)])
        self.assertEqual(data['count'], 1)
        self.assertEqual({row['status'] for row in staff.get(f'{STAFF}?status=all').data['results']}, {'pending', 'rejected'})
        self.assertEqual(staff.get(f'{STAFF}?status=bogus').status_code, 400)
        self.assertEqual(audit_rows(Action.INBOX_VIEW).count(), 2)
        self.assertEqual(audit_rows(Action.INBOX_VIEW).filter(reason='payments status=pending').count(), 1)

    def test_a_staff_row_is_an_allowlist_with_no_storage_path_or_url(self):
        self.make_payment(reference='ROW-0001')
        row = self.as_user(self.staff).get(STAFF).data['results'][0]
        self.assertEqual(set(row), {
            'id', 'user_id', 'email', 'name', 'plan', 'plan_name', 'plan_price', 'amount', 'currency', 'reference',
            'notes', 'status', 'created_at', 'reviewed_at', 'reviewed_by', 'rejection_reason', 'period_start',
            'period_end', 'has_proof', 'proof_type', 'proof_size', 'current_plan_name', 'current_period_end',
            'can_review'})
        self.assertNotIn('payment_proofs', str(row))
        self.assertTrue(row['can_review'])

    def test_a_missing_payment_is_404_for_staff(self):
        import uuid
        staff = self.as_user(self.staff)
        missing = uuid.uuid4()
        self.assertEqual(staff.post(f'{STAFF}{missing}/approve/', {}, format='json').status_code, 404)
        self.assertEqual(staff.post(f'{STAFF}{missing}/reject/', {'reason': 'x'}, format='json').status_code, 404)
        self.assertEqual(staff.post(f'{STAFF}{missing}/proof-link/', {}, format='json').status_code, 404)


# ─── approve ─────────────────────────────────────────────────────────────────

class ApproveTests(PaymentBase):
    def test_approve_flips_the_entitlement_at_once(self):
        gallery = Gallery.objects.create(photographer=self.owner, title='Wedding', slug='wedding-75b')
        original = {'design_settings': {'downloads': {'high_res': {'enabled': True, 'mode': 'original'}}}}
        owner = self.as_user(self.owner)
        before = get_feature_entitlements(self.owner)
        self.assertEqual((before['branding'], before['watermark'], before['original_download']), (False, False, False))
        gate = owner.patch(f'/api/v1/galleries/{gallery.slug}/', original, format='json')
        self.assertEqual((gate.status_code, gate.data['code']), (403, 'original_download_requires_upgrade'))
        # a choice stored earlier (say, while on Pro) has no effect while the account is Free
        gallery.design_settings = original['design_settings']
        gallery.save(update_fields=['design_settings'])
        self.assertEqual(effective_high_res_mode(gallery), '3600')
        gallery.design_settings = {}
        gallery.save(update_fields=['design_settings'])

        payment = self.make_payment()
        response = self.approve(payment)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['changed'])

        after = get_feature_entitlements(self.owner)
        self.assertEqual((after['branding'], after['watermark'], after['original_download'], after['plan_name']),
                         (True, True, True, 'Pro'))
        gate = owner.patch(f'/api/v1/galleries/{gallery.slug}/', original, format='json')
        self.assertEqual(gate.status_code, 200, gate.data)
        gallery.refresh_from_db()
        self.assertEqual(effective_high_res_mode(gallery), 'original')
        mine = owner.get('/api/v1/subscriptions/my-subscription/').data
        self.assertEqual((mine['plan']['key'], mine['status'], mine['entitlements']['original_download']), ('pro', 'active', True))
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active_plan)

    def test_the_plan_applied_is_the_one_paid_for_through_the_plan_table(self):
        self.basic.original_download = True               # an owner edit in admin: no plan name in code
        self.basic.save(update_fields=['original_download'])
        payment = self.make_payment(plan=self.basic)
        self.approve(payment)
        self.assertEqual(self.subscription().plan_id, self.basic.id)
        entitled = get_feature_entitlements(self.owner)
        self.assertEqual((entitled['plan_name'], entitled['original_download'], entitled['branding']), ('Basic', True, False))

    def test_the_period_is_the_setting_in_days_from_now_for_a_new_subscriber(self):
        payment = self.make_payment()
        before = timezone.now()
        self.approve(payment)
        sub, payment = self.subscription(), ManualPayment.objects.get(pk=payment.pk)
        days = timedelta(days=settings.MANUAL_PAYMENT_PERIOD_DAYS)
        self.assertEqual(settings.MANUAL_PAYMENT_PERIOD_DAYS, 30)
        self.assertAlmostEqual((sub.expires_at - before).total_seconds(), days.total_seconds(), delta=30)
        self.assertEqual((payment.period_start, payment.period_end), (sub.starts_at, sub.expires_at))
        self.assertEqual((payment.status, payment.verified_by_id), ('approved', self.staff.pk))
        self.assertIsNotNone(payment.reviewed_at)

    @override_settings(MANUAL_PAYMENT_PERIOD_DAYS=45)
    def test_the_number_of_days_is_a_setting(self):
        self.approve(self.make_payment())
        sub = self.subscription()
        self.assertAlmostEqual((sub.expires_at - timezone.now()).total_seconds(), 45 * 86400, delta=30)

    def test_already_on_that_plan_extends_from_the_current_end_date(self):
        grant_plan(self.owner, name='Pro', days=10)
        old = self.subscription()
        self.approve(self.make_payment())
        sub = self.subscription()
        self.assertEqual(sub.starts_at, old.starts_at)
        self.assertEqual(sub.expires_at, old.expires_at + timedelta(days=30))
        self.assertEqual(sub.status, 'active')

    def test_another_plan_or_a_lapsed_one_starts_now_instead(self):
        grant_plan(self.owner, name='Basic', days=10)                       # live, but another plan
        self.approve(self.make_payment(plan=self.pro, reference='ANO-0001'))
        sub = self.subscription()
        self.assertEqual(sub.plan_id, self.pro.id)
        self.assertAlmostEqual((sub.expires_at - timezone.now()).total_seconds(), 30 * 86400, delta=30)

        lapsed = make_user('lapsed')
        grant_plan(lapsed, name='Pro', days=-5)
        self.approve(self.make_payment(user=lapsed, reference='ANO-0002'))
        sub = self.subscription(lapsed)
        self.assertAlmostEqual((sub.expires_at - timezone.now()).total_seconds(), 30 * 86400, delta=30)
        self.assertEqual(sub.status, 'active')

    def test_the_audit_row_the_bell_and_the_email(self):
        payment = self.make_payment(reference='MAIL-REF-1')
        self.assertEqual(self.approve(payment).status_code, 200)
        row = audit_rows(Action.PAYMENT_APPROVE).get()
        self.assertEqual((row.actor_id, row.target_id, row.target_email), (self.staff.pk, self.owner.pk, self.owner.email))
        self.assertEqual(row.reason, f'payment={payment.pk} plan=pro amount={self.pro.price} NPR')
        for forbidden in ('MAIL-REF-1', 'proof', '.png'):
            self.assertNotIn(forbidden, row.reason)
        self.assertEqual(Notification.objects.filter(user=self.owner, kind='payment').count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.owner.email])
        self.assertIn('approved', mail.outbox[0].subject)
        self.assertIn(f'{ManualPayment.objects.get().period_end:%d %b %Y}', mail.outbox[0].body)

    def test_a_double_click_changes_nothing_and_says_so(self):
        payment = self.make_payment()
        first = self.approve(payment)
        sub_after_first = self.subscription().expires_at
        second = self.approve(payment)
        self.assertEqual((first.status_code, first.data['changed']), (200, True))
        self.assertEqual((second.status_code, second.data['changed'], second.data['code']), (200, False, 'already_approved'))
        self.assertIn('Nothing was changed', second.data['message'])
        self.assertEqual(self.subscription().expires_at, sub_after_first)
        self.assertEqual(UserSubscription.objects.filter(user=self.owner).count(), 1)
        self.assertEqual(audit_rows(Action.PAYMENT_APPROVE).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Notification.objects.filter(user=self.owner, kind='payment').count(), 1)

    def test_a_reject_after_an_approve_changes_nothing_and_says_so(self):
        payment = self.make_payment()
        self.approve(payment)
        response = self.reject(payment)
        self.assertEqual((response.status_code, response.data['code']), (409, 'already_approved'))
        payment.refresh_from_db()
        self.assertEqual((payment.status, payment.rejection_reason), ('approved', ''))
        self.assertEqual(self.subscription().plan_id, self.pro.id)
        self.assertEqual(audit_rows(Action.PAYMENT_REJECT).count(), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_an_approve_after_a_reject_is_refused(self):
        payment = self.make_payment()
        self.reject(payment)
        response = self.approve(payment)
        self.assertEqual((response.status_code, response.data['code']), (409, 'already_rejected'))
        self.assertIsNone(self.subscription())
        self.assertEqual(audit_rows(Action.PAYMENT_APPROVE).count(), 0)

    def test_staff_cannot_approve_or_reject_their_own_payment(self):
        mine = self.make_payment(user=self.staff, reference='SELF-0001')
        for response in (self.approve(mine), self.reject(mine)):
            self.assertEqual((response.status_code, response.data['code']), (403, 'cannot_review_own'))
        mine.refresh_from_db()
        self.assertEqual(mine.status, 'pending')
        self.assertIsNone(self.subscription(self.staff))
        self.assertEqual(audit_rows(Action.PAYMENT_APPROVE).count() + audit_rows(Action.PAYMENT_REJECT).count(), 0)
        self.assertFalse(self.as_user(self.staff).get(STAFF).data['results'][0]['can_review'])
        # another staff member can
        self.assertEqual(self.approve(mine, client=self.as_user(self.staff2)).status_code, 200)

    def test_a_failure_inside_the_review_rolls_everything_back(self):
        payment = self.make_payment()
        with mock.patch('apps.subscriptions.payments.audit.record', side_effect=RuntimeError('SECRET-SQL-DETAIL')):
            response = self.approve(payment)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('SECRET-SQL-DETAIL', str(response.data))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')
        self.assertIsNone(self.subscription())
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active_plan)
        self.assertEqual((len(mail.outbox), Notification.objects.filter(user=self.owner).count()), (0, 0))

    def test_payment_alerts_off_still_applies_the_plan_but_sends_no_mail(self):
        self.owner.notify_payments = False
        self.owner.save(update_fields=['notify_payments'])
        self.approve(self.make_payment())
        self.assertEqual(self.subscription().plan_id, self.pro.id)
        self.assertEqual(mail.outbox, [])


# ─── reject ──────────────────────────────────────────────────────────────────

class RejectTests(PaymentBase):
    def test_reject_leaves_the_plan_unchanged_and_shows_the_reason(self):
        grant_plan(self.owner, name='Basic', includes_branding_watermark=False, days=12)
        before = self.subscription()
        payment = self.make_payment(plan=self.pro)
        response = self.reject(payment, reason='The receipt is for a different account')
        self.assertEqual((response.status_code, response.data['changed'], response.data['code']), (200, True, 'rejected'))
        after = self.subscription()
        self.assertEqual((after.plan_id, after.status, after.starts_at, after.expires_at),
                         (before.plan_id, before.status, before.starts_at, before.expires_at))
        entitled = get_feature_entitlements(self.owner)
        self.assertEqual((entitled['plan_name'], entitled['original_download']), ('Basic', False))
        payment.refresh_from_db()
        self.assertEqual((payment.status, payment.verified_by_id, payment.period_end), ('rejected', self.staff.pk, None))
        shown = self.as_user(self.owner).get(PAYMENTS).data[0]
        self.assertEqual(shown['rejection_reason'], 'The receipt is for a different account')

    def test_a_rejected_payment_on_a_free_account_unlocks_nothing(self):
        gallery = Gallery.objects.create(photographer=self.owner, title='Shoot', slug='shoot-75b')
        self.reject(self.make_payment())
        self.assertIsNone(self.subscription())
        entitled = get_feature_entitlements(self.owner)
        self.assertEqual((entitled['branding'], entitled['watermark'], entitled['original_download']), (False, False, False))
        gate = self.as_user(self.owner).patch(
            f'/api/v1/galleries/{gallery.slug}/',
            {'design_settings': {'downloads': {'high_res': {'enabled': True, 'mode': 'original'}}}}, format='json')
        self.assertEqual(gate.status_code, 403)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active_plan)

    def test_a_reason_is_required_plain_and_length_limited(self):
        payment = self.make_payment()
        staff = self.as_user(self.staff)
        for body in ({}, {'reason': ''}, {'reason': '   '}, {'reason': 7}):
            response = staff.post(f'{STAFF}{payment.pk}/reject/', body, format='json')
            self.assertEqual((response.status_code, response.data['code']), (400, 'reason_required'), body)
        long = staff.post(f'{STAFF}{payment.pk}/reject/', {'reason': 'x' * 301}, format='json')
        self.assertEqual((long.status_code, long.data['code']), (400, 'reason_too_long'))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')
        ok = staff.post(f'{STAFF}{payment.pk}/reject/', {'reason': 'Line one\nline\ttwo \x00 <b>bold</b>'}, format='json')
        self.assertEqual(ok.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.rejection_reason, 'Line one line two <b>bold</b>')      # one line; escaped when displayed

    def test_the_user_is_emailed_the_reason_and_gets_a_bell(self):
        self.reject(self.make_payment(), reason='Receipt unreadable')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Receipt unreadable', mail.outbox[0].body)
        self.assertIn('Your plan has not changed', mail.outbox[0].body)
        self.assertIn('could not be approved', mail.outbox[0].subject)
        self.assertEqual(Notification.objects.filter(user=self.owner, kind='payment').count(), 1)

    def test_one_audit_row_a_repeat_is_idempotent(self):
        payment = self.make_payment()
        first = self.reject(payment, reason='First reason')
        second = self.reject(payment, reason='Second reason')
        self.assertEqual((first.data['changed'], second.status_code, second.data['changed'], second.data['code']),
                         (True, 200, False, 'already_rejected'))
        payment.refresh_from_db()
        self.assertEqual(payment.rejection_reason, 'First reason')
        row = audit_rows(Action.PAYMENT_REJECT).get()
        self.assertEqual((row.actor_id, row.target_id), (self.staff.pk, self.owner.pk))
        self.assertEqual(row.reason, f'payment={payment.pk} plan=pro amount={self.pro.price} NPR')
        self.assertNotIn('First reason', row.reason)
        self.assertEqual(len(mail.outbox), 1)


# ─── the single entitlement check at request time ────────────────────────────

class ExpiredPeriodTests(PaymentBase):
    """An 'active' row whose period ended is Free the moment the clock passes it - no sweep has to run."""

    def lapse(self):
        UserSubscription.objects.filter(user=self.owner).update(expires_at=timezone.now() - timedelta(seconds=1))

    def test_an_expired_period_is_free_even_though_no_job_ever_ran(self):
        self.approve(self.make_payment())
        self.assertTrue(get_feature_entitlements(self.owner)['original_download'])
        self.lapse()
        sub = self.subscription()
        self.assertEqual(sub.status, 'active')                      # the sweep has not run, the flag still says active
        entitled = get_feature_entitlements(self.owner)
        self.assertEqual((entitled['branding'], entitled['watermark'], entitled['original_download'], entitled['plan_name']),
                         (False, False, False, None))
        self.assertEqual(entitlements.entitlements_for_subscription(self.owner, sub)['original_download'], False)
        from apps.core.utils import get_user_subscription_metrics
        metrics = get_user_subscription_metrics(self.owner)
        free = SubscriptionPlan.get_free()
        self.assertEqual((metrics['plan_name'], metrics['storage_bytes_limit'], metrics['max_galleries']),
                         ('Free', free.storage_gb * GB, free.max_collections))
        self.assertEqual(UserSubscription.objects.get(user=self.owner).status, 'active')    # still untouched

    def test_requests_made_after_the_period_ends_are_refused_at_request_time(self):
        gallery = Gallery.objects.create(photographer=self.owner, title='Late', slug='late-75b')
        self.approve(self.make_payment())
        owner = self.as_user(self.owner)
        patch = {'design_settings': {'downloads': {'high_res': {'enabled': True, 'mode': 'original'}}}}
        self.assertEqual(owner.patch(f'/api/v1/galleries/{gallery.slug}/', patch, format='json').status_code, 200)
        self.lapse()
        back = {'design_settings': {'downloads': {'high_res': {'enabled': True, 'mode': '3600'}}}}
        self.assertEqual(owner.patch(f'/api/v1/galleries/{gallery.slug}/', back, format='json').status_code, 200)
        gate = owner.patch(f'/api/v1/galleries/{gallery.slug}/', patch, format='json')
        self.assertEqual((gate.status_code, gate.data['code']), (403, 'original_download_requires_upgrade'))
        gallery.design_settings = patch['design_settings']                  # a choice stored while it was Pro
        gallery.save(update_fields=['design_settings'])
        self.assertEqual(effective_high_res_mode(gallery), '3600')        # the stored choice stays, the effect stops
        self.assertEqual(gallery.design_settings['downloads']['high_res']['mode'], 'original')

    def test_the_profile_flag_follows_the_live_plan_not_the_stale_column(self):
        me = '/api/v1/auth/me/'
        owner = self.as_user(self.owner)
        self.assertFalse(owner.get(me).data['is_active_plan'])
        self.approve(self.make_payment())
        self.assertTrue(owner.get(me).data['is_active_plan'])
        self.lapse()
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active_plan)                       # the column is stale until a sweep ...
        self.assertFalse(owner.get(me).data['is_active_plan'])           # ... the API is not
        User.objects.filter(pk=self.owner.pk).update(is_active_plan=False)
        UserSubscription.objects.filter(user=self.owner).update(expires_at=timezone.now() + timedelta(days=3))
        self.assertTrue(owner.get(me).data['is_active_plan'])            # a live plan reads true whatever the column says

    def test_nothing_is_deleted_and_storage_over_the_free_limit_follows_the_billc_rules(self):
        gallery = Gallery.objects.create(photographer=self.owner, title='Big', slug='big-75b')
        self.approve(self.make_payment())
        free = SubscriptionPlan.get_free()
        used = free.storage_gb * GB + 5
        MediaAsset.objects.create(
            gallery=gallery, original_file=SimpleUploadedFile('fill.jpg', b'x'), original_name='fill.jpg',
            file_size=used, order=Decimal(1), processing_status=MediaAsset.ProcessingStatus.READY)
        payment_count = ManualPayment.objects.count()
        self.lapse()

        from apps.core.utils import get_user_subscription_metrics
        figures = storage_figures(get_user_subscription_metrics(self.owner))
        self.assertEqual(figures['storage_state'], 'over')
        self.assertEqual(figures['storage_used_bytes'], used)
        # BILL-C: an account over its limit keeps everything and cannot add more
        upload_url = f'/api/v1/photos/{gallery.slug}/upload/'
        buf = io.BytesIO()
        Image.new('RGB', (30, 30), 'white').save(buf, 'JPEG')
        refused = self.as_user(self.owner).post(
            upload_url, {'image': [SimpleUploadedFile('more.jpg', buf.getvalue(), content_type='image/jpeg')]},
            format='multipart')
        self.assertEqual((refused.status_code, refused.data['code']), (403, 'storage_limit_reached'))
        self.assertEqual(MediaAsset.objects.filter(gallery=gallery).count(), 1)
        self.assertTrue(Gallery.objects.filter(pk=gallery.pk).exists())
        self.assertEqual(ManualPayment.objects.count(), payment_count)
        self.assertTrue(UserSubscription.objects.filter(user=self.owner).exists())
        self.assertEqual(self.as_user(self.owner).get('/api/v1/galleries/dashboard/stats/').status_code, 200)


# ─── the staff link to a proof ───────────────────────────────────────────────

class CaptureLogs(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


class ProofLinkTests(PaymentBase):
    def link(self, payment, client=None):
        response = (client or self.as_user(self.staff)).post(f'{STAFF}{payment.pk}/proof-link/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_staff_open_a_proof_through_a_signed_short_lived_link(self):
        data = image_bytes('PNG', (33, 21))
        payment = self.make_payment(data=data)
        staff = self.as_user(self.staff)
        minted = self.link(payment)
        self.assertEqual((minted['expires_in'], minted['content_type']),
                         (settings.MANUAL_PAYMENT_PROOF_LINK_SECONDS, 'image/png'))
        self.assertNotIn('payment_proofs', minted['url'])
        self.assertNotIn(payment.payment_proof.name, str(minted))
        response = staff.get(minted['url'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), data)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        self.assertIn("default-src 'none'", response['Content-Security-Policy'])
        row = audit_rows(Action.PAYMENT_PROOF_VIEW).get()
        self.assertEqual((row.actor_id, row.target_id), (self.staff.pk, self.owner.pk))
        self.assertNotIn('payment_proofs', row.reason)

    def test_a_pdf_proof_is_served_as_a_pdf(self):
        payment = self.make_payment(data=PDF, ext='pdf')
        payment.proof_type = 'application/pdf'
        payment.save(update_fields=['proof_type'])
        response = self.as_user(self.staff).get(self.link(payment)['url'])
        self.assertEqual((response.status_code, response['Content-Type']), (200, 'application/pdf'))
        self.assertEqual(b''.join(response.streaming_content), PDF)

    def test_the_link_is_bound_to_the_payment_the_staff_member_and_the_clock(self):
        first, second = self.make_payment(reference='LNK-0001'), self.make_payment(user=self.other, plan=self.basic, reference='LNK-0002')
        url = self.link(first)['url']
        token = url.split('?s=')[1]
        staff, staff2, normal = self.as_user(self.staff), self.as_user(self.staff2), self.as_user(self.other)
        self.assertEqual(staff.get(f'{STAFF}{first.pk}/proof/').status_code, 403)                 # no link at all
        self.assertEqual(staff.get(f'{STAFF}{first.pk}/proof/?s=junk').status_code, 403)
        self.assertEqual(staff.get(f'{STAFF}{first.pk}/proof/?s={token[:-2]}xx').status_code, 403)  # tampered
        self.assertEqual(staff.get(f'{STAFF}{second.pk}/proof/?s={token}').status_code, 403)      # another payment
        self.assertEqual(staff2.get(url).status_code, 403)                                        # another staff member
        self.assertEqual(normal.get(url).status_code, 403)                                        # not staff at all
        self.assertEqual(APIClient().get(url).status_code, 401)
        self.assertEqual(staff.get(url).status_code, 200)
        with mock.patch('django.core.signing.time.time', return_value=time.time() + settings.MANUAL_PAYMENT_PROOF_LINK_SECONDS + 5):
            expired = staff.get(url)
        self.assertEqual((expired.status_code, expired.data['code']), (403, 'proof_link_invalid'))

    def test_a_missing_file_is_a_clean_404(self):
        payment = self.make_payment()
        url = self.link(payment)['url']
        payment.payment_proof.delete(save=False)
        self.assertEqual(self.as_user(self.staff).get(url).status_code, 404)

    def test_the_proof_and_its_link_never_reach_a_log(self):
        capture = CaptureLogs()
        root = logging.getLogger()
        previous = root.level
        root.addHandler(capture)
        root.setLevel(logging.DEBUG)
        try:
            payment = self.make_payment(reference='LOG-SECRET-9')
            minted = self.link(payment)
            self.as_user(self.staff).get(minted['url'])
            self.as_user(self.other).get(minted['url'])                      # a refused attempt is logged by Django too
            self.approve(payment)
            self.submit(user=self.other, plan=self.basic, reference='LOG-SECRET-8')
        finally:
            root.removeHandler(capture)
            root.setLevel(previous)
        text = '\n'.join(capture.lines)
        token = minted['url'].split('?s=')[1]
        for secret in (token, payment.payment_proof.name, 'payment_proofs', 'LOG-SECRET-9', 'LOG-SECRET-8'):
            self.assertNotIn(secret, text)

    def test_the_user_cannot_get_a_link_or_the_file_of_any_payment_by_id(self):
        payment = self.make_payment()
        staff_url = self.link(payment)['url']
        for client in (self.as_user(self.owner), self.as_user(self.other)):
            self.assertEqual(client.post(f'{STAFF}{payment.pk}/proof-link/', {}, format='json').status_code, 403)
            self.assertEqual(client.get(staff_url).status_code, 403)
        # the private file is not on any public route either
        self.assertEqual(self.client.get(f'/media/{payment.payment_proof.name}').status_code, 404)


# ─── two staff at once, two submits at once ──────────────────────────────────

class RaceTests(TransactionTestCase):
    """Real threads on real commits. Plan rows are re-created in setUp (no serialized_rollback)."""

    def setUp(self):
        cache.clear()
        MediaSandbox.enter.__func__(type(self))
        self.addCleanup(MediaSandbox.leave.__func__, type(self))
        ensure_seed_plans()
        self.staffs = [make_user(f'racestaff{i}', is_staff=True) for i in range(3)]
        self.owner = make_user('racepayer')
        self.pro = SubscriptionPlan.objects.get(key='pro')
        self.basic = SubscriptionPlan.objects.get(key='basic')
        self.studio = SubscriptionPlan.objects.get(key='studio')
        patcher = mock.patch('apps.users.tasks.send_notification_email.delay',
                             side_effect=lambda *args: deliver_notification(*args))
        patcher.start()
        self.addCleanup(patcher.stop)

    def payment(self, user, plan, reference):
        payment = ManualPayment(user=user, plan=plan, amount=plan.price, plan_price=plan.price, reference=reference,
                                proof_type='image/png', proof_size=1)
        payment.payment_proof.save('proof.png', ContentFile(image_bytes()), save=False)
        payment.save()
        return payment

    def run_threads(self, jobs):
        barrier = threading.Barrier(len(jobs))
        results = [None] * len(jobs)

        def worker(index, job):
            try:
                barrier.wait(timeout=10)
                results[index] = job()
            except Exception as error:               # surfaced by the assertions below
                results[index] = error
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(i, job)) for i, job in enumerate(jobs)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        return results

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_two_staff_approving_one_payment_at_once_flip_it_exactly_once(self):
        payment = self.payment(self.owner, self.pro, 'RACE-0001')
        url = f'{STAFF}{payment.pk}/approve/'
        results = self.run_threads([lambda s=s: self.api(s).post(url, {}, format='json') for s in self.staffs])
        for result in results:
            self.assertEqual(getattr(result, 'status_code', None), 200, result)
        self.assertEqual(sorted(r.data['changed'] for r in results), [False, False, True])
        self.assertEqual(UserSubscription.objects.filter(user=self.owner).count(), 1)
        sub = UserSubscription.objects.get(user=self.owner)
        self.assertAlmostEqual((sub.expires_at - timezone.now()).total_seconds(), 30 * 86400, delta=60)   # one period, not three
        self.assertEqual(StaffAuditLog.objects.filter(action=Action.PAYMENT_APPROVE).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.owner, kind='payment').count(), 1)
        self.assertEqual(ManualPayment.objects.get(pk=payment.pk).status, 'approved')

    def test_an_approve_and_a_reject_at_once_end_in_one_state_only(self):
        payment = self.payment(self.owner, self.pro, 'RACE-0002')
        approve, reject = f'{STAFF}{payment.pk}/approve/', f'{STAFF}{payment.pk}/reject/'
        results = self.run_threads([
            lambda: self.api(self.staffs[0]).post(approve, {}, format='json'),
            lambda: self.api(self.staffs[1]).post(reject, {'reason': 'No'}, format='json'),
        ])
        payment = ManualPayment.objects.get(pk=payment.pk)
        self.assertIn(payment.status, ('approved', 'rejected'))
        self.assertEqual(sorted(getattr(r, 'status_code', 0) for r in results), [200, 409], results)
        has_plan = UserSubscription.objects.filter(user=self.owner).exists()
        self.assertEqual(has_plan, payment.status == 'approved')
        self.assertEqual(StaffAuditLog.objects.filter(action__in=[Action.PAYMENT_APPROVE, Action.PAYMENT_REJECT]).count(), 1)

    def test_two_payments_of_one_user_approved_together_add_both_periods(self):
        first = self.payment(self.owner, self.pro, 'RACE-0003')
        second = self.payment(self.owner, self.pro, 'RACE-0004')
        results = self.run_threads([
            lambda p=p, s=s: self.api(s).post(f'{STAFF}{p.pk}/approve/', {}, format='json')
            for p, s in ((first, self.staffs[0]), (second, self.staffs[1]))
        ])
        self.assertEqual([getattr(r, 'status_code', None) for r in results], [200, 200], results)
        sub = UserSubscription.objects.get(user=self.owner)
        self.assertAlmostEqual((sub.expires_at - timezone.now()).total_seconds(), 60 * 86400, delta=60)      # no lost update

    def test_two_users_submitting_one_reference_at_once_get_one_payment(self):
        other = make_user('racepayer2')
        jobs = [
            lambda u=u: self.api(u).post(PAYMENTS, {
                'plan': str(self.pro.id), 'amount': str(self.pro.price), 'reference': 'SAME-REF-1',
                'payment_proof': upload()}, format='multipart')
            for u in (self.owner, other)
        ]
        results = self.run_threads(jobs)
        self.assertEqual(sorted(getattr(r, 'status_code', 0) for r in results), [201, 400], results)
        self.assertEqual(ManualPayment.objects.filter(reference_key='same-ref-1').count(), 1)

    def test_parallel_submits_of_one_user_cannot_pass_the_pending_cap(self):
        with override_settings(MANUAL_PAYMENT_MAX_PENDING=1):
            jobs = [
                lambda plan=plan, i=i: self.api(self.owner).post(PAYMENTS, {
                    'plan': str(plan.id), 'amount': str(plan.price), 'reference': f'CAPRACE-{i}',
                    'payment_proof': upload()}, format='multipart')
                for i, plan in enumerate((self.basic, self.pro, self.studio))
            ]
            results = self.run_threads(jobs)
        self.assertEqual(sorted(getattr(r, 'status_code', 0) for r in results), [201, 400, 400], results)
        self.assertEqual(ManualPayment.objects.filter(user=self.owner, status='pending').count(), 1)
