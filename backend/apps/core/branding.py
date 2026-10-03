# C:/Users/LENOVO/Desktop/kyapture/backend/apps/core/branding.py
"""
Safe handling of the photographer's branding logo upload.

The logo is shown to every visitor of the photographer's galleries and is
reused as an image watermark, so an upload is treated as untrusted input:
validated by what Pillow can actually decode (not by extension or the
client-sent content type), capped in bytes and pixels, and RE-ENCODED so the
stored file is a clean image of a known format — no EXIF/GPS metadata, no
trailing/polyglot payload, no SVG/script content.
"""
import io
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps

LOGO_MAX_BYTES = 2 * 1024 * 1024          # matches the limit the settings UI advertises
LOGO_MAX_DIMENSION = 4096                 # px, longest edge
LOGO_MIN_DIMENSION = 16                   # px, shortest edge — rejects 1x1 tracking pixels

# Pillow format -> (extension, content type). Animated/other formats are rejected.
_ALLOWED_FORMATS = {
    'PNG': ('.png', 'image/png'),
    'JPEG': ('.jpg', 'image/jpeg'),
    'WEBP': ('.webp', 'image/webp'),
}


class InvalidLogo(ValueError):
    """Raised with a user-presentable message when a logo upload is unacceptable."""


def sanitize_logo_upload(uploaded):
    """
    Validates `uploaded` and returns a re-encoded SimpleUploadedFile.
    Raises InvalidLogo (message safe to show the user) on any problem.
    """
    if uploaded.size > LOGO_MAX_BYTES:
        raise InvalidLogo('Logo file exceeds the 2MB size limit.')

    try:
        uploaded.seek(0)
        probe = Image.open(uploaded)
        source_format = (probe.format or '').upper()
        probe.verify()                       # structural check; invalidates `probe`
        uploaded.seek(0)
        img = Image.open(uploaded)
        img.load()                           # full decode: surfaces truncated/corrupt data
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise InvalidLogo('Upload a valid PNG, JPEG or WEBP image.')
    finally:
        uploaded.seek(0)

    if source_format not in _ALLOWED_FORMATS:
        raise InvalidLogo('Logo must be a PNG, JPEG or WEBP image.')
    if getattr(img, 'is_animated', False):
        raise InvalidLogo('Animated images are not supported for logos.')

    width, height = img.size
    if min(width, height) < LOGO_MIN_DIMENSION:
        raise InvalidLogo('Logo is too small. Use an image at least 16 pixels on each side.')
    if max(width, height) > LOGO_MAX_DIMENSION:
        raise InvalidLogo(f'Logo is too large. Maximum dimension is {LOGO_MAX_DIMENSION} pixels.')

    img = ImageOps.exif_transpose(img)
    extension, content_type = _ALLOWED_FORMATS[source_format]
    out = io.BytesIO()
    if source_format == 'JPEG':
        img.convert('RGB').save(out, format='JPEG', quality=92, optimize=True)
    elif source_format == 'PNG':
        img.convert('RGBA').save(out, format='PNG', optimize=True)
    else:
        img.convert('RGBA').save(out, format='WEBP', quality=92)

    return SimpleUploadedFile(f'logo{extension}', out.getvalue(), content_type=content_type)
