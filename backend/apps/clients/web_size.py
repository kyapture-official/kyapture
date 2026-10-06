# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/web_size.py
"""
"Web Size" downloads at the EXACT size the photographer chose (2048 / 1024 / 640).

The stored web tiers are 2048/1280/640 WebP files, so serving one of them
for a 1024px choice would hand out a 1280px file under a 1024px label. Instead
the file is derived once and cached:

  - from the un-watermarked source: the 3600px Download Master when there is
    one, else the preserved original (never modified, only read)
  - oriented, normalized to sRGB, long edge = the chosen px
    (Image.thumbnail never upscales: a smaller source is delivered as it is)
  - the gallery's CURRENT watermark applied when it has one, exactly like the
    web tiers (Original / the Download Master are never watermarked)
  - saved as a standard baseline JPEG, Pillow quality 90, no EXIF / ICC / GPS
    (jpegli was measured against this baseline in chunk 6-C and rejected: see
    docs/KYAPTURE_COMPRESSION_CALIBRATION.md section 6)

Cache: one private-storage object per (photo, px, watermark state, source),
    photographers/<id>/galleries/<id>/web_size/<asset id>/<px>-<wm>-<src>.jpg
  - <wm> is the watermark signature, or "clean" for no watermark, so turning a
    watermark on/off or editing it selects a different object
  - <src> fingerprints the file it was derived from (Download Master or
    original: name + byte size) and the encoder settings, so a re-encoded master never serves a
    stale size
  - the second request for the same key is a storage read: no decode, no encode
  - older keys of the same (photo, px) are removed when a new one is written;
    the whole directory goes when the photo / set / collection is purged
    (apps/photos/purge.py)
  - encoding never runs in a request thread: single downloads ask the
    `generate_web_size` Celery task (own queue, bounded concurrency), a ZIP job
    is already a Celery task and encodes inline

Returns None when the source cannot be decoded; callers then fall back to the
nearest stored tier rather than failing the download.
"""
import hashlib
import io
import logging

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from apps.core.storage import PrivateMediaStorage
from apps.core.utils import _normalize_to_srgb
from apps.core.watermark import apply_watermark, build_watermark_spec
from apps.photos.purge import web_size_prefix

logger = logging.getLogger(__name__)

WEB_JPEG_QUALITY = 90
WEB_PX_CHOICES = (2048, 1024, 640)
CACHE_VERSION = 'v1'      # bump when the encoder settings change: old cached sizes stop matching
CLEAN = 'clean'           # watermark state of an un-watermarked size


def _flatten_alpha(img):
    """JPEG has no alpha: composite transparent images over white, not black."""
    has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
    if not has_alpha:
        return img
    rgba = img.convert('RGBA')
    background = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, rgba).convert('RGB')


def render_web_jpeg(asset, px, spec=None):
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


def derive_web_jpeg(asset, px, gallery=None):
    """Uncached render with the gallery's current watermark (kept for callers that want raw bytes)."""
    return render_web_jpeg(asset, px, build_watermark_spec(gallery) if gallery is not None else None)


# ─── the cache ───────────────────────────────────────────────────────────────

def watermark_state(spec):
    return spec.signature if spec is not None else CLEAN


def cache_key(asset, px, spec):
    """Storage key of this photo's `px` Web Size in this watermark state, or None (non-standard original path)."""
    prefix = web_size_prefix(asset)
    if prefix is None:
        return None
    field = asset.download_file or asset.original_file
    try:
        size = field.size       # a master re-encoded in place keeps its name, so its size is part of the fingerprint
    except Exception:
        size = 0
    fingerprint = hashlib.sha256(f'{field.name}|{size}|q{WEB_JPEG_QUALITY}|{CACHE_VERSION}'.encode()).hexdigest()[:10]
    return f'{prefix}{int(px)}-{watermark_state(spec)}-{fingerprint}.jpg'


def cached_exists(key):
    try:
        return bool(key) and PrivateMediaStorage().exists(key)
    except Exception:
        logger.warning('Web Size cache lookup failed for %s', key)
        return False


def open_cached(key):
    return PrivateMediaStorage().open(key, 'rb')


def read_cached(key):
    handle = open_cached(key)
    try:
        return handle.read()
    finally:
        handle.close()


def _drop_other_sizes(storage, key):
    """Removes this photo's superseded cache entries for the same px (older watermark / source)."""
    prefix, _, name = key.rpartition('/')
    px_part = name.split('-', 1)[0] + '-'
    try:
        _, files = storage.listdir(prefix + '/')
    except (FileNotFoundError, NotADirectoryError):
        return
    for other in files:
        if other != name and other.startswith(px_part):
            try:
                storage.delete(f'{prefix}/{other}')
            except Exception:
                logger.warning('Could not delete superseded Web Size %s/%s', prefix, other)


def build_cached(asset, px, spec):
    """
    Encodes and stores `asset`'s `px` Web Size unless it is already cached.
    Returns the storage key, or None if the source cannot be decoded / stored.
    Callers must be Celery tasks (never a request thread).
    """
    key = cache_key(asset, px, spec)
    if key is None:
        return None
    if cached_exists(key):
        return key
    data = render_web_jpeg(asset, px, spec)
    if data is None:
        return None
    storage = PrivateMediaStorage()
    try:
        if not storage.exists(key):          # another worker may have won the race
            storage.save(key, ContentFile(data))
        _drop_other_sizes(storage, key)
    except Exception:
        logger.exception('Web Size %s could not be stored', key)
        return None
    return key


def request_cached(asset, px, spec, wait=None):
    """
    Request-thread entry: the storage key of the cached size, asking the
    `generate_web_size` Celery task (and waiting up to `wait` seconds) on a
    miss. Returns the key, or None when the source is undecodable. Raises
    WebSizeNotReady when the worker could not deliver in time.
    """
    key = cache_key(asset, px, spec)
    if key is None:
        return None
    if cached_exists(key):
        return key
    from .tasks import generate_web_size

    wait = settings.WEB_SIZE_WAIT_SECONDS if wait is None else wait
    try:
        result = generate_web_size.apply_async(args=[str(asset.id), int(px), watermark_state(spec)])
        built = result.get(timeout=wait, propagate=True, disable_sync_subtasks=False)
    except Exception as exc:
        logger.warning('Web Size %s was not ready (%s)', key, exc.__class__.__name__)
        raise WebSizeNotReady() from exc
    if built is None:
        return None                            # undecodable source
    if built != key or not cached_exists(key):
        raise WebSizeNotReady()                # e.g. the watermark changed while it was encoding
    return key


class WebSizeNotReady(Exception):
    """The Celery worker did not deliver a cold Web Size in time (or could not be reached)."""
