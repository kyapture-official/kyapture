import os
import uuid

from django.core.management.base import BaseCommand
from PIL import Image

from apps.core.utils import DOWNLOAD_MAX_EDGE, process_download_master
from apps.photos.models import MediaAsset


class Command(BaseCommand):
    help = "Regenerates old download masters for READY image assets."

    def _download_dimensions(self, asset):
        with asset.download_file.open("rb") as download_file:
            with Image.open(download_file) as image:
                return image.size

    def _is_eligible(self, asset):
        if not asset.original_file or not asset.download_file:
            return False
        try:
            return max(self._download_dimensions(asset)) > DOWNLOAD_MAX_EDGE
        except Exception as exc:
            raise ValueError(f"could not inspect existing download master: {exc}") from exc

    def _replace_download_file(self, asset, replacement):
        old_name = asset.download_file.name if asset.download_file else None
        storage = asset.download_file.storage
        directory = os.path.dirname(old_name) if old_name else ""
        temporary_name = os.path.join(
            directory,
            f".backfill-{asset.id}-{uuid.uuid4().hex}.tmp{os.path.splitext(replacement.name)[1]}",
        ).replace("\\", "/")

        temporary_name = storage.save(temporary_name, replacement)
        try:
            asset.download_file.name = temporary_name
            asset.save(update_fields=["download_file"])
        except Exception:
            storage.delete(temporary_name)
            raise

        if old_name and old_name != temporary_name:
            storage.delete(old_name)

    def handle(self, *args, **options):
        assets = MediaAsset.objects.filter(
            processing_status=MediaAsset.ProcessingStatus.READY,
            media_type=MediaAsset.MediaType.IMAGE,
        ).order_by("created_at", "id")

        eligible = []
        skipped = 0
        classification_failures = 0
        for asset in assets:
            try:
                if self._is_eligible(asset):
                    eligible.append(asset)
                else:
                    skipped += 1
            except Exception as exc:
                classification_failures += 1
                self.stdout.write(self.style.ERROR(f"Failed to inspect {asset.id}: {exc}"))

        self.stdout.write(f"Eligible READY image assets: {len(eligible)}")

        regenerated = 0
        fallback = 0
        failed = classification_failures
        for asset in eligible:
            try:
                replacement = process_download_master(asset.original_file)

                # Eligible assets have a master above the 3600 px cap, so their
                # original is above it too: a capped master is kept even when it
                # is larger than the original (serving that original to a Free
                # client would leak the resolution the cap promises).
                if replacement is None:
                    old_name = asset.download_file.name
                    storage = asset.download_file.storage
                    asset.download_file = None
                    asset.save(update_fields=["download_file"])
                    if old_name:
                        storage.delete(old_name)
                    fallback += 1
                    continue

                replacement.seek(0)
                with Image.open(replacement) as image:
                    if max(image.size) > DOWNLOAD_MAX_EDGE:
                        raise ValueError(
                            f"replacement exceeds {DOWNLOAD_MAX_EDGE}px long edge: {image.size}"
                        )
                replacement.seek(0)
                self._replace_download_file(asset, replacement)
                regenerated += 1
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"Failed {asset.id}: {exc}"))

        remaining_old = 0
        for asset in MediaAsset.objects.filter(
            processing_status=MediaAsset.ProcessingStatus.READY,
            media_type=MediaAsset.MediaType.IMAGE,
        ).exclude(original_file="").exclude(download_file=""):
            try:
                if self._is_eligible(asset):
                    remaining_old += 1
            except Exception:
                remaining_old += 1

        self.stdout.write(f"Total eligible: {len(eligible)}")
        self.stdout.write(f"Regenerated successfully: {regenerated}")
        self.stdout.write(f"Skipped: {skipped}")
        self.stdout.write(f"Fallback-to-original: {fallback}")
        self.stdout.write(f"Failed: {failed}")
        self.stdout.write(f"Remaining old artifacts: {remaining_old}")