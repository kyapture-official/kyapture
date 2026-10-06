"""
Per-file upload limits (chunk UP-A): read from the admin-edited UploadLimits row
at request time, never from code. One home for the rules so the upload view, the
serializers, the Celery tasks and the usage API all agree.

An image is judged by its file size first (no file read at all), then by the
pixel count in its header: Pillow reads the dimensions when it opens a file
without decoding any pixel data, so a huge image is refused before it costs CPU
or memory.
"""
from PIL import Image as PILImage

from .models import UploadLimits

MB = 1024 * 1024

FILE_TOO_LARGE = 'file_too_large'
IMAGE_TOO_MANY_PIXELS = 'image_too_many_pixels'


class Limits:
    """A snapshot of the admin row, in the units the checks use."""

    def __init__(self, row):
        self.max_image_mb = row.max_image_mb
        self.max_image_pixels = row.max_image_pixels
        self.max_video_mb = row.max_video_mb
        self.max_image_bytes = row.max_image_mb * MB
        self.max_video_bytes = row.max_video_mb * MB

    def payload(self):
        """The figures the usage API hands the browser for its own pre-check."""
        return {
            'max_image_mb': self.max_image_mb,
            'max_image_pixels': self.max_image_pixels,
            'max_video_mb': self.max_video_mb,
        }


def get_upload_limits():
    """The current limits (one primary-key query)."""
    return Limits(UploadLimits.load())


def apply_pillow_pixel_guard(limits=None):
    """
    Make Pillow's decompression-bomb guard follow the setting: a file above
    max_image_pixels warns, above twice that Image.open raises DecompressionBombError.
    Call it where an upload is judged and at the start of a worker task that decodes.
    """
    limits = limits or get_upload_limits()
    PILImage.MAX_IMAGE_PIXELS = limits.max_image_pixels
    return limits


def file_too_large(name, size, kind, limits):
    """The refusal for a file over its size limit (kind: 'image' or 'video')."""
    limit_mb = limits.max_image_mb if kind == 'image' else limits.max_video_mb
    return {
        'error': f'Size exceeds {limit_mb} MB limit',
        'code': FILE_TOO_LARGE,
        'message': f'Size exceeds {limit_mb} MB limit',
        'file_name': name,
        'size_bytes': size,
        'limit_mb': limit_mb,
        'limit_bytes': limit_mb * MB,
        'media_type': kind,
    }


def image_too_many_pixels(name, limits, width=None, height=None):
    limit = limits.max_image_pixels
    refusal = {
        'error': f'Image exceeds the {limit:,} pixel limit',
        'code': IMAGE_TOO_MANY_PIXELS,
        'message': f'Image exceeds the {limit:,} pixel limit',
        'file_name': name,
        'limit_pixels': limit,
        'media_type': 'image',
    }
    if width and height:
        refusal.update({'width': width, 'height': height, 'pixels': width * height})
        refusal['message'] = refusal['error'] = f'Image is {width:,} x {height:,} px, above the {limit:,} pixel limit'
    return refusal


def check_size(file, kind, limits):
    """None when the file's size is within the limit (exactly at it is allowed), else the refusal."""
    cap = limits.max_image_bytes if kind == 'image' else limits.max_video_bytes
    return file_too_large(file.name, file.size, kind, limits) if file.size > cap else None


def check_image_pixels(file, limits):
    """
    None when the image's pixel count is within the limit, else the refusal.
    Only the header is read (PIL.Image.open is lazy; nothing is decoded). A file
    Pillow cannot identify is left to the normal validation, which answers 400.
    """
    apply_pillow_pixel_guard(limits)
    try:
        file.seek(0)
        with PILImage.open(file) as img:
            width, height = img.size
    except PILImage.DecompressionBombError:
        # Pillow's own guard fired (more than twice the limit): same answer.
        return image_too_many_pixels(file.name, limits)
    except Exception:
        return None
    finally:
        file.seek(0)
    if width * height > limits.max_image_pixels:
        return image_too_many_pixels(file.name, limits, width, height)
    return None
