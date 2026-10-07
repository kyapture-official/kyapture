# C:/Users/LENOVO/Desktop/kyapture/backend/apps/core/utils.py
import io
import logging
import piexif
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from decimal import Decimal

from PIL import Image, ImageDraw, ImageFont, ImageCms
from PIL.ImageOps import exif_transpose
from PIL import Image as PILImage

from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import Sum, Count, Q
from django.core.files.uploadedfile import SimpleUploadedFile, InMemoryUploadedFile

from rest_framework.exceptions import PermissionDenied, ValidationError
from apps.subscriptions.models import UserSubscription, SubscriptionPlan
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset

logger = logging.getLogger(__name__)


def generate_unique_slug(model_class, title, reserved_words=None, exclude_pk=None, **lookup_filters):
    """
    Generates a URL-safe slug, dynamically scoped to multi-tenant filters
    to prevent cross-photographer namespace collisions [1.2.7].

    reserved_words: optional iterable of slug values that must never be
    handed out directly, because they collide with a literal URL segment
    registered ahead of a '<slug:...>' pattern for this model (e.g.
    Gallery's 'search' collides with apps/galleries/urls.py's 'search/'
    route). Treated exactly like an existing DB row: the numeric-suffix
    loop below kicks in, so the title still gets a usable, similar slug
    (e.g. 'search-1') instead of one that's silently unreachable.

    exclude_pk: required when regenerating a slug for an EXISTING row
    (e.g. GalleryUpdateSerializer on a title edit). Without it, the
    row's own still-in-place slug counts as a "collision" against
    itself, incorrectly bumping a numeric suffix onto a title edit
    that didn't actually change the slugified form (whitespace,
    casing, etc). Not used on create() — there's no existing row yet.

    Example Usage:
        slug = generate_unique_slug(Gallery, "My Wedding", photographer=user)
    """
    base_slug = slugify(title)
    if not base_slug:
        base_slug = "untitled"

    reserved = set(reserved_words or ())

    slug = base_slug
    counter = 1

    queryset = model_class.objects.all()
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)

    # Scopes the database existence check strictly to the provided tenant filter [1.2.7]
    while slug in reserved or queryset.filter(slug=slug, **lookup_filters).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


def generate_secure_token(length=32):
    """
    Generates a cryptographically secure, high-entropy, URL-safe random token.
    Uses Python's secrets module (CSPRNG) [1.1.2].
    """
    return secrets.token_urlsafe(length)



def get_user_subscription_metrics(user):
    """
    Computes a single-pass evaluation of a photographer's active subscription tier 
    limits versus their actual real-time database usage.
    
    Dynamically imported inside the function to prevent circular dependency boots 
    with apps.subscriptions, apps.galleries, and apps.photos.
    """

    # 1. Limits come from the plan table only: the photographer's active plan,
    # else the Free-tier row (owner-editable in admin). NULL limits = unlimited.
    try:
        # Same rule as apps/subscriptions/entitlements.py::_active_plan: an
        # 'active' row whose expires_at has passed is a lapsed plan, even before
        # the 15-minute sweep flips its status (7-B, debt row 43).
        active_sub = UserSubscription.objects.select_related('plan').get(
            user=user,
            status='active',
            expires_at__gt=timezone.now(),
        )
        plan = active_sub.plan
    except UserSubscription.DoesNotExist:
        active_sub, plan = None, SubscriptionPlan.get_free()

    limits = {
        "active_subscription": active_sub,
        "plan_name": plan.name,
        "max_galleries": plan.max_collections,
        "storage_bytes_limit": plan.storage_gb * 1024 * 1024 * 1024,
        # Video allowance comes from the plan row: 0 = no video, None = unlimited,
        # N = N minutes (apps/subscriptions/entitlements.py::video_quota_violation).
        "video_minutes_limit": plan.video_minutes,
        "allow_video": plan.video_minutes != 0,
        "current_video_seconds": 0,
        "current_galleries_count": 0,
        "live_galleries_count": 0,
        "current_total_storage_bytes": 0,
    }

    # 2. Single-pass Aggregation for Current Usage
    #
    # Phase 4 (F-30 storage-leak fix): deliberately counts EVERY gallery
    # row that still exists for this user — active AND trashed
    # (is_active=False, pending purge) alike — not just is_active=True.
    # A soft-deleted gallery's files are still sitting in storage during
    # its retention window (see Gallery.trashed_at's docstring); if
    # quota stopped counting it the instant it was trashed, a user could
    # delete+reupload indefinitely at zero counted cost while real S3
    # usage grew unbounded, which is exactly the leak this fixes. Once
    # the scheduled purge task actually hard-deletes a gallery past its
    # retention window, its row (and its MediaAssets, cascade-deleted)
    # stops existing at all and naturally drops out of this count —
    # quota only frees up when the data is actually gone, not when it's
    # merely hidden.
    #
    # The plan's COLLECTION CAP is checked against `live_galleries_count`
    # instead: live (is_active) collections only, i.e. what the photographer
    # sees. Deleting a collection is permanent now, so a delete removes the row
    # and frees its slot at once; a legacy trashed row never blocks creation.
    gallery_counts = Gallery.objects.filter(photographer=user).aggregate(
        total=Count('id'),
        live=Count('id', filter=Q(is_active=True)),
    )
    limits["current_galleries_count"] = gallery_counts['total']
    limits["live_galleries_count"] = gallery_counts['live']

    # Same rationale as above — a trashed gallery's assets still occupy
    # real storage until the purge task actually deletes them.
    asset_aggregation = MediaAsset.objects.filter(
        gallery__photographer=user,
    ).aggregate(
        total_bytes=Sum('file_size'),
        total_count=Count('id'),
        # The dashboard also shows the count for ACTIVE (non-trashed)
        # galleries only; folding it into this aggregate saves a second scan.
        active_count=Count('id', filter=Q(gallery__is_active=True)),
        # Live video rows only (freed the moment a video row is deleted), same
        # scope as the storage total above.
        video_seconds=Sum('duration', filter=Q(media_type=MediaAsset.MediaType.VIDEO)),
    )

    # Postgres SUM() of a bigint column is numeric, which psycopg returns as Decimal;
    # DRF would render that as a JSON string, so hand back a plain int.
    limits["current_total_storage_bytes"] = int(asset_aggregation['total_bytes'] or 0)
    limits["current_video_seconds"] = asset_aggregation['video_seconds'] or 0
    limits["current_photos_count"] = asset_aggregation['total_count'] or 0
    limits["active_photos_count"] = asset_aggregation['active_count'] or 0
    return limits

