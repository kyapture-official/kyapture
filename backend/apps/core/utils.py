# C:/Users/LENOVO/Desktop/kyapture/backend/apps/core/utils.py
import io
import logging
import piexif
import os
import secrets
import subprocess  
import tempfile 
from decimal import Decimal

from PIL import Image, ImageDraw, ImageFont, ImageCms
from PIL.ImageOps import exif_transpose
from PIL import Image as PILImage

from django.core.files.base import ContentFile
from django.utils.text import slugify
from django.db.models import Sum, Count
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

    # Fallback default limits if no active plan is found (SaaS safety net)
    default_limits = {
        "plan_name": "Free (Trial)",
        "max_galleries": None,
        "max_photos_per_gallery": None,
        "storage_bytes_limit": 3 * 1024 * 1024 * 1024,  # 3 GB limit
        "allow_video": False,
        "current_galleries_count": 0,
        "current_total_storage_bytes": 0,
    }

    # 1. Fetch current active subscription plan
    try:
        active_sub = UserSubscription.objects.select_related('plan').get(
            user=user, 
            status='active'
        )
        plan = active_sub.plan
        limits = {
            "plan_name": plan.name,
            "max_galleries": plan.max_galleries,
            "max_photos_per_gallery": plan.max_photos_per_gallery,
            "storage_bytes_limit": plan.storage_gb * 1024 * 1024 * 1024,
            "allow_video": True,
        }
    except UserSubscription.DoesNotExist:
        # Fall back to free tier or force subscription via standard metadata
        limits = default_limits

    # 2. Single-pass Aggregation for Current Usage
    # Count only soft-deleted (is_active=True) galleries for accurate billing metrics
    limits["current_galleries_count"] = Gallery.objects.filter(
        photographer=user, 
        is_active=True
    ).count()

    # Calculate total database storage footprints and photo count across active collections
    asset_aggregation = MediaAsset.objects.filter(
        gallery__photographer=user,
        gallery__is_active=True
    ).aggregate(total_bytes=Sum('file_size'), total_count=Count('id'))

    limits["current_total_storage_bytes"] = asset_aggregation['total_bytes'] or 0
    limits["current_photos_count"] = asset_aggregation['total_count'] or 0
    return limits

# Magic Byte Signatures for strict JPEG and PNG security verification
_ALLOWED_SIGNATURES = [
    b'\xff\xd8\xff\xe0',  # JPEG JFIF
    b'\xff\xd8\xff\xe1',  # JPEG Exif
    b'\xff\xd8\xff\xe2',  # JPEG with ICC profile
    b'\xff\xd8\xff\xdb',  # JPEG raw tables
    b'\x89PNG\r\n\x1a\n', # PNG
]


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
    
