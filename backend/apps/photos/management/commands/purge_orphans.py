# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/management/commands/purge_orphans.py
"""
Find storage objects that no database row refers to - what a permanently failed
purge task, a crashed upload or a manual DB cleanup can leave behind.

    manage.py purge_orphans                      # DRY RUN (the default): list only
    manage.py purge_orphans --dry-run            # same, explicit
    manage.py purge_orphans --delete             # actually delete what was listed

Scope is the collection tree (`photographers/<id>/galleries/...`) and prepared
download ZIPs (`download_jobs/...`) - never avatars, logos or payment proofs.
Objects younger than --min-age-minutes (default 60) are skipped, so a file that
an upload or a processing task has written but not yet recorded is never touched.
Nothing is deleted unless --delete is given.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.clients.models import DownloadJob
from apps.core.storage import PrivateMediaStorage, PublicMediaStorage
from apps.photos.models import MediaAsset
from apps.photos.purge import ASSET_FILE_FIELDS

SCAN_ROOTS = ('photographers/', 'download_jobs/')


def referenced_names():
    """Every storage key a database row still owns."""
    names = set()
    for field in ASSET_FILE_FIELDS:
        names.update(
            name for name in MediaAsset.objects.exclude(**{field: ''}).exclude(**{f'{field}__isnull': True})
            .values_list(field, flat=True) if name
        )
    for files in DownloadJob.objects.values_list('files', flat=True):
        names.update(entry['storage_path'] for entry in (files or []) if entry.get('storage_path'))
    return names


def walk(storage, prefix):
    """Yield every object key under `prefix`."""
    try:
        directories, files = storage.listdir(prefix)
    except (FileNotFoundError, NotADirectoryError):
        return
    for name in files:
        yield f'{prefix}{name}'
    for directory in directories:
        yield from walk(storage, f'{prefix}{directory}/')


def in_scope(key):
    if key.startswith('download_jobs/'):
        return True
    parts = key.split('/')
    return len(parts) > 3 and parts[0] == 'photographers' and parts[2] == 'galleries'


class Command(BaseCommand):
    help = "List (and with --delete, remove) storage objects that no database row refers to."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='List only (this is the default).')
        parser.add_argument('--delete', action='store_true', help='Actually delete the orphans that are listed.')
        parser.add_argument('--min-age-minutes', type=int, default=60,
                            help='Skip objects modified more recently than this (default 60).')

    def handle(self, *args, **options):
        if options['dry_run'] and options['delete']:
            self.stderr.write('Choose either --dry-run or --delete, not both.')
            return
        delete = options['delete']
        cutoff = timezone.now() - timedelta(minutes=options['min_age_minutes'])
        referenced = referenced_names()

        found = []          # (kind, storage, key, size)
        seen = set()
        for kind, storage in (('private', PrivateMediaStorage()), ('public', PublicMediaStorage())):
            for root in SCAN_ROOTS:
                for key in walk(storage, root):
                    if key in seen or not in_scope(key) or key in referenced:
                        continue
                    try:
                        modified = storage.get_modified_time(key)
                        if timezone.is_naive(modified):
                            modified = timezone.make_aware(modified)
                        if modified > cutoff:
                            continue
                        size = storage.size(key)
                    except Exception:
                        continue
                    seen.add(key)
                    found.append((kind, storage, key, size))

        for kind, _, key, size in found:
            self.stdout.write(f'{"DELETE" if delete else "ORPHAN"}  [{kind}] {key}  ({size} bytes)')

        total = sum(size for *_, size in found)
        if not delete:
            self.stdout.write(self.style.WARNING(
                f'{len(found)} orphaned object(s), {total} bytes. DRY RUN - nothing was deleted. '
                f'Re-run with --delete to remove them.'
            ))
            return

        removed = 0
        for kind, storage, key, _ in found:
            try:
                storage.delete(key)
                removed += 1
            except Exception as exc:
                self.stderr.write(f'could not delete {key}: {exc}')
        self.stdout.write(self.style.SUCCESS(f'Deleted {removed} of {len(found)} orphaned object(s), {total} bytes.'))
