import os
import secrets
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
from django.utils.text import slugify


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


def generate_image_thumbnail(image_field, max_size=(800, 800), quality=85):
    """
    Processes an uploaded original high-res image entirely in-memory using Pillow.
    Converts color modes, scales keeping aspect ratios, applies optimization,
    and returns a Django-compatible ContentFile ready for direct storage saving [1.1.2].
    """
    try:
        # 1. Open the raw image file from the Django field
        img = Image.open(image_field)
        
        # 2. Convert complex formats (RGBA/PNG/TIFF) to web-safe RGB
        if img.mode in ('RGBA', 'P', 'CMYK'):
            img = img.convert('RGB')
            
        # 3. Calculate aspect ratio and scale down to max boundaries using high-quality resampling
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # 4. Stream binary data into an in-memory RAM buffer (avoiding slow disk writes) [1.1.2]
        buffer = BytesIO()
        
        # Save as modern WebP format for superior compression and loading speeds
        img.save(buffer, format='WEBP', quality=quality, optimize=True)
        buffer.seek(0)
        
        # 5. Extract original extension and construct a clean output filename
        original_filename = os.path.basename(image_field.name)
        filename_root = os.path.splitext(original_filename)[0]
        output_filename = f"{filename_root}_thumb.webp"
        
        # 6. Wrap memory buffer inside a Django-safe ContentFile [1.1.2]
        return ContentFile(buffer.read(), name=output_filename)
        
    except Exception as e:
        # Fallback safeguard: If image processing fails, return None so the system doesn't crash
        return None