# 7.5-D QA: creates throwaway accounts and triggers every email through the real code paths in the Docker stack.
# Run:  docker exec -i kyapture-backend-1 python manage.py shell < docs/qa-7-5d/qa_trigger.py
# Mail is delivered to Mailpit (http://localhost:8025). Ids are written to /tmp/qa75d_ids.json for the exact-id cleanup
# (docs/qa-7-5d/qa_cleanup.py). Every address is unique to this run; nothing is matched by pattern.
import io
import json
import time
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.clients.download_access import send_email_code
from apps.clients.models import DownloadJob, DownloadLog, Favorite
from apps.clients.ready_email import deliver_ready_email
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.subscriptions import lifecycle
from apps.subscriptions.models import LifecycleSettings, ManualPayment, SubscriptionPlan, UserSubscription
from apps.users.models import User

tag = f'qa75d{int(time.time())}'
PW = 'Sturdy-Pass-8842!'
ids = {'tag': tag, 'users': [], 'galleries': [], 'jobs': [], 'payments': [], 'proofs': []}


def mk(name, **extra):
    user = User.objects.create_user(email=f'{tag}-{name}@example.test', password=PW, username=f'{tag}{name}', **extra)
    ids['users'].append(str(user.pk))
    return user


def api(user):
    client = APIClient(HTTP_HOST='localhost')
    client.force_authenticate(user=user)
    return client


def png():
    buf = io.BytesIO()
    Image.new('RGB', (60, 40), 'white').save(buf, 'PNG')
    return SimpleUploadedFile('receipt.png', buf.getvalue(), content_type='image/png')


owner = mk('owner', display_name='<b>Ann</b> Owner', notify_downloads=True, notify_favorites=True)
payer = mk('payer', display_name='Pat Payer')
payer2 = mk('payerb', display_name='Pia Payer')
staff = mk('staff', is_staff=True)
expiring = mk('expiring', display_name='Eve Expiring')
ended = mk('ended', display_name='Ed Ended')
pro = SubscriptionPlan.objects.get(key='pro')

# gallery with a hostile title, to show escaping in the real mail
gallery = Gallery.objects.create(photographer=owner, title='<i>QA</i> Wedding & Co', slug=f'{tag}-g', is_published=True, is_active=True)
ids['galleries'].append(str(gallery.pk))

# 1-2. password reset (real endpoint -> Celery worker) and password changed (change-password endpoint -> Celery worker)
print('reset', APIClient(HTTP_HOST='localhost').post('/api/v1/auth/password/reset/', {'email': payer.email}, format='json').status_code)
print('change', api(payer2).put('/api/v1/auth/change-password/',
      {'old_password': PW, 'new_password': 'Another-Pass-5531!', 'new_password2': 'Another-Pass-5531!'}, format='json').status_code)

# 3. payment received (payer) + staff alert (STAFF_ALERT_EMAIL), then approve; payer2 submits and is rejected
for who, ref in ((payer, f'{tag.upper()}-A'), (payer2, f'{tag.upper()}-B')):
    r = api(who).post('/api/v1/subscriptions/payments/', {
        'plan': str(pro.id), 'amount': str(pro.price), 'reference': ref, 'payment_proof': png(),
        'notes': 'PRIVATE-NOTE-SHOULD-NOT-BE-MAILED'}, format='multipart')
    print('submit', who.username, r.status_code)
for p in ManualPayment.objects.filter(user_id__in=[payer.pk, payer2.pk]):
    ids['payments'].append(str(p.pk))
    ids['proofs'].append(p.payment_proof.name)
pay_a = ManualPayment.objects.get(user=payer)
pay_b = ManualPayment.objects.get(user=payer2)
print('approve', api(staff).post(f'/api/v1/staff/payments/{pay_a.pk}/approve/', {}, format='json').status_code)
print('reject', api(staff).post(f'/api/v1/staff/payments/{pay_b.pk}/reject/',
      {'reason': 'The amount is wrong <b>x</b>\r\nBcc: evil@example.test'}, format='json').status_code)

# 4. plan expiring (ends in 2 days) and plan ended (ended 4 days ago): the lifecycle step functions, these accounts only
now = timezone.now()
cfg = LifecycleSettings.load()
tz = lifecycle.billing_tz()
for who, end in ((expiring, now + timedelta(days=2, hours=3)), (ended, now - timedelta(days=cfg.grace_days + 1, hours=3))):
    sub = UserSubscription.objects.create(user=who, plan=pro, status='active', payment_method='manual',
                                          starts_at=end - timedelta(days=30), expires_at=end)
    who.is_active_plan = True
    who.save(update_fields=['is_active_plan'])
print('reminder', lifecycle.process_reminder(UserSubscription.objects.get(user=expiring).pk, expiring.pk, now, cfg, tz))
print('downgrade', lifecycle.process_downgrade(UserSubscription.objects.get(user=ended).pk, ended.pk, now, cfg, tz))

# 5. activity alerts (signals -> queue -> Celery worker)
DownloadLog.objects.create(gallery=gallery, email='<u>guest</u>@example.test', download_type='photo')
asset = MediaAsset.objects.create(gallery=gallery, media_type='image', original_name='a.jpg', file_size=1,
                                  processing_status='ready', original_file=f'photographers/{tag}/a.jpg')
Favorite.objects.create(gallery=gallery, media_asset=asset, email='<u>fan</u>@example.test', client_key=f'{tag}-key')

# 6. download ready (client) and the emailed download code (client)
job = DownloadJob.objects.create(gallery=gallery, state='ready', email=f'{tag}-guest@example.test',
                                 expires_at=now + timedelta(days=7), files=[])
ids['jobs'].append(str(job.pk))
print('ready', deliver_ready_email(str(job.pk)))
print('code', send_email_code(gallery, f'{tag}-codeguest@example.test'))

json.dump(ids, open('/tmp/qa75d_ids.json', 'w'))
print('TAG', tag)
