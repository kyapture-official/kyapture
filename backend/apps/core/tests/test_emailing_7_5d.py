# backend/apps/core/tests/test_emailing_7_5d.py
"""
CHUNK 7.5-D - one shared base for every transactional email (apps/core/emailing.py).

  - Every email of the audit is an entry of EMAILS and renders in HTML and in text on the SAME base; no other
    code path builds a mail (a source scan fails on a stray send_mail / EmailMessage).
  - Subjects are fixed strings: no user text, no code, no token. There is no way to pass one.
  - Every user-supplied value is HTML-escaped and folded to one line; no header can be injected.
  - Links come from FRONTEND_URL only (never localhost unless FRONTEND_URL says so); the password-reset token
    stays in the #fragment.
  - No remote image, no web font, no tracking pixel, no script. 600 px card, system fonts, dark-mode rules.
  - Sender and Reply-To come from settings. The new mails: payment received, plan expiring, plan ended, and the
    staff alert (one env address; id, plan, amount and the staff link only).
  - A failed send never reaches the user: a request is not failed by a broker or mail error.
"""
import inspect
import re
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from smtplib import SMTPException
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.template.loader import get_template
from django.test import SimpleTestCase, override_settings

from apps.clients.download_access import _email_code_key, send_email_code
from apps.clients.models import DownloadLog
from apps.core import emailing
from apps.core.emailing import EMAILS, app_url, clean_line, render_email, safe_send_email, send_email
from apps.galleries.models import Gallery
from apps.subscriptions.models import ManualPayment
from apps.subscriptions.tests.test_lifecycle_7_5c import END, LifecycleBase, give_period, mails_to, npt
from apps.subscriptions.tests.test_payment_review_7_5b import PaymentBase, make_user
from apps.users import tasks as user_tasks
from apps.users.notifications import deliver_notification, deliver_staff_alert
from apps.users.password_reset import reset_link

APP = 'https://app.example.test'
BACKEND = Path(emailing.__file__).resolve().parents[2]      # the backend folder (BASE_DIR differs between hosts)
HOSTILE = '<script>alert(1)</script>\r\nBcc: evil@example.test'
URL = re.compile(r'https?://[^\s"\'<>]+')


def realistic_contexts():
    """A plausible context for every email, with the links built the way the real senders build them."""
    link = app_url
    return {
        'download_ready': dict(studio='Herry Shop', gallery_title='Sari and Ravi', days=7,
                               download_url=link('/g/herry/sari/download/file/1#key=abc:def'),
                               gallery_url=link('/g/herry/sari')),
        'download_code': dict(studio='Herry Shop', gallery_title='Sari and Ravi', code='482913', minutes=10),
        'password_reset': dict(display_name='Ann', reset_url=link('/reset-password#token=tok-en_123'), minutes=30),
        'password_changed': dict(display_name='Ann', email='ann@example.test', when='14 Oct 2026, 18:05 (UTC+05:45)',
                                 via_reset=True, by_staff=False, forgot_url=link('/forgot-password')),
        'notify_download': dict(who='client@example.test', what='a photo', gallery_title='Sari and Ravi',
                                activity_url=link('/dashboard/galleries/sari/activities?tab=downloads'),
                                window_minutes=15),
        'notify_favorite': dict(who='client@example.test', gallery_title='Sari and Ravi',
                                activity_url=link('/dashboard/galleries/sari/activities?tab=favorites'),
                                window_minutes=15),
        'payment_received': dict(plan_name='Pro', amount='NPR 1,500', billing_url=link('/dashboard/billing')),
        'payment_approved': dict(plan_name='Pro', until='14 Nov 2026', billing_url=link('/dashboard/billing')),
        'payment_rejected': dict(plan_name='Pro', reason='The amount on the receipt is wrong',
                                 billing_url=link('/dashboard/billing')),
        'plan_expiring': dict(plan_name='Pro', end_date='14 Oct 2026', when='in 3 days',
                              billing_url=link('/dashboard/billing')),
        'plan_ended': dict(plan_name='Pro', end_date='14 Oct 2026', billing_url=link('/dashboard/billing')),
        'staff_payment_alert': dict(payment_id='0190aa', plan_name='Pro', amount='NPR 1,500',
                                    staff_url=link('/dashboard/staff/payments')),
        # 7.5-E account deletion
        'deletion_code': dict(code='482913', minutes=10),
        'deletion_requested': dict(display_name='Ann', email='ann@example.test', scheduled_date='21 Oct 2026', days=7,
                                   cancel_url=link('/cancel-deletion#token=tok-en_123')),
        'account_deleted': dict(email='ann@example.test'),
    }


