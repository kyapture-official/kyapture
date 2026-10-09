# 7.5-D QA cleanup: deletes ONLY the exact ids written by qa_trigger.py, after printing them.
# Run:  docker exec -i kyapture-backend-1 python manage.py shell < docs/qa-7-5d/qa_cleanup.py
# (The staff audit rows the QA actions wrote cannot be deleted: append-only trigger; never touched.)
import json
import os

from django.core.files.storage import default_storage

from apps.clients.models import DownloadJob
from apps.galleries.models import Gallery
from apps.subscriptions.models import ManualPayment
from apps.users.models import User

ids = json.load(open('/tmp/qa75d_ids.json'))
users = User.objects.filter(pk__in=ids['users'])
print('tag', ids['tag'])
print('users to delete   ', sorted(users.values_list('email', flat=True)), 'expected', len(ids['users']), 'found', users.count())
galleries = Gallery.objects.filter(pk__in=ids['galleries'])
print('galleries         ', list(galleries.values_list('slug', flat=True)), 'found', galleries.count())
payments = ManualPayment.objects.filter(pk__in=ids['payments'])
print('payments          ', payments.count(), 'expected', len(ids['payments']))
jobs = DownloadJob.objects.filter(pk__in=ids['jobs'])
print('jobs              ', jobs.count(), 'expected', len(ids['jobs']))
for e in users.values_list('email', flat=True):
    assert e.startswith(ids['tag'] + '-'), e
assert users.count() == len(ids['users'])
assert galleries.count() == len(ids['galleries'])
for name in ids['proofs']:
    try:
        default_storage.delete(name)
    except Exception as exc:
        print('proof file not removed', name, type(exc).__name__)
print('deleted', users.delete())
print('remaining by exact id', User.objects.filter(pk__in=ids['users']).count())
os.remove('/tmp/qa75d_ids.json')