def strip_exif_gps(file_obj):
    """
    Strips raw GPS location coordinates from JPEG EXIF metadata to protect
    client privacy, while leaving every other byte of the file — pixel
    data, ICC color profile, quality, and all non-GPS metadata (camera,
    lens, aperture, shutter speed) — completely untouched.

    This result becomes MediaAsset.original_file: the private, permanent
    master copy Phase 2 requires to be byte-preserved. The previous
    implementation decoded the image with PIL and re-saved it (even at
    quality=100), which always fully recompresses JPEG pixel data and
    silently drops the ICC profile — that re-encode was happening to
    every uploaded original, not just a derivative. piexif.insert()
    instead rewrites only the JPEG's APP1/EXIF segment directly in the
    raw byte stream: pixel data is never decoded or recompressed.
    """
    try:
        file_obj.seek(0)
        raw_bytes = file_obj.read()
        file_obj.seek(0)

        # Only JPEGs carry EXIF the way piexif understands it; PNGs (and
        # anything else) pass through completely untouched, exactly as
        # before.
        if not raw_bytes.startswith(b'\xff\xd8'):
            return file_obj

        try:
            exif_dict = piexif.load(raw_bytes)
        except Exception:
            # No parseable EXIF segment — nothing to strip, original
            # bytes already carry no GPS data.
            return file_obj

        if not exif_dict.get('GPS'):
            # No GPS tags present — return the original bytes completely
            # untouched instead of doing a needless rewrite.
            file_obj.seek(0)
            return file_obj

        exif_dict['GPS'] = {}
        clean_exif_bytes = piexif.dump(exif_dict)

        output_stream = io.BytesIO()
        piexif.insert(clean_exif_bytes, raw_bytes, output_stream)
        clean_bytes = output_stream.getvalue()

        return InMemoryUploadedFile(
            file=io.BytesIO(clean_bytes),
            field_name=None,
            name=file_obj.name,
            content_type=getattr(file_obj, 'content_type', None) or 'image/jpeg',
            size=len(clean_bytes),
            charset=None
        )
    except Exception:
        # Log warning so failure rate is monitorable instead of silent
        logger.warning("strip_exif_gps failed for %s — uploading with EXIF intact", file_obj.name)
        file_obj.seek(0)
        return file_obj

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
    Overlays a translucent white copyright text with a subtle dark drop shadow 
    at the bottom-right corner of the image.
    Calculates font-size dynamically relative to image width to support 4K/8K images.
    """
    try:
        # 1. Create a transparent overlay layer matching original image dimensions
        watermark_layer = Image.new('RGBA', img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(watermark_layer)
        
        # 2. Compute dynamic, scale-proportional font size (3% of image width)
        width, height = img.size
        font_size = max(16, int(width * 0.03))
        
        try:
            # Fallback chain: Arial truetype -> default system font
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        clean_text = f" {text} "

        # 3. Calculate text bounding dimensions for bottom-right corner positioning
        try:
            left, top, right, bottom = draw.textbbox((0, 0), clean_text, font=font)
            text_width = right - left
            text_height = bottom - top
        except AttributeError:
            # Fallback for older Pillow installations
            text_width, text_height = draw.textsize(clean_text, font=font) if hasattr(draw, 'textsize') else (100, 20)

        # Set 5% margins from the image borders
        margin_x = int(width * 0.05)
        margin_y = int(height * 0.05)
        x = width - text_width - margin_x
        y = height - text_height - margin_y

        # 4. Draw Translucent Shadow (Black at 35% opacity) for visibility on white backdrops
        draw.text((x + 2, y + 2), clean_text, font=font, fill=(0, 0, 0, 90))

        # 5. Draw Primary Text (White at 55% opacity)
        draw.text((x, y), clean_text, font=font, fill=(255, 255, 255, 140))

        # 6. Composite the transparent overlay back onto the original image
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
            
        return Image.alpha_composite(img, watermark_layer).convert('RGB')
    except Exception:
        # Fallback security: If watermarking fails, return the original image un-watermarked
        return img.convert('RGB') if img.mode != 'RGB' else img

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


def process_image_pipeline(image_file, watermark_text=None):
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

    Returns tuple: (display_file, medium_file, thumbnail_file, blurhash_str)
    """
    image_file.seek(0)
    img = Image.open(image_file)
    img = exif_transpose(img)       # Correct rotation from DSLR/phone orientation metadata
    img = _normalize_to_srgb(img)   # Correct wide-gamut color profiles to browser-standard sRGB

    base_name = os.path.splitext(image_file.name)[0]

    def _make_derivative(max_edge, quality, suffix):
        derivative_img = img.copy()
        derivative_img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

        if watermark_text:
            derivative_img = apply_copyright_watermark(derivative_img, watermark_text)

        stream = io.BytesIO()
        # WebP save() never carries over EXIF/ICC metadata unless it's
        # explicitly passed in — derivatives are metadata-free by
        # construction here, not because anything is being stripped.
        derivative_img.save(stream, format='WEBP', quality=quality)
        stream.seek(0)

        filename = f"{base_name}_{suffix}.webp"
        return SimpleUploadedFile(filename, stream.read(), content_type="image/webp")

    # ─── 1. Display WebP (2048px — full-screen lightbox view) ───
    display_file = _make_derivative(2048, 82, "display")

    # ─── 2. Medium WebP (1280px — grid/in-page column width) ───
    medium_file = _make_derivative(1280, 80, "medium")

    # ─── 3. Thumbnail WebP (640px — grid thumbnails, incl. high-DPI phones) ───
    thumbnail_file = _make_derivative(640, 75, "thumb")

    # ─── 4. Generate BlurHash String ───
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

    return display_file, medium_file, thumbnail_file, blurhash_str

def process_video_pipeline(video_file):
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

    Returns tuple: (poster_file, playback_file, duration_seconds)
    """
    temp_video_path = None
    temp_poster_path = None
    temp_playback_path = None

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

        # 2. Extract exact video duration using FFprobe
        ffprobe_cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            temp_video_path
        ]
        duration_result = subprocess.run(
            ffprobe_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        duration_float = float((duration_result.stdout or "0").strip() or 0.0)
        duration = int(duration_float)

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
            '-vframes', '1', '-f', 'image2',
            temp_poster_path
        ]
        subprocess.run(ffmpeg_poster_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

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
            '-movflags', '+faststart',
            '-f', 'mp4',
            temp_playback_path
        ]
        subprocess.run(ffmpeg_playback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        with open(temp_playback_path, 'rb') as f:
            playback_data = f.read()
        playback_name = os.path.splitext(video_file.name)[0] + "_playback.mp4"
        playback_file = SimpleUploadedFile(playback_name, playback_data, content_type="video/mp4")

        return poster_file, playback_file, duration

    except Exception as e:
        raise RuntimeError(f"FFmpeg/FFprobe system processing execution failed: {str(e)}")

    finally:
        # Strict filesystem hygiene: clean up all disk remnants regardless of success or failure
        for path in [temp_video_path, temp_poster_path, temp_playback_path]:
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