# Which context keys carry text a user (or a client visitor) typed.
USER_TEXT_KEYS = ('display_name', 'studio', 'gallery_title', 'who', 'what', 'plan_name', 'reason')


@override_settings(FRONTEND_URL=APP)
class RenderTests(SimpleTestCase):
    def test_the_audit_is_complete_and_every_email_has_a_context(self):
        # the 10 emails found by the 7.5-D audit + payment received + the staff alert + the 3 account-deletion emails (7.5-E)
        self.assertEqual(set(EMAILS), {
            'download_ready', 'download_code', 'password_reset', 'password_changed', 'notify_download',
            'notify_favorite', 'payment_received', 'payment_approved', 'payment_rejected', 'plan_expiring',
            'plan_ended', 'staff_payment_alert',
            'deletion_code', 'deletion_requested', 'account_deleted',      # 7.5-E
        })
        self.assertEqual(set(realistic_contexts()), set(EMAILS))

    def test_each_email_renders_in_html_and_text_on_the_shared_base(self):
        for key, context in realistic_contexts().items():
            subject, text, html = render_email(key, context)
            with self.subTest(key):
                # one base: wordmark, the support address, a 600 px card, system fonts, dark mode, mobile rules
                self.assertIn('>Kyapture</div>', html)
                self.assertIn('mailto:support@kyapture.com', html)
                self.assertIn('max-width:600px', html)
                self.assertIn('-apple-system', html)
                self.assertIn('prefers-color-scheme: dark', html)
                self.assertIn('max-width: 620px', html)
                self.assertIn('name="color-scheme" content="light dark"', html)
                self.assertIn(f'<title>{subject}</title>', html)
                self.assertTrue(text.startswith('KYAPTURE\n'))
                self.assertIn('support@kyapture.com', text)
                self.assertNotIn('<', text)                                  # the text part holds no markup
                self.assertTrue(text.endswith('\n'))
                self.assertNotIn('\n\n\n', text)

    def test_every_template_extends_the_one_base_and_nothing_else_exists(self):
        for key in EMAILS:
            for ext, base in (('html', 'emails/base.html'), ('txt', 'emails/base.txt')):
                source = get_template(f'emails/{key}.{ext}').template.source
                with self.subTest(f'{key}.{ext}'):
                    self.assertTrue(source.lstrip().startswith(f'{{% extends "{base}" %}}'))
        folder = BACKEND / 'apps' / 'core' / 'templates' / 'emails'
        names = {p.name for p in folder.iterdir()}
        expected = {f'{key}.{ext}' for key in EMAILS for ext in ('html', 'txt')} | {'base.html', 'base.txt', '_button.html'}
        self.assertEqual(names, expected)
        # and no other app keeps an email template of its own any more
        self.assertEqual(list((BACKEND / 'apps').glob('*/templates/*/emails/*')), [])

    def test_no_code_path_builds_a_mail_outside_the_shared_module(self):
        banned = re.compile(r'\b(send_mail|send_mass_mail|mail_admins|mail_managers|EmailMessage|EmailMultiAlternatives)\s*\(')
        offenders = []
        for root in ('apps', 'config'):
            for path in (BACKEND / root).rglob('*.py'):
                parts = path.parts
                if 'tests' in parts or 'migrations' in parts or 'venv' in parts or path.name == 'emailing.py':
                    continue
                code = '\n'.join(line for line in path.read_text(encoding='utf-8').splitlines() if not line.lstrip().startswith('#'))
                if banned.search(code):
                    offenders.append(str(path.relative_to(BACKEND)))
        self.assertEqual(offenders, [])

    def test_subjects_are_fixed_plain_strings(self):
        subjects = [spec.subject for spec in EMAILS.values()]
        self.assertEqual(len(set(subjects)), len(subjects))
        for subject in subjects:
            self.assertRegex(subject, r'^[A-Za-z ]{8,70}$')                  # letters and spaces: no digit, brace, code
        # a context can never change a subject
        for key, context in realistic_contexts().items():
            hostile = {k: HOSTILE if k in USER_TEXT_KEYS else v for k, v in context.items()}
            self.assertEqual(render_email(key, hostile)[0], EMAILS[key].subject)
        # and send_email has no way to take one
        self.assertNotIn('subject', inspect.signature(send_email).parameters)
        self.assertNotIn('subject', inspect.signature(render_email).parameters)

    def test_user_text_is_escaped_in_html_and_folded_to_one_line_everywhere(self):
        for key, context in realistic_contexts().items():
            keys = [k for k in USER_TEXT_KEYS if k in context]
            if not keys:
                continue
            hostile = {k: HOSTILE if k in keys else v for k, v in context.items()}
            subject, text, html = render_email(key, hostile)
            with self.subTest(key):
                self.assertNotIn('<script>', html)
                self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt; Bcc: evil@example.test', html)
                self.assertNotIn('\r', html + text)
                self.assertNotIn('\nBcc:', html + text)                      # the CRLF became a space
                self.assertIn('alert(1)</script> Bcc: evil@example.test', text)   # text/plain: not escaped, one line

    def test_html_loads_nothing_remote_and_tracks_nothing(self):
        for key, context in realistic_contexts().items():
            _, _, html = render_email(key, context)
            with self.subTest(key):
                for needle in ('<img', '<script', '<link', '<iframe', '<video', '@import', 'url(', ' src=', 'background=',
                               '@font-face', 'googleapis', 'gstatic'):
                    self.assertNotIn(needle, html.lower())
                # every absolute URL is a link the reader clicks, to our own app or a mailto
                for url in re.findall(r'(?:href|src)="([^"]+)"', html):
                    self.assertTrue(url.startswith((APP, 'mailto:')), url)

    def test_every_link_is_built_from_frontend_url(self):
        for key, context in realistic_contexts().items():
            subject, text, html = render_email(key, context)
            with self.subTest(key):
                self.assertNotIn('localhost', html + text)
                for url in URL.findall(html + text):
                    self.assertTrue(url.startswith(APP), url)

    @override_settings(FRONTEND_URL='http://localhost:3000')
    def test_localhost_appears_only_when_frontend_url_says_so(self):
        _, text, html = render_email('plan_ended', dict(plan_name='Pro', end_date='1 Jan 2030', billing_url=app_url('/dashboard/billing')))
        self.assertIn('http://localhost:3000/dashboard/billing', html)
        self.assertIn('http://localhost:3000/dashboard/billing', text)
        self.assertTrue(all(u.startswith('http://localhost:3000/dashboard/') for u in URL.findall(html + text)))

    def test_app_url_refuses_a_frontend_url_that_is_not_absolute(self):
        for bad in ('', '/relative', 'localhost:3000', 'ftp://x.test', 'javascript:alert(1)'):
            with override_settings(FRONTEND_URL=bad):
                with self.assertRaises(ValueError, msg=bad):
                    app_url('/dashboard/billing')

    def test_the_password_reset_token_stays_in_the_fragment(self):
        link = reset_link('tok-en_123')
        self.assertEqual(link, f'{APP}/reset-password#token=tok-en_123')
        _, text, html = render_email('password_reset', realistic_contexts()['password_reset'])
        self.assertIn(f'{APP}/reset-password#token=tok-en_123', text)
        self.assertNotIn('?token', html + text)
        self.assertNotIn('token=', EMAILS['password_reset'].subject)

    def test_the_footer_links_the_notification_settings_only_where_a_preference_applies(self):
        for key, context in realistic_contexts().items():
            _, text, html = render_email(key, context)
            has_link = f'{APP}/dashboard/settings/notifications' in html
            with self.subTest(key):
                self.assertEqual(has_link, EMAILS[key].preferences_link)
                self.assertEqual(has_link, f'{APP}/dashboard/settings/notifications' in text)
        self.assertEqual({k for k, s in EMAILS.items() if s.preferences_link}, {
            'notify_download', 'notify_favorite', 'payment_received', 'payment_approved', 'payment_rejected',
            'plan_expiring', 'plan_ended',
        })

    def test_no_email_is_marketing_and_none_mentions_a_grace_period(self):
        for key, context in realistic_contexts().items():
            _, text, html = render_email(key, context)
            for word in ('grace', 'unsubscribe', 'newsletter', 'discount', 'offer ', 'upgrade now'):
                self.assertNotIn(word, (text + html).lower(), f'{key}: {word}')

    def test_the_plan_expiring_and_plan_ended_copy(self):
        ctx = realistic_contexts()
        _, text, html = render_email('plan_expiring', ctx['plan_expiring'])
        self.assertIn('Your plan ends on 14 Oct 2026', text)
        self.assertIn('Your Pro plan ends on 14 Oct 2026 (in 3 days)', text)
        self.assertIn('Your plan ends on 14 Oct 2026</h1>', html)
        _, text, html = render_email('plan_ended', ctx['plan_ended'])
        for needle in ('Your plan has ended', 'Your Pro plan ended on 14 Oct 2026', 'now on the Free plan',
                       'files, galleries and settings are kept', 'Renewing restores the paid features'):
            self.assertIn(needle, text)
            self.assertIn(needle.replace("'", '&#x27;'), html)

    def test_dates_are_shown_in_the_billing_zone(self):
        late = datetime(2040, 10, 10, 20, 30, tzinfo=dt_timezone.utc)            # 02:15 on Oct 11 in Kathmandu
        self.assertEqual(emailing.format_date(late), '11 Oct 2040')
        self.assertEqual(emailing.format_datetime(late), '11 Oct 2040, 02:15 (UTC+05:45)')
        with override_settings(BILLING_TIME_ZONE='UTC'):
            self.assertEqual(emailing.format_date(late), '10 Oct 2040')

    def test_clean_line_folds_every_kind_of_line_break(self):
        self.assertEqual(clean_line('a\r\nb\nc\rd\x00e f\tg'), 'a b c d e f g')


@override_settings(FRONTEND_URL=APP)
class SendTests(SimpleTestCase):
    def setUp(self):
        mail.outbox = []

    def test_the_message_has_both_parts_and_the_env_sender_and_reply_to(self):
        with override_settings(DEFAULT_FROM_EMAIL='Kyapture <hello@mail.example.test>', EMAIL_REPLY_TO='help@example.test'):
            send_email('payment_received', 'ann@example.test', realistic_contexts()['payment_received'])
        (message,) = mail.outbox
        self.assertEqual(message.subject, 'We received your payment')
        self.assertEqual(message.from_email, 'Kyapture <hello@mail.example.test>')
        self.assertEqual(message.reply_to, ['help@example.test'])
        self.assertEqual(message.to, ['ann@example.test'])
        ((html, mimetype),) = message.alternatives
        self.assertEqual(mimetype, 'text/html')
        self.assertIn('We received your payment of NPR 1,500', message.body)
        self.assertIn('We received your payment of NPR 1,500', html)

    def test_a_hostile_value_cannot_add_a_header(self):
        context = dict(realistic_contexts()['notify_download'], who=HOSTILE, gallery_title=HOSTILE)
        send_email('notify_download', 'owner@example.test', context)
        (message,) = mail.outbox
        raw = message.message()
        self.assertIsNone(raw['Bcc'])
        self.assertEqual(message.bcc, [])
        self.assertEqual(raw['Subject'], 'New download from one of your collections')
        self.assertNotIn('evil@example.test', ''.join(f'{k}: {v}' for k, v in raw.items()))

    def test_a_studio_name_cannot_break_the_from_header(self):
        with override_settings(DEFAULT_FROM_EMAIL='Kyapture <no-reply@kyapture.com>'):
            header = emailing.display_from('Evil"\r\nBcc: x@example.test')
        self.assertNotIn('\n', header)
        self.assertNotIn('\r', header)
        self.assertTrue(header.endswith('<no-reply@kyapture.com>'), header)

    def test_safe_send_returns_false_and_logs_no_trace_when_the_backend_fails(self):
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=SMTPException('smtp.secret-host down')):
            with self.assertLogs('apps.core.emailing', level='ERROR') as logs:
                self.assertFalse(safe_send_email('download_code', 'x@example.test', realistic_contexts()['download_code']))
        self.assertEqual(mail.outbox, [])
        for record in logs.records:
            self.assertIsNone(record.exc_info)
            self.assertNotIn('secret-host', record.getMessage())
            self.assertNotIn('x@example.test', record.getMessage())

    def test_send_email_raises_so_a_task_can_retry(self):
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=SMTPException('down')):
            with self.assertRaises(SMTPException):
                send_email('plan_ended', 'x@example.test', realistic_contexts()['plan_ended'])

    def test_an_unknown_email_key_is_refused(self):
        with self.assertRaises(KeyError):
            send_email('hello_there', 'x@example.test', {})
        self.assertEqual(mail.outbox, [])


