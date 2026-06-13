import os
import secrets
from io import BytesIO
from PIL import Image
from PIL.ImageOps import exif_transpose
from django.core.files.base import ContentFile
from django.utils.text import slugify
from django.db.models import Sum, Count
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import PermissionDenied
from apps.subscriptions.models import UserSubscription, SubscriptionPlan
from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset

def generate_unique_slug(model_class, title, **lookup_filters):
    """
    Generates a URL-safe slug, dynamically scoped to multi-tenant filters
    to prevent cross-photographer namespace collisions [1.2.7].
    
    Example Usage:
        slug = generate_unique_slug(Gallery, "My Wedding", photographer=user)
    """
    base_slug = slugify(title)
    if not base_slug:
        base_slug = "untitled"
        
    slug = base_slug
    counter = 1
    
    # Scopes the database existence check strictly to the provided tenant filter [1.2.7]
    while model_class.objects.filter(slug=slug, **lookup_filters).exists():
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
    from apps.subscriptions.models import UserSubscription, SubscriptionPlan
    from apps.galleries.models import Gallery
    from apps.photos.models import MediaAsset

    # Fallback default limits if no active plan is found (SaaS safety net)
    default_limits = {
        "plan_name": "Free (Trial)",
        "max_galleries": 3,
        "max_photos_per_gallery": 50,
        "storage_bytes_limit": 2 * 1024 * 1024 * 1024,  # 2 GB Fallback
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

    # Calculate total database storage footprints across active collections
    storage_aggregation = MediaAsset.objects.filter(
        gallery__photographer=user,
        gallery__is_active=True
    ).aggregate(total_bytes=Sum('file_size'))

    limits["current_total_storage_bytes"] = storage_aggregation['total_bytes'] or 0
    
    return limits

import io
import piexif
from PIL import Image as PILImage
from django.core.files.uploadedfile import InMemoryUploadedFile
from decimal import Decimal
from rest_framework.exceptions import ValidationError

# Magic Byte Signatures for strict JPEG and PNG security verification
_ALLOWED_SIGNATURES = [
    b'\xff\xd8\xff\xe0',  # JPEG JFIF
    b'\xff\xd8\xff\xe1',  # JPEG Exif
    b'\xff\xd8\xff\xe2',  # JPEG with ICC profile
    b'\xff\xd8\xff\xdb',  # JPEG raw tables
    b'\x89PNG\r\n\x1a\n', # PNG
]

def validate_magic_bytes(file_obj):
    """
    Reads the first 8 bytes of an upload stream to verify genuine binary signatures,
    preventing hackers from uploading executables renamed as '.jpg'.
    """
    header = file_obj.read(8)
    file_obj.seek(0)  # Reset stream

    for sig in _ALLOWED_SIGNATURES:
        if header[:len(sig)] == sig:
            return 'PNG' if sig.startswith(b'\x89PNG') else 'JPEG'

    raise ValidationError(
        detail="Security violation: Uploaded file signature is invalid. Only genuine JPEG and PNG images are allowed.",
        code="invalid_file_signature"
    )

def strip_exif_gps(file_obj):
    """
    Strips raw GPS location coordinates from JPEG EXIF metadata to protect client privacy,
    while leaving harmless metadata (camera lens, aperture, shutter speed) intact.
    """
    try:
        file_obj.seek(0)
        img = PILImage.open(file_obj)

        # Skip PNGs or JPEGs without EXIF footprints
        if img.format != 'JPEG' or 'exif' not in img.info:
            file_obj.seek(0)
            return file_obj

        exif_dict = piexif.load(img.info['exif'])
        
        # Purge GPS tags completely
        exif_dict.pop('GPS', None)
        clean_exif_bytes = piexif.dump(exif_dict)

        output_stream = io.BytesIO()
        img.save(output_stream, format='JPEG', exif=clean_exif_bytes, quality=100)
        output_stream.seek(0)

        # Wrap back into standard Django InMemoryUploadedFile
        return InMemoryUploadedFile(
            file=output_stream,
            field_name=None,
            name=file_obj.name,
            content_type='image/jpeg',
            size=output_stream.getbuffer().nbytes,
            charset=None
        )
    except Exception:
        # Fallback security: If stripping fails, do not block the request
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


    return limits


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
    
    
def process_image_pipeline(image_file):
    """
    Unified High-Performance Image Processing Pipeline.
    
    Reads the original source file exactly once in memory, fixes EXIF orientation,
    and generates:
    1. Display WebP (Max 2048px on longest edge, 80% quality)
    2. Thumbnail WebP (Max 600px on longest edge, 70% quality)
    3. BlurHash Base85 string (calculated from a fast 100x100 downsampled frame)
    
    Returns tuple: (display_file, thumbnail_file, blurhash_str)
    """
    image_file.seek(0)
    img = Image.open(image_file)
    img = exif_transpose(img)  # Rotate image based on DSLR metadata orientation
    
    # ─── 1. Generate WebP Display File (2048px Lightbox View) ───
    display_img = img.copy()
    display_img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    
    display_stream = io.BytesIO()
    display_img.save(display_stream, format='WEBP', quality=80)
    display_stream.seek(0)
    
    display_filename = os.path.splitext(image_file.name)[0] + "_display.webp"
    display_file = SimpleUploadedFile(display_filename, display_stream.read(), content_type="image/webp")

    # ─── 2. Generate WebP Thumbnail File (600px Grid View) ───
    thumb_img = img.copy()
    thumb_img.thumbnail((600, 600), Image.Resampling.LANCZOS)
    
    thumb_stream = io.BytesIO()
    thumb_img.save(thumb_stream, format='WEBP', quality=70)
    thumb_stream.seek(0)
    
    thumb_filename = os.path.splitext(image_file.name)[0] + "_thumb.webp"
    thumbnail_file = SimpleUploadedFile(thumb_filename, thumb_stream.read(), content_type="image/webp")

    # ─── 3. Generate BlurHash String ───
    default_placeholder = "LEHV6nWB2yk8pyo0adR*.7kCMdnj"
    blurhash_str = default_placeholder
    try:
        import blurhash
        blur_img = img.copy()
        # Keep dimensions extremely small to guarantee immediate calculation speeds
        blur_img.thumbnail((100, 100), Image.Resampling.LANCZOS)
        if blur_img.mode != 'RGB':
            blur_img = blur_img.convert('RGB')
        blurhash_str = blurhash.encode(blur_img, x_components=4, y_components=4)
    except Exception:
        pass  # Gracefully falls back to grey placeholder if package is missing or errors out

    # Reset stream pointers for S3 upload preservation
    image_file.seek(0)
    
    return display_file, thumbnail_file, blurhash_str    