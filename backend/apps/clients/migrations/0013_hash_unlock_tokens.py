"""
7-B (SEC-14 / debt row 89): unlock tokens are stored as their SHA-256, never in
plaintext. Existing rows still hold the token itself, so each is replaced by its
hash; the browsers that hold those tokens keep working (the lookup hashes what
they send). Favorite lists and favorites made on a protected gallery without a
client_uid were keyed by the plaintext token: they move to the same hash.

Not reversible: a hash cannot be turned back into the token (reversing leaves the
hashes in place, which only logs those visitors out of protected galleries).
"""
import hashlib

from django.db import migrations


def _hash(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def hash_existing_tokens(apps, schema_editor):
    ClientSession = apps.get_model('clients', 'ClientSession')
    FavoriteList = apps.get_model('clients', 'FavoriteList')
    Favorite = apps.get_model('clients', 'Favorite')
    for session in ClientSession.objects.all().only('pk', 'gallery_id', 'access_token').iterator():
        raw = session.access_token
        hashed = _hash(raw)
        ClientSession.objects.filter(pk=session.pk).update(access_token=hashed)
        FavoriteList.objects.filter(gallery_id=session.gallery_id, client_key=raw).update(client_key=hashed)
        Favorite.objects.filter(gallery_id=session.gallery_id, client_key=raw).update(client_key=hashed)


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0012_download_job_variant'),
    ]

    operations = [
        migrations.RunPython(hash_existing_tokens, migrations.RunPython.noop),
    ]
