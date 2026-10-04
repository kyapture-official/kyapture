# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/web_size.py
"""
"Web Size" downloads at the EXACT size the photographer chose (2048 / 1024 / 640).

The stored web tiers are 2048/1280/640 WebP files, so serving one of them
for a 1024px choice would hand out a 1280px file under a 1024px label. Instead
the file is derived when a download is prepared:

  - from the un-watermarked source: the 3600px Download Master when there is
    one, else the preserved original (never modified, only read)
  - oriented, normalized to sRGB, long edge = the chosen px
    (Image.thumbnail never upscales: a smaller source is delivered as it is)
  - the gallery's CURRENT watermark applied when it has one, exactly like the
    web tiers (Original / the Download Master are never watermarked)
  - saved as a standard baseline JPEG with no EXIF / ICC / GPS

Returns None when the source cannot be decoded; callers then fall back to the
nearest stored tier rather than failing the download.
"""
import io
import logging

from PIL import Image, ImageOps

from apps.core.utils import _normalize_to_srgb
from apps.core.watermark import apply_watermark, build_watermark_spec

logger = logging.getLogger(__name__)

WEB_JPEG_QUALITY = 90


def _flatten_alpha(img):
    """JPEG has no alpha: composite transparent images over white, not black."""
    has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
    if not has_alpha:
        return img
    rgba = img.convert('RGBA')
    background = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, rgba).convert('RGB')


def derive_web_jpeg(asset, px, gallery=None):
    """JPEG bytes of `asset` with its long edge at most `px`, or None if it cannot be decoded."""
    for field in (asset.download_file, asset.original_file):
        if not field:
            continue
        try:
            field.open('rb')
            try:
                with Image.open(field) as opened:
                    img = ImageOps.exif_transpose(opened)
                    img.load()
            finally:
                field.close()
            img = _normalize_to_srgb(_flatten_alpha(img))
            img.thumbnail((px, px), Image.Resampling.LANCZOS)
            spec = build_watermark_spec(gallery) if gallery is not None else None
            if spec is not None:
                img = apply_watermark(img, spec)
            out = io.BytesIO()
            img.convert('RGB').save(
                out, format='JPEG', quality=WEB_JPEG_QUALITY, optimize=True, progressive=False,
            )
            return out.getvalue()
        except Exception as exc:
            logger.warning('Web Size derivation from %s failed for asset %s: %s', field.name, asset.id, exc)
    return None