# Magic Byte Signatures for strict JPEG and PNG security verification
_ALLOWED_SIGNATURES = [
    b'\xff\xd8\xff\xe0',  # JPEG JFIF
    b'\xff\xd8\xff\xe1',  # JPEG Exif
    b'\xff\xd8\xff\xe2',  # JPEG with ICC profile
    b'\xff\xd8\xff\xdb',  # JPEG raw tables
    b'\x89PNG\r\n\x1a\n', # PNG
]


def _ffprobe_duration(path):
    """Container duration in seconds (float) via ffprobe; raises on an unreadable file."""
    result = subprocess.run(
        [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
        timeout=60,
    )
    return float((result.stdout or "0").strip() or 0.0)


def probe_video_duration(uploaded_file):
    """
    Whole-second duration of an uploaded video, measured at upload time so
    the plan's video-minutes allowance can be enforced BEFORE anything is
    stored. Large uploads arrive as temp files on disk, so ffprobe reads the
    existing path where there is one; otherwise the (small, in-memory) upload
    is spooled to a temp file. Returns None when ffprobe cannot read it.
    """
    path = getattr(uploaded_file, 'temporary_file_path', None)
    if callable(path):
        try:
            return round(_ffprobe_duration(path()))
        except (subprocess.SubprocessError, ValueError, OSError):
            return None

    temp_path = None
    try:
        uploaded_file.seek(0)
        ext = os.path.splitext(uploaded_file.name)[1].lower() or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            temp_path = tmp.name
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
        return round(_ffprobe_duration(temp_path))
    except (subprocess.SubprocessError, ValueError, OSError):
        return None
    finally:
        uploaded_file.seek(0)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def validate_video_magic_bytes(file_obj):
    """
    Reads the first 12 bytes of an upload stream to verify a genuine
    ISO-BMFF container signature (MP4/MOV/M4V), preventing disguised
    binaries from being accepted as "video". All ISO-BMFF containers open
    with a 4-byte box size followed by a 4-byte box type — the first box
    in a valid camera/phone/editing-tool export is virtually always 'ftyp'.
    This is a best-effort container check (same spirit as
    validate_magic_bytes above), not a full codec validator.
    """
    header = file_obj.read(12)
    file_obj.seek(0)

    if len(header) >= 8 and header[4:8] == b'ftyp':
        return 'ISO-BMFF'

    raise ValidationError(
        detail="Security violation: Uploaded file signature is invalid. Only genuine MP4 and MOV video files are allowed.",
        code="invalid_file_signature"
    )

def validate_magic_bytes(file_obj):
    """
    Reads the first 8 bytes of an upload stream to verify genuine binary signatures,
    preventing hackers from uploading executables renamed as '.jpg'.
    """
    header = file_obj.read(8)
    file_obj.seek(0)  # Reset stream

    # All JPEGs globally start with the 2-byte SOI marker: FF D8
    if header.startswith(b'\xff\xd8'):
        return 'JPEG'
    # All PNGs globally start with this standard 8-byte signature
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'PNG'

    raise ValidationError(
        detail="Security violation: Uploaded file signature is invalid. Only genuine JPEG and PNG images are allowed.",
        code="invalid_file_signature"
    )
    
class LocationStripError(Exception):
    """Location metadata is present (or cannot be ruled out) and could not be removed."""


_XMP_HEADERS = (b'http://ns.adobe.com/xap/1.0/\x00', b'http://ns.adobe.com/xmp/extension/\x00')
_XMP_LOCATION_MARKERS = (b'GPSLatitude', b'GPSLongitude', b'GPSPosition', b'GPSAltitude')
_PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def _xmp_has_location(payload):
    return any(marker in payload for marker in _XMP_LOCATION_MARKERS)


def _exif_without_gps(exif_bytes):
    """EXIF (TIFF, or 'Exif\0\0'+TIFF) without its GPS IFD; raises LocationStripError when unreadable."""
    try:
        exif_dict = piexif.load(exif_bytes)
    except Exception as exc:
        raise LocationStripError('unreadable EXIF') from exc
    if not exif_dict.get('GPS'):
        return None
    exif_dict['GPS'] = {}
    try:
        return piexif.dump(exif_dict)
    except Exception as exc:
        raise LocationStripError('EXIF could not be rewritten') from exc


def _jpeg_segments(raw):
    """[(marker, segment bytes incl. marker+length)] up to SOS, plus the rest of the file."""
    if not raw.startswith(b'\xff\xd8'):
        raise LocationStripError('not a JPEG')
    pos, segments = 2, []
    while pos + 4 <= len(raw):
        if raw[pos] != 0xFF:
            raise LocationStripError('malformed JPEG marker')
        marker = raw[pos + 1]
        if marker == 0xDA or 0xD0 <= marker <= 0xD9 or marker == 0x01:   # SOS / RSTn / EOI / TEM: data follows
            break
        length = int.from_bytes(raw[pos + 2:pos + 4], 'big')
        if length < 2 or pos + 2 + length > len(raw):
            raise LocationStripError('truncated JPEG segment')
        segments.append((marker, raw[pos:pos + 2 + length]))
        pos += 2 + length
    return segments, raw[pos:]


def _strip_jpeg(raw):
    segments, rest = _jpeg_segments(raw)
    changed = False
    out = [b'\xff\xd8']
    for marker, segment in segments:
        payload = segment[4:]
        if marker == 0xE1 and payload.startswith(b'Exif\x00\x00'):
            clean = _exif_without_gps(payload)
            if clean is not None:
                out.append(b'\xff\xe1' + (len(clean) + 2).to_bytes(2, 'big') + clean)
                changed = True
                continue
        elif marker == 0xE1 and payload.startswith(_XMP_HEADERS) and _xmp_has_location(payload):
            changed = True                  # the XMP packet carries coordinates: drop that packet only
            continue
        out.append(segment)
    out.append(rest)
    return b''.join(out), changed


def _png_chunk(kind, data):
    import zlib
    return len(data).to_bytes(4, 'big') + kind + data + (zlib.crc32(kind + data) & 0xFFFFFFFF).to_bytes(4, 'big')


def _strip_png(raw):
    import zlib
    pos, out, changed = len(_PNG_SIGNATURE), [_PNG_SIGNATURE], False
    while pos + 8 <= len(raw):
        length = int.from_bytes(raw[pos:pos + 4], 'big')
        kind = raw[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(raw):
            raise LocationStripError('truncated PNG chunk')
        data = raw[pos + 8:pos + 8 + length]
        chunk = raw[pos:end]
        pos = end
        if kind == b'eXIf':
            clean = _exif_without_gps(data)
            if clean is not None:
                out.append(_png_chunk(b'eXIf', clean[6:] if clean.startswith(b'Exif\x00\x00') else clean))
                changed = True
                continue
        elif kind in (b'iTXt', b'tEXt', b'zTXt') and data.startswith(b'XML:com.adobe.xmp\x00'):
            text = data
            if kind == b'zTXt':
                try:
                    text = zlib.decompress(data.split(b'\x00', 1)[1][1:])
                except Exception as exc:
                    raise LocationStripError('unreadable compressed XMP') from exc
            if _xmp_has_location(text):
                changed = True
                continue
        out.append(chunk)
        if kind == b'IEND':
            break
    return b''.join(out), changed


def _has_location(data):
    """Independent re-check of the result (fail closed if anything is left)."""
    if data.startswith(b'\xff\xd8'):
        segments, _ = _jpeg_segments(data)
        for marker, segment in segments:
            payload = segment[4:]
            if marker == 0xE1 and payload.startswith(b'Exif\x00\x00') and _exif_without_gps(payload) is not None:
                return True
            if marker == 0xE1 and payload.startswith(_XMP_HEADERS) and _xmp_has_location(payload):
                return True
        return False
    if data.startswith(_PNG_SIGNATURE):
        return _strip_png(data)[1]
    return False


def strip_exif_gps(file_obj):
    """
    Removes location data from an uploaded photo, leaving every other byte of
    the file — pixel data, ICC profile, quality, and all non-location metadata
    (camera, lens, aperture, shutter speed) — untouched. The pixel data is never
    decoded or recompressed: only metadata segments are rewritten or dropped.

    This result becomes MediaAsset.original_file: the private, permanent master
    copy that must stay byte-preserved apart from its location.

    Covered: the JPEG EXIF GPS IFD (piexif), an XMP packet carrying GPS
    coordinates (JPEG APP1, PNG iTXt/tEXt/zTXt: that packet is dropped), and the
    PNG eXIf chunk.

    7-B (SEC-19 / debt row 94): fails CLOSED. It used to log a warning and keep
    the original bytes (GPS included) whenever anything went wrong; now it raises
    LocationStripError when location data is present, or cannot be ruled out
    (unreadable EXIF), and was not removed. The upload view refuses that file.
    """
    file_obj.seek(0)
    raw_bytes = file_obj.read()
    file_obj.seek(0)

    if raw_bytes.startswith(b'\xff\xd8'):
        clean_bytes, changed = _strip_jpeg(raw_bytes)
        content_type = 'image/jpeg'
    elif raw_bytes.startswith(_PNG_SIGNATURE):
        clean_bytes, changed = _strip_png(raw_bytes)
        content_type = 'image/png'
    else:
        return file_obj                 # not an image type this app stores (refused by validation)

    if not changed:
        return file_obj                 # no location: the original bytes, untouched
    if _has_location(clean_bytes):      # independent re-check of the result
        raise LocationStripError('location still present after stripping')

    return InMemoryUploadedFile(
        file=io.BytesIO(clean_bytes),
        field_name=None,
        name=file_obj.name,
        content_type=getattr(file_obj, 'content_type', None) or content_type,
        size=len(clean_bytes),
        charset=None
    )

def get_insertion_order(gallery_id, insert_after_id=None):
    """
    Generates a Decimal fractional sort value for midpoint placement.
    Allows single-row drag-and-drop updates on David's frontend.
    """
    from apps.photos.models import MediaAsset

    assets = MediaAsset.objects.filter(gallery_id=gallery_id).order_by('order')

    if not assets.exists():
        return Decimal('1.0')

    if insert_after_id is None:
        # Append directly to the end of the gallery list
        return assets.last().order + Decimal('1.0')

    try:
        after_node = assets.get(id=insert_after_id)
        next_node = assets.filter(order__gt=after_node.order).first()

        if next_node is None:
            return after_node.order + Decimal('1.0')

        # Calculate midpoint fraction between both surrounding objects
        return (after_node.order + next_node.order) / Decimal('2')
    except MediaAsset.DoesNotExist:
        return assets.last().order + Decimal('1.0')


    


# Phase 4 (download hardening): every format this pipeline's own upload
# validators accept or its own derivative pipeline produces is already
# entropy-dense compressed media — DEFLATE-compressing it again inside a
# ZIP archive burns CPU for essentially zero size benefit (sometimes a
# net loss, once the DEFLATE stream overhead is counted). Used to pick
# ZIP_STORED instead of ZIP_DEFLATED per-entry in the gallery ZIP download.
ALREADY_COMPRESSED_EXTS = {
    '.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.heif',
    '.mp4', '.mov', '.m4v', '.webm',
}


# Phase 4 (download hardening): strips anything that could turn an
# untrusted, user-supplied filename (MediaAsset.original_name — set
# directly from the uploaded file's own name, never validated as "safe")
# into an attack when it's later placed into an HTTP response header or
# a ZIP archive entry.
_UNSAFE_FILENAME_CHARS = re.compile(r'[\r\n"\\\x00-\x1f]')


def sanitize_download_filename(name, fallback='download'):
    """
    Produces a filename safe to use BOTH as a Content-Disposition header
    value and as a ZIP archive entry name:

    - Strips any directory path component (os.path.basename, after
      normalizing backslashes to forward slashes first) — defends
      against "zip slip" (a crafted `original_name` like
      `../../../etc/cron.d/evil` extracting outside the target directory
      when a client unzips the archive) and against the same traversal
      applying to a single-file download's saved filename.
    - Strips CR/LF and other control characters — defends against HTTP
      response header injection.
    - Strips embedded double quotes and backslashes — defends against
      breaking out of a quoted `filename="..."` header value.

    Never returns an empty string (falls back to `fallback`), since an
    empty ZIP entry name or Content-Disposition filename is its own kind
    of malformed-response edge case.
    """
    if not name:
        return fallback
    base = os.path.basename(name.replace('\\', '/'))
    cleaned = _UNSAFE_FILENAME_CHARS.sub('_', base).strip()
    return cleaned or fallback


def raise_gating_violation(message, code):
    """
    Standardized validation exception raiser designed to match
    the core/exceptions.py standardized output format.
    """
    raise PermissionDenied(
        detail={
            "error": message,
            "code": code
        }
    )   
    
    

def apply_copyright_watermark(img, text):
    """
    Legacy entry point, kept for existing callers: a plain text watermark with
    the default position/size/opacity. All rendering now lives in
    apps/core/watermark.py (relative sizing, safe fonts, logged fallback).
    """
    from apps.core.watermark import DEFAULTS, apply_watermark, make_spec
    return apply_watermark(img, make_spec({**DEFAULTS, 'text': text}))


def _normalize_to_srgb(img):
    """
    Best-effort ICC color-profile normalization — applied to DERIVATIVES
    only, never to the preserved original (see strip_exif_gps, which
    never touches color data).

    If the source carries an embedded ICC profile, converts pixel data
    through it into sRGB so a wide-gamut capture (Adobe RGB, ProPhoto
    RGB, a camera or Lightroom's own profile) renders correctly — a
    browser always treats an untagged image as sRGB, so an unconverted
    wide-gamut image looks washed out or oversaturated. The embedded
    profile is then dropped from the result: once pixel data is
    genuinely sRGB, carrying a profile along just adds bytes for no
    visual benefit.

    Never raises: a missing, unreadable, or unconvertible ICC profile
    falls back to a plain RGB conversion rather than failing the whole
    derivative pipeline over a bad embedded profile.
    """
    icc_bytes = img.info.get('icc_profile')
    if icc_bytes:
        try:
            src_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
            srgb_profile = ImageCms.createProfile('sRGB')
            converted = ImageCms.profileToProfile(img, src_profile, srgb_profile, outputMode='RGB')
            converted.info.pop('icc_profile', None)
            return converted
        except Exception:
            logger.warning("ICC-to-sRGB conversion failed; falling back to plain RGB conversion")
    return img.convert('RGB') if img.mode != 'RGB' else img


DOWNLOAD_MAX_EDGE = 3600

# Download Master encoder (chunk 6-B, calibrated in 6-A): one fixed jpegli
# encode, no quality search. cjpegli is built from a pinned commit in the
# backend Dockerfile and called by its absolute path with a fixed argv.
CJPEGLI_BIN = os.environ.get('CJPEGLI_PATH', '/usr/local/bin/cjpegli')
CJPEGLI_TIMEOUT_SECONDS = 60
JPEGLI_QUALITIES = (90, 85)       # q90 first; q85 once if q90 is larger than the source
PILLOW_FALLBACK_QUALITY = 86      # SS2-equivalent to jpegli q90 (6-A), used if cjpegli is unusable


def _file_size(file_obj):
    size = getattr(file_obj, 'size', None)
    if size is not None:
        return size
    position = file_obj.tell()
    file_obj.seek(0, io.SEEK_END)
    size = file_obj.tell()
    file_obj.seek(position)
    return size


def _encode_jpegli(image, quality):
    """
    One cjpegli encode of an sRGB RGB image (4:2:0, progressive level 2).
    Returns the JPEG bytes, or None on ANY failure (missing binary, non-zero
    exit, timeout, empty/undecodable/mis-sized output). Fixed argv,
    shell=False, timeout, private temp dir removed in `finally`; the encoder's
    own error text is logged server-side only and never returned.
    """
    tmp_dir = tempfile.mkdtemp(prefix='kyapture-master-')
    try:
        src_path = os.path.join(tmp_dir, 'in.ppm')
        out_path = os.path.join(tmp_dir, 'out.jpg')
        image.save(src_path, format='PPM')
        argv = [
            CJPEGLI_BIN, src_path, out_path,
            '-q', str(int(quality)),
            '--chroma_subsampling=420',
            '--progressive_level=2',
            '--quiet',
        ]
        try:
            result = subprocess.run(
                argv,
                shell=False,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=CJPEGLI_TIMEOUT_SECONDS,
                cwd=tmp_dir,
            )
        except subprocess.TimeoutExpired:
            logger.warning("cjpegli timed out after %ss; using Pillow fallback", CJPEGLI_TIMEOUT_SECONDS)
            return None
        except OSError as exc:
            logger.warning("cjpegli could not be started (%s); using Pillow fallback", exc.__class__.__name__)
            return None
        if result.returncode != 0:
            logger.warning(
                "cjpegli exited %s: %s; using Pillow fallback",
                result.returncode, result.stderr[-300:].decode('utf-8', 'replace'),
            )
            return None
        try:
            with open(out_path, 'rb') as handle:
                encoded = handle.read()
            with Image.open(io.BytesIO(encoded)) as check:
                check.load()
                if check.format != 'JPEG' or check.size != image.size:
                    raise ValueError('unexpected cjpegli output')
        except Exception:
            logger.warning("cjpegli produced unusable output; using Pillow fallback")
            return None
        return encoded
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _encode_jpeg_pillow(image, quality=PILLOW_FALLBACK_QUALITY):
    stream = io.BytesIO()
    image.save(stream, format='JPEG', quality=quality, optimize=True, progressive=True, subsampling=2)
    return stream.getvalue()


def _make_jpeg_master_bytes(source, original_size, capped):
    """
    Deterministic guard (6-A): encode q90; if larger than the original, q85
    once. If still larger: a source that was not capped gets no master (the
    original is served, same pixels and smaller); a capped source keeps the
    q85 master, because the 3600 px cap is what Free clients are promised and
    serving a >3600 px original would leak resolution (debt row 50).
    If cjpegli is unusable, a single Pillow q86 encode takes its place under
    the same rule.
    """
    def fits(data):
        return original_size is None or len(data) <= original_size

    encoded = None
    for quality in JPEGLI_QUALITIES:
        encoded = _encode_jpegli(source, quality)
        if encoded is None:
            break
        if fits(encoded):
            return encoded
    if encoded is None:                       # cjpegli unusable
        encoded = _encode_jpeg_pillow(source)
        if fits(encoded):
            return encoded
    return encoded if capped else None


def _make_download_master(image, source_format, base_name, original_size=None):
    """
    Encode a bounded, private client-download derivative. `image` must already
    be EXIF-oriented. JPEG: sRGB -> long edge <= 3600 (never upscaled) -> one
    fixed jpegli encode. PNG stays lossless. The preserved original is never
    written to here.
    """
    stream = io.BytesIO()
    if source_format in ('JPEG', 'JPG'):
        source = _normalize_to_srgb(image)
        if source is image:
            source = source.copy()   # thumbnail() resizes in place; never mutate the caller's image
        capped = max(source.size) > DOWNLOAD_MAX_EDGE
        source.thumbnail((DOWNLOAD_MAX_EDGE, DOWNLOAD_MAX_EDGE), Image.Resampling.LANCZOS)
        encoded_bytes = _make_jpeg_master_bytes(source, original_size, capped)
        if encoded_bytes is None:
            return None
        stream.write(encoded_bytes)
        filename = f"{base_name}_download.jpg"
        content_type = 'image/jpeg'
    elif source_format == 'PNG':
        source = image.copy()
        capped = max(source.size) > DOWNLOAD_MAX_EDGE
        source.thumbnail((DOWNLOAD_MAX_EDGE, DOWNLOAD_MAX_EDGE), Image.Resampling.LANCZOS)
        png_kwargs = {'format': 'PNG', 'optimize': True}
        if source.info.get('icc_profile'):
            png_kwargs['icc_profile'] = source.info['icc_profile']
        source.save(stream, **png_kwargs)
        if original_size is not None and stream.tell() > original_size and not capped:
            return None
        filename = f"{base_name}_download.png"
        content_type = 'image/png'
    else:
        return None

    return SimpleUploadedFile(filename, stream.getvalue(), content_type=content_type)


def process_download_master(image_file):
    """Create only a missing download master without regenerating web tiers."""
    image_file.seek(0)
    source_image = Image.open(image_file)
    source_format = (source_image.format or '').upper()
    source_image = exif_transpose(source_image)
    base_name = os.path.splitext(image_file.name)[0]
    try:
        return _make_download_master(
            source_image,
            source_format,
            base_name,
            original_size=_file_size(image_file),
        )
    finally:
        image_file.seek(0)


_DISPLAY_TIERS = (
    # (max longest edge px, WebP quality, filename suffix)
    (2048, 82, "display"),   # full-screen / lightbox view
    (1280, 80, "medium"),    # typical in-page grid-column width
    (640, 75, "thumb"),      # grid thumbnails, incl. high-DPI phones
)


def _build_display_tiers(img, base_name, watermark=None):
    """
    The three client-visible WebP derivatives from one oriented, sRGB-normalized
    image, optionally watermarked. Shared by first-time processing and by
    regeneration after a watermark-setting change so both always produce
    identical tiers. WebP save() never carries EXIF/ICC metadata unless it is
    passed explicitly — derivatives are metadata-free by construction.
    """
    from apps.core.watermark import apply_watermark

    files = []
    for max_edge, quality, suffix in _DISPLAY_TIERS:
        derivative_img = img.copy()
        derivative_img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        if watermark is not None:
            derivative_img = apply_watermark(derivative_img, watermark)
        stream = io.BytesIO()
        derivative_img.save(stream, format='WEBP', quality=quality)
        files.append(SimpleUploadedFile(f"{base_name}_{suffix}.webp", stream.getvalue(), content_type="image/webp"))
    return tuple(files)


def regenerate_display_derivatives(image_file, watermark=None):
    """
    Rebuilds ONLY the display/medium/thumbnail tiers from the preserved
    original, with `watermark` (or none). Does not touch the Download Master,
    the BlurHash or the original — used to re-apply watermark settings to
    already-processed assets. Pure function of (original bytes, spec), so
    running it twice yields the same files.
    Returns (display_file, medium_file, thumbnail_file).
    """
    image_file.seek(0)
    try:
        img = exif_transpose(Image.open(image_file))
        img = _normalize_to_srgb(img)
        return _build_display_tiers(img, os.path.splitext(image_file.name)[0], watermark)
    finally:
        image_file.seek(0)


def process_image_pipeline(image_file, watermark_text=None, watermark=None):
    """
    Unified image-derivative pipeline: PRESERVED ORIGINAL (handled
    upstream by strip_exif_gps — never touched here) → OPTIMIZED
    DERIVATIVES.

    Reads the source file once, fixes EXIF orientation, normalizes color
    to sRGB (see _normalize_to_srgb), conditionally applies a
    translucent copyright watermark, and generates the MVP 640/1280/2048
    derivative set (evaluated against the Phase 2 plan as written — a
    fourth tier or AVIF was not added, since there's no demonstrated MVP
    need for either):

    1. Display WebP   — max 2048px on the longest edge (full-screen /
       lightbox view)
    2. Medium WebP    — max 1280px on the longest edge (typical in-page
       grid-column width on desktop/tablet — the gap the previous
       two-tier set left, forcing a phone-sized 600/640px image or the
       full 2048px lightbox image into an ordinary page view)
    3. Thumbnail WebP — max 640px on the longest edge (grid thumbnails,
       including on high-DPI phone screens)
    4. BlurHash string

    Every derivative is generated from the SAME normalized, oriented,
    optionally-watermarked in-memory image — the source is read exactly
    once. Generation is a pure function of image_file's bytes, so
    re-running it (a Celery retry) always reproduces the same output for
    the same input; combined with PublicMediaStorage's deterministic,
    overwrite-on-write keys (apps/photos/models.py, apps/core/storage.py)
    that makes retries idempotent and orphan-free.

    `watermark` is a WatermarkSpec (apps/core/watermark.py) or None. It is
    applied to the display/medium/thumbnail tiers ONLY. The Download Master
    is built from the un-watermarked, oriented source and the preserved
    original is never written to here — see the contract in watermark.py.
    `watermark_text` is the legacy plain-text form and is converted to a spec.

    Returns tuple: (display_file, medium_file, thumbnail_file,
    download_file, blurhash_str)
    """
    if watermark is None and watermark_text:
        from apps.core.watermark import DEFAULTS, make_spec
        watermark = make_spec({**DEFAULTS, 'text': watermark_text})

    image_file.seek(0)
    img = Image.open(image_file)
    source_format = (img.format or '').upper()
    img = exif_transpose(img)       # Correct rotation from DSLR/phone orientation metadata
    # Keep a separate oriented PNG source for the download master. The
    # display tiers are intentionally normalized to opaque sRGB WebP, but a
    # PNG download must retain alpha and its lossless semantics.
    download_source = img.copy()
    img = _normalize_to_srgb(img)   # Correct wide-gamut color profiles to browser-standard sRGB

    base_name = os.path.splitext(image_file.name)[0]

    # ─── 1-3. Display (2048px) / Medium (1280px) / Thumbnail (640px) WebP ───
    display_file, medium_file, thumbnail_file = _build_display_tiers(img, base_name, watermark)

    # ─── 4. Bounded client Download Master ─────────────────────────────────
    # JPEGs are measured across high-quality progressive strategies and are
    # capped at DOWNLOAD_MAX_EDGE. PNGs stay lossless and retain transparency.
    # If no candidate is both visually acceptable and no larger than the
    # source, the download views safely fall back to the preserved original.
    download_file = _make_download_master(
        download_source,
        source_format,
        base_name,
        original_size=_file_size(image_file),
    )

    # ─── 5. Generate BlurHash String ───
    # Previously this ALWAYS fell back to one single hardcoded placeholder
    # string for every image ever uploaded, for two independent reasons:
    #   (a) the `blurhash` package was never listed in requirements.txt,
    #       so `import blurhash` always raised ImportError;
    #   (b) even installed, the call used `x_components=`/`y_components=`
    #       keyword arguments that don't exist on the real `blurhash`
    #       PyPI package (its actual signature is `components_x=`/
    #       `components_y=`), AND that package's encode() needs a plain
    #       3-dimensional [y][x][r,g,b] array, not a PIL Image object —
    #       both would have raised TypeError even with the package
    #       installed. Both are fixed below; verified against the real
    #       `blurhash==1.1.5` package.
    default_placeholder = "LEHV6nWB2yk8pyo0adR*.7kCMdnj"
    blurhash_str = default_placeholder
    try:
        import blurhash
        blur_img = img.copy()
        # Small, fixed size keeps encode time negligible regardless of
        # source resolution — blurhash is a heavily-downsampled summary,
        # so more input resolution buys nothing.
        blur_img.thumbnail((100, 100), Image.Resampling.LANCZOS)
        if blur_img.mode != 'RGB':
            blur_img = blur_img.convert('RGB')

        width, height = blur_img.size
        pixels = list(blur_img.getdata())
        pixel_rows = [pixels[y * width:(y + 1) * width] for y in range(height)]
        blurhash_str = blurhash.encode(pixel_rows, components_x=4, components_y=4)
    except Exception:
        logger.warning("blurhash encode failed for %s — using placeholder", image_file.name)

    # Reset stream pointer for S3 upload preservation
    image_file.seek(0)

    return display_file, medium_file, thumbnail_file, download_file, blurhash_str

# ffmpeg time limits (7-B, SEC-18 / debt row 93). A crafted or pathological
# video must never hold a worker forever: every call has a timeout, the
# transcode one in proportion to the video's length.
FFMPEG_POSTER_TIMEOUT_SECONDS = 120
FFMPEG_TRANSCODE_BASE_SECONDS = 600
FFMPEG_TRANSCODE_SECONDS_PER_VIDEO_SECOND = 3
FFMPEG_REMUX_BASE_SECONDS = 300

_LOCATION_TAG = re.compile(r'location|iso6709|xyz|gps', re.IGNORECASE)


def video_location_tags(path):
    """
    The container/stream tags of a video that carry a location (QuickTime
    `©xyz` and `com.apple.quicktime.location.ISO6709` both surface as
    `location...`), plus whether it has a timed-metadata track (`mebx`, used
    by phones for per-frame location). Raises on an unreadable file.
    """
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format_tags:stream=codec_type,codec_tag_string:stream_tags',
         '-of', 'json', path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, timeout=60,
    )
    import json
    data = json.loads(result.stdout or '{}')
    tags = {k: v for k, v in (data.get('format', {}).get('tags') or {}).items() if _LOCATION_TAG.search(k)}
    timed_metadata = False
    for stream in data.get('streams', []):
        tags.update({k: v for k, v in (stream.get('tags') or {}).items() if _LOCATION_TAG.search(k)})
        if stream.get('codec_type') == 'data' and stream.get('codec_tag_string') == 'mebx':
            timed_metadata = True
    return tags, timed_metadata


def remove_video_location(source_path, duration_seconds):
    """
    A copy of the video at `source_path` with its location removed, or None when
    it carries none. Stream copy (`-c copy`): the video and audio packets are
    byte-identical; only the container's metadata changes (all global/stream
    metadata is dropped, as are data/timed-metadata tracks). Raises on failure:
    the caller fails closed (7-B, SEC-19 / debt row 94).
    """
    tags, timed_metadata = video_location_tags(source_path)
    if not tags and not timed_metadata:
        return None
    ext = os.path.splitext(source_path)[1] or '.mp4'
    fd, clean_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-i', source_path, '-map', '0:v?', '-map', '0:a?', '-c', 'copy',
             '-map_metadata', '-1', '-map_metadata:s:v', '-1', '-map_metadata:s:a', '-1', '-map_chapters', '-1',
             clean_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
            timeout=FFMPEG_REMUX_BASE_SECONDS + int(duration_seconds),
        )
        left, _ = video_location_tags(clean_path)
        if left:
            raise RuntimeError('location metadata survived the remux')
        return clean_path
    except Exception:
        os.remove(clean_path)
        raise


