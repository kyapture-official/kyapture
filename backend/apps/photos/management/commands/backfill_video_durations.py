# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/management/commands/backfill_video_durations.py
import os
import subprocess
import tempfile

from django.core.management.base import BaseCommand

from apps.core.utils import _ffprobe_duration
from apps.photos.models import MediaAsset


class Command(BaseCommand):
    """
    Stores the duration (whole seconds) on video rows that have none, so the
    plan's video-minutes allowance counts them. Dry-run by default; pass
    --apply to write. Safe to re-run: rows that already have a duration are skipped.
    Run via: python manage.py backfill_video_durations [--apply]
    """
    help = 'Measure and store duration for videos missing it (dry-run unless --apply).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write the durations (default is a dry run).')

    def handle(self, *args, apply=False, **options):
        videos = MediaAsset.objects.filter(media_type=MediaAsset.MediaType.VIDEO, duration__isnull=True)
        found = measured = failed = 0
        for asset in videos.iterator():
            found += 1
            seconds = self._measure(asset)
            if seconds is None:
                failed += 1
                self.stderr.write(f'{asset.id}: could not measure {asset.original_name!r}')
                continue
            measured += 1
            self.stdout.write(f'{asset.id}: {asset.original_name!r} -> {seconds}s')
            if apply:
                MediaAsset.objects.filter(pk=asset.pk).update(duration=seconds)
        verb = 'Updated' if apply else 'Would update'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} {measured} of {found} videos without a duration ({failed} unreadable).'
            + ('' if apply else ' Dry run - re-run with --apply to write.')
        ))

    @staticmethod
    def _measure(asset):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(asset.original_name)[1] or '.mp4') as tmp:
                temp_path = tmp.name
                asset.original_file.open('rb')
                for chunk in asset.original_file.chunks():
                    tmp.write(chunk)
            return round(_ffprobe_duration(temp_path))
        except (subprocess.SubprocessError, ValueError, OSError):
            return None
        finally:
            try:
                asset.original_file.close()
            except Exception:
                pass
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