# ─── the download code (a visitor, in the request) ───────────────────────────

@override_settings(FRONTEND_URL=APP)
class DownloadCodeTests(PaymentBase):
    def setUp(self):
        super().setUp()
        mail.outbox = []
        self.gallery = Gallery.objects.create(photographer=self.owner, title='Wedding <b>', slug='code-gallery',
                                              is_published=True, is_active=True)

    def test_the_code_is_in_the_body_never_in_the_subject(self):
        self.assertEqual(send_email_code(self.gallery, 'guest@example.test'), 'sent')
        (message,) = mail.outbox
        code = re.search(r'\b(\d{6})\b', message.body).group(1)
        self.assertEqual(message.subject, 'Your Kyapture download code')
        self.assertNotIn(code, message.subject)
        self.assertIn(code, message.alternatives[0][0])
        self.assertIn('Wedding &lt;b&gt;', message.alternatives[0][0])           # the gallery title is escaped
        self.assertEqual(message.to, ['guest@example.test'])

    def test_a_failed_send_is_reported_and_leaves_no_usable_code(self):
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=SMTPException('down')):
            self.assertEqual(send_email_code(self.gallery, 'guest@example.test'), 'failed')
        self.assertIsNone(cache.get(_email_code_key(self.gallery, 'guest@example.test')))
        self.assertEqual(mail.outbox, [])


