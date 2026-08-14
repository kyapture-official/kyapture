from django.core.management.base import BaseCommand
from PIL import Image as PILImage
from PIL.ImageOps import exif_transpose
from apps.photos.models import MediaAsset


class Command(BaseCommand):
    help = "Backfills width/height on existing photos that predate the dimension fix."

    def handle(self, *args, **kwargs):
        assets = MediaAsset.objects.filter(
            media_type=MediaAsset.MediaType.IMAGE,
            width__isnull=True,
        )
        total = assets.count()
        self.stdout.write(f"Found {total} photo(s) missing dimensions.")

        fixed = 0
        for asset in assets:
            try:
                asset.original_file.open('rb')
                with PILImage.open(asset.original_file) as img:
                    img = exif_transpose(img)
                    width, height = img.size
                asset.width = width
                asset.height = height
                asset.save(update_fields=['width', 'height'])
                fixed += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Skipped {asset.id}: {e}"))
            finally:
                asset.original_file.close()

        self.stdout.write(self.style.SUCCESS(f"Backfilled {fixed}/{total} photo(s)."))