def process_video_pipeline(video_file, on_location_removed=None):
    """
    Video-derivative pipeline: PRIVATE ORIGINAL VIDEO (untouched here —
    only ever read) → ASYNC PROCESSING → BROWSER-FRIENDLY DERIVATIVE.

    Spools the original video to a temporary disk file using CHUNKED
    reads (`video_file.chunks()`) instead of one `.read()` call that
    materializes the entire file as an in-memory `bytes` object — the
    previous implementation did exactly that, so a multi-GB upload held
    its full size in the Celery worker's RAM at once. Chunked reads keep
    memory bounded to one chunk regardless of file size, and work
    identically whether original_file is on local disk or streamed from
    S3 (PrivateMediaStorage).

    Then runs safe (shell=False, fixed argument-list) FFprobe/FFmpeg
    subprocess calls to:
    1. Extract the exact video duration.
    2. Capture a poster frame (JPEG) at a timestamp GUARANTEED to fall
       inside the video's actual duration. The previous hardcoded
       "seek to 00:00:02" produced a completely empty/failed output for
       any video shorter than 2 seconds — a real bug, and "short video"
       is one of the explicit MVP test cases this phase calls for.
    3. Transcode ONE browser-compatible H.264 (yuv420p) / AAC MP4
       derivative with faststart (front-loaded moov atom, so playback
       can begin before the whole file downloads), scaled DOWN (never
       up) to a 1080p-max height. 1080p mirrors the image pipeline's own
       precedent of a fixed largest-tier cap (2048px) — the product
       defines no other video resolution limit today, so this is an
       explicit, documented inference, not a measured requirement.
       Replaces the previous 3-second silent WebM hover-preview clip:
       confirmed dead code (no frontend view reads `preview_url` /
       `preview_file`), so generating it was a wasted FFmpeg pass and a
       wasted stored derivative — exactly what "do not generate
       unnecessary video variants" rules out.

    Guarantees filesystem hygiene by unlinking every temp file from disk
    inside a 'finally' block regardless of success or failure.

    7-B: location metadata never reaches a client. When the original carries a
    location, a stream-copied clean original is made first; it is handed to
    `on_location_removed(open_file, size)` (the task stores it as the new
    original) and the poster and playback copy are made from it. The poster and
    playback commands also drop all metadata (`-map_metadata -1`). Any failure
    raises, so the asset fails closed. Every ffmpeg call has a timeout.

    Returns tuple: (poster_file, playback_file, duration_seconds)
    """
    temp_video_path = None
    temp_poster_path = None
    temp_playback_path = None
    clean_video_path = None

    try:
        # 1. Stream the original to a temp disk file in bounded chunks —
        #    never materialize the whole video as one in-memory object.
        video_file.seek(0)
        ext = os.path.splitext(video_file.name)[1].lower() or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_video:
            temp_video_path = temp_video.name
            for chunk in video_file.chunks():
                temp_video.write(chunk)
        video_file.seek(0)

        # 2. Extract exact video duration using FFprobe (same helper the
        #    upload endpoint uses, so both store the same whole-second value)
        duration_float = _ffprobe_duration(temp_video_path)
        duration = round(duration_float)

        clean_video_path = remove_video_location(temp_video_path, duration_float)
        if clean_video_path is not None:
            if on_location_removed is not None:
                with open(clean_video_path, 'rb') as clean:
                    on_location_removed(clean, os.path.getsize(clean_video_path))
            temp_video_path, clean_video_path = clean_video_path, temp_video_path

        # 3. Extract a poster frame (JPEG) at a SAFE timestamp — the
        #    clip's midpoint, capped at 2s, so it reliably lands inside
        #    both very short and ordinary-length videos (never seeks
        #    past end-of-file the way a hardcoded 2s offset could).
        poster_ts = max(0.0, min(2.0, duration_float * 0.5)) if duration_float > 0 else 0.0

        temp_poster_fd, temp_poster_path = tempfile.mkstemp(suffix=".jpg")
        os.close(temp_poster_fd)

        ffmpeg_poster_cmd = [
            'ffmpeg', '-y', '-ss', f'{poster_ts:.3f}',
            '-i', temp_video_path,
            '-map_metadata', '-1',
            '-vframes', '1', '-f', 'image2',
            temp_poster_path
        ]
        subprocess.run(ffmpeg_poster_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                       timeout=FFMPEG_POSTER_TIMEOUT_SECONDS)

        with open(temp_poster_path, 'rb') as f:
            poster_data = f.read()
        poster_name = os.path.splitext(video_file.name)[0] + "_poster.jpg"
        poster_file = SimpleUploadedFile(poster_name, poster_data, content_type="image/jpeg")

        # 4. Transcode ONE browser-compatible H.264/AAC MP4 playback
        #    derivative. yuv420p is required for broad decoder
        #    compatibility (notably Safari/iOS); faststart lets playback
        #    begin before the full file has downloaded; scale-down-only
        #    (via min(1080, ih)) never upscales a smaller source.
        #    Works unmodified for video-only sources too — ffmpeg simply
        #    emits no audio stream when the input has none.
        temp_playback_fd, temp_playback_path = tempfile.mkstemp(suffix=".mp4")
        os.close(temp_playback_fd)

        ffmpeg_playback_cmd = [
            'ffmpeg', '-y', '-i', temp_video_path,
            '-vf', "scale='-2:min(1080,ih)'",
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k',
            '-map_metadata', '-1', '-map_metadata:s:v', '-1', '-map_metadata:s:a', '-1', '-map_chapters', '-1',
            '-movflags', '+faststart',
            '-f', 'mp4',
            temp_playback_path
        ]
        subprocess.run(
            ffmpeg_playback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
            timeout=FFMPEG_TRANSCODE_BASE_SECONDS + FFMPEG_TRANSCODE_SECONDS_PER_VIDEO_SECOND * duration,
        )

        with open(temp_playback_path, 'rb') as f:
            playback_data = f.read()
        playback_name = os.path.splitext(video_file.name)[0] + "_playback.mp4"
        playback_file = SimpleUploadedFile(playback_name, playback_data, content_type="video/mp4")

        return poster_file, playback_file, duration

    except Exception as e:
        raise RuntimeError(f"FFmpeg/FFprobe system processing execution failed: {str(e)}")

    finally:
        # Strict filesystem hygiene: clean up all disk remnants regardless of success or failure
        for path in [temp_video_path, temp_poster_path, temp_playback_path, clean_video_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

def sanitize_text(text):
    """
    Surgically strips all HTML/JS tags from user-provided input strings.
    Prevents persistent Cross-Site Scripting (XSS) payload storage 
    inside gallery titles, descriptions, and photographer bio fields.

    bleach.clean() is built for producing HTML-safe *markup*, so besides
    removing tags it also HTML-entity-escapes survivors (e.g. "&" becomes
    "&amp;", '"' becomes "&quot;"). We store this as plain text — React
    renders it as JSX text content, never via dangerouslySetInnerHTML — so
    that escaping has no protective value here and only corrupts normal
    input (an ampersand in a couple's names, a title in quotes, emoji are
    passed through untouched by bleach but neighboring quotes/ampersands
    were getting mangled). html.unescape() after cleaning restores the
    literal characters. This is safe: tags themselves were already removed
    by strip=True, so unescaping cannot re-introduce a live tag — at worst
    an encoded "&lt;script&gt;" becomes the inert literal text "<script>",
    which renders as visible text, not executable markup.
    """
    if not text:
        return ""

    try:
        import bleach
        import html
        # Strip all HTML tags/attributes, then undo bleach's entity-escaping
        # of the plain-text characters that survive (&, quotes, etc).
        cleaned = bleach.clean(text, tags=[], strip=True)
        return html.unescape(cleaned)
    except ImportError:
        # Fallback safeguard: If bleach is not installed, run basic character stripping
        import re
        clean = re.sub('<[^<]+?>', '', text)
        return clean