# ─── payments: received, approved, rejected, and the staff alert ────────────

@override_settings(FRONTEND_URL=APP, STAFF_ALERT_EMAIL='alerts@example.test', SUPPORT_EMAIL='help@example.test')
class PaymentEmailTests(PaymentBase):
    def setUp(self):
        super().setUp()
        mail.outbox = []
        patcher = mock.patch('apps.users.tasks.send_staff_alert_email.delay',
                             side_effect=lambda *args: deliver_staff_alert(*args))
        patcher.start()
        self.addCleanup(patcher.stop)

    def submit_committed(self, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            return self.submit(**kwargs)

    def test_the_payer_gets_payment_received_on_the_base(self):
        response = self.submit_committed(reference='TX-RCV-1')
        self.assertEqual(response.status_code, 201, response.data)
        (message,) = mails_to(self.owner)
        self.assertEqual(message.subject, 'We received your payment')
        self.assertIn(f'{self.pro.name} plan', message.body)
        self.assertIn(f'{APP}/dashboard/billing', message.body)
        self.assertIn('help@example.test', message.alternatives[0][0])           # the support address from the env
        self.assertNotIn('TX-RCV-1', message.body)                              # the reference stays out of the mail

    def test_payment_received_follows_the_payments_preference(self):
        self.owner.notify_payments = False
        self.owner.save(update_fields=['notify_payments'])
        self.assertEqual(self.submit_committed(reference='TX-RCV-2').status_code, 201)
        self.assertEqual(mails_to(self.owner), [])

    def test_one_staff_alert_goes_to_the_one_env_address_with_nothing_private(self):
        response = self.submit_committed(reference='ALERT-REF-77', notes='my private note about the bank')
        self.assertEqual(response.status_code, 201, response.data)
        payment = ManualPayment.objects.get()
        (alert,) = [m for m in mail.outbox if m.to == ['alerts@example.test']]
        self.assertEqual(alert.subject, 'New payment to review')
        html = alert.alternatives[0][0]
        for body in (alert.body, html):
            self.assertIn(str(payment.pk), body)
            self.assertIn(self.pro.name, body)
            self.assertIn(f'{payment.currency} {payment.amount:,.0f}', body)
            self.assertIn(f'{APP}/dashboard/staff/payments', body)
            for private in ('ALERT-REF-77', 'my private note', self.owner.email, self.owner.username, '/proof', '/api/', '/media/'):
                self.assertNotIn(private, body)
        self.assertEqual(alert.reply_to, ['help@example.test'])

    def test_no_staff_alert_when_the_env_address_is_empty_the_bell_still_works(self):
        with override_settings(STAFF_ALERT_EMAIL=''):
            self.assertEqual(self.submit_committed(reference='TX-RCV-3').status_code, 201)
        self.assertEqual([m for m in mail.outbox if m.subject == 'New payment to review'], [])
        from apps.users.models import Notification
        self.assertEqual(Notification.objects.filter(user=self.staff, kind='payment_review').count(), 1)

    def test_the_staff_alert_is_not_held_back_by_the_payers_preference(self):
        self.owner.notify_payments = False
        self.owner.save(update_fields=['notify_payments'])
        self.submit_committed(reference='TX-RCV-4')
        self.assertEqual(len([m for m in mail.outbox if m.to == ['alerts@example.test']]), 1)

    def test_a_rolled_back_submit_sends_nothing(self):
        self.submit_committed(reference='SAME-REF-1')
        mail.outbox = []
        again = self.submit_committed(reference='SAME-REF-1', user=self.other)     # refused: the reference is taken
        self.assertEqual(again.status_code, 400)
        self.assertEqual(mail.outbox, [])

    def test_a_broker_or_mail_failure_never_fails_the_submit(self):
        with mock.patch('apps.users.tasks.send_staff_alert_email.delay', side_effect=OSError('broker down')), \
                mock.patch('apps.users.tasks.send_notification_email.delay', side_effect=OSError('broker down')):
            response = self.submit_committed(reference='TX-BROKER-1')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ManualPayment.objects.count(), 1)
        with mock.patch('apps.users.notifications.send_email', side_effect=SMTPException('down')):
            response = self.submit_committed(reference='TX-SMTP-1', user=self.other)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ManualPayment.objects.count(), 2)

    def test_a_bad_frontend_url_never_fails_the_submit_or_the_review(self):
        with override_settings(FRONTEND_URL='not-a-url'):
            response = self.submit_committed(reference='TX-URL-1')
            self.assertEqual(response.status_code, 201)
            payment = ManualPayment.objects.get()
            self.assertEqual(self.approve(payment).status_code, 200)
        self.assertEqual(mail.outbox, [])

    def test_approved_and_rejected_use_fixed_subjects_and_the_billing_zone_date(self):
        payment = self.make_payment(reference='TX-APP-1')
        self.assertEqual(self.approve(payment).status_code, 200)
        (approved,) = mails_to(self.owner)
        self.assertEqual(approved.subject, 'Your payment was approved')
        payment.refresh_from_db()
        self.assertIn(f'It runs until {emailing.format_date(payment.period_end)}.', approved.body)
        mail.outbox = []
        other = self.make_payment(user=self.other, reference='TX-REJ-1')
        self.assertEqual(self.reject(other, reason='Receipt\r\nBcc: evil@example.test <b>').status_code, 200)
        (rejected,) = mails_to(self.other)
        self.assertEqual(rejected.subject, 'Your payment could not be approved')
        self.assertIn('Reason: Receipt Bcc: evil@example.test <b>', rejected.body)
        self.assertIn('Receipt Bcc: evil@example.test &lt;b&gt;', rejected.alternatives[0][0])
        self.assertIsNone(rejected.message()['Bcc'])

    def test_the_task_wrappers_never_raise_to_the_caller_when_the_mail_fails(self):
        with mock.patch('apps.users.notifications.send_email', side_effect=SMTPException('down')):
            result = user_tasks.send_notification_email.apply(
                args=(str(self.owner.pk), 'payments', 'payment_received', {'plan_name': 'Pro', 'amount': 'NPR 1', 'billing_url': APP}),
                throw=False)
            self.assertFalse(result.successful())
            alert = user_tasks.send_staff_alert_email.apply(args=('staff_payment_alert', {'plan_name': 'Pro'}), throw=False)
            self.assertFalse(alert.successful())
        self.assertEqual(mail.outbox, [])

    def test_an_unknown_template_in_a_queued_task_is_dropped_not_retried(self):
        self.assertFalse(deliver_notification(str(self.owner.pk), 'payments', 'Old subject line', 'Old body'))
        self.assertFalse(deliver_staff_alert('Old subject line', {}))
        self.assertEqual(mail.outbox, [])


# ─── a photographer's activity alerts ───────────────────────────────────────

@override_settings(FRONTEND_URL=APP)
class ActivityEmailTests(PaymentBase):
    def setUp(self):
        super().setUp()
        mail.outbox = []
        cache.clear()
        self.owner.notify_downloads = True
        self.owner.notify_favorites = True
        self.owner.save(update_fields=['notify_downloads', 'notify_favorites'])
        self.gallery = Gallery.objects.create(photographer=self.owner, title='<script>x</script> Wedding\nBcc: a@b.test',
                                              slug='activity-gallery', is_published=True, is_active=True)

    def test_a_download_alert_has_a_fixed_subject_and_an_escaped_body(self):
        with self.captureOnCommitCallbacks(execute=True):
            DownloadLog.objects.create(gallery=self.gallery, email='<i>guest</i>@example.test', download_type='photo')
        (message,) = mails_to(self.owner)
        self.assertEqual(message.subject, 'New download from one of your collections')
        html = message.alternatives[0][0]
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;x&lt;/script&gt; Wedding Bcc: a@b.test', html)
        self.assertIn('&lt;i&gt;guest&lt;/i&gt;@example.test', html)
        self.assertIn(f'{APP}/dashboard/galleries/activity-gallery/activities?tab=downloads', message.body)
        self.assertIn(f'{APP}/dashboard/settings/notifications', message.body)
        self.assertIsNone(message.message()['Bcc'])


# ─── the lifecycle mails (7.5-C placeholders, closed here) ─────────────────

@override_settings(FRONTEND_URL=APP)
class LifecycleEmailTests(LifecycleBase):
    def test_the_reminder_says_the_plan_ends_on_the_kathmandu_date_before_the_end(self):
        end = datetime(2040, 10, 10, 20, 30, tzinfo=dt_timezone.utc)             # Oct 11, 02:15 in Kathmandu
        give_period(self.owner, end)
        self.run_job(npt(10, 9, 9))
        (message,) = mails_to(self.owner)
        self.assertEqual(message.subject, 'Your Kyapture plan is ending soon')
        for body in (message.body, message.alternatives[0][0]):
            self.assertIn('Your plan ends on 11 Oct 2040', body)
            self.assertIn('Your Pro plan ends on 11 Oct 2040 (in 2 days)', body)
            self.assertIn(f'{APP}/dashboard/billing', body)
            self.assertNotIn('grace', body.lower())
        self.assertIn(f'{APP}/dashboard/settings/notifications', message.body)

    def test_the_downgrade_mail_says_the_plan_has_ended_and_files_are_kept(self):
        give_period(self.owner, END)
        self.run_job(npt(10, 15, 9))
        (message,) = mails_to(self.owner)
        self.assertEqual(message.subject, 'Your Kyapture plan has ended')
        for body in (message.body, message.alternatives[0][0]):
            self.assertIn('Your plan has ended', body)
            self.assertIn('Your Pro plan ended on 10 Oct 2040', body)
            self.assertIn('Free plan', body)
            self.assertIn('files, galleries and settings are kept', body)
            self.assertIn('Renewing restores the paid features', body)
            self.assertNotIn('grace', body.lower())
        self.assertIn(f'{APP}/dashboard/billing', message.body)

    def test_a_failing_send_still_downgrades_and_is_retried_by_the_next_run(self):
        give_period(self.owner, END)
        with mock.patch('apps.subscriptions.lifecycle.send_email', side_effect=SMTPException('down')):
            self.run_job(npt(10, 15, 9))
        self.assertEqual(self.sub().status, 'expired')
        self.assertEqual(mails_to(self.owner), [])
        self.run_job(npt(10, 16, 9))
        self.assertEqual(len(mails_to(self.owner)), 1)

    def test_a_bad_frontend_url_does_not_stop_the_daily_job(self):
        give_period(self.owner, END)
        with override_settings(FRONTEND_URL='not-a-url'):
            report = self.run_job(npt(10, 15, 9))
        self.assertEqual(self.sub().status, 'expired')
        self.assertEqual(len(report['downgrades']), 1)
        self.assertEqual(mails_to(self.owner), [])
