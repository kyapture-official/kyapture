import io
import os
from PIL import Image as PILImage, UnidentifiedImageError
from PIL.ImageOps import exif_transpose
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers

from .models import MediaAsset

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB Limit
ALLOWED_IMAGE_FORMATS = {'JPEG', 'JPG', 'PNG', 'WEBP', 'TIFF'}
ALLOWED_FORMAT_NAMES = 'JPEG, JPG, PNG, WEBP, TIFF'


# ─────────────────────────────────────────────────────────────
# IN-MEMORY MULTI-TIER IMAGE GENERATORS
# ─────────────────────────────────────────────────────────────

def generate_display_webp(image_file):
    """
    Generates a web-optimized 2048px display variant in memory.
    Saves as WebP at 80% quality to compress multi-megabyte files down to ~500KB.
    """
    image_file.seek(0)
    img = PILImage.open(image_file)
    img = exif_transpose(img)  # Correct DSLR rotation metadata
    
    # Scale Down preserving aspect ratio
    img.thumbnail((2048, 2048), PILImage.Resampling.LANCZOS)
    
    output_stream = io.BytesIO()
    img.save(output_stream, format='WEBP', quality=80)
    output_stream.seek(0)
    
    filename = os.path.splitext(image_file.name)[0] + "_display.webp"
    return SimpleUploadedFile(filename, output_stream.read(), content_type="image/webp")


def generate_thumbnail_webp(image_file):
    """
    Generates a fast-loading 600px thumbnail variant in memory.
    Saves as WebP at 70% quality to ensure grid rendering fits under 100KB per card.
    """
    image_file.seek(0)
    img = PILImage.open(image_file)
    img = exif_transpose(img)
    
    img.thumbnail((600, 600), PILImage.Resampling.LANCZOS)
    
    output_stream = io.BytesIO()
    img.save(output_stream, format='WEBP', quality=70)
    output_stream.seek(0)
    
    filename = os.path.splitext(image_file.name)[0] + "_thumb.webp"
    return SimpleUploadedFile(filename, output_stream.read(), content_type="image/webp")


def calculate_blurhash(image_file):
    """
    Generates a Base85 BlurHash text string.
    Downsamples the target image to 100x100 first to prevent CPU spikes.
    Includes dynamic package loading to prevent runtime crashes if blurhash-python is missing.
    """
    default_placeholder = "LEHV6nWB2yk8pyo0adR*.7kCMdnj"  # Clean fallback gray hash
    try:
        import blurhash
    except ImportError:
        # Graceful fallback: run `pip install blurhash-python` to activate
        return default_placeholder

    try:
        image_file.seek(0)
        img = PILImage.open(image_file)
        img = exif_transpose(img)
        
        # Keep dimensions extremely small to guarantee O(1) performance speeds
        img.thumbnail((100, 100), PILImage.Resampling.LANCZOS)
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        return blurhash.encode(img, x_components=4, y_components=4)
    except Exception:
        return default_placeholder


# ─────────────────────────────────────────────────────────────
# SERIALIZERS
# ─────────────────────────────────────────────────────────────

class MediaAssetSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for displaying unified multi-tier media asset parameters.
    Dynamically resolves absolute URLs for original, display, thumbnail, 
    poster, and preview assets.
    """
    original_url = serializers.SerializerMethodField()
    display_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    poster_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = [
            'id',
            'media_type',
            'title',
            'original_name',
            'file_size',
            'order',
            'original_url',
            'display_url',
            'thumbnail_url',
            'blurhash',
            'width',
            'height',
            'stream_url',
            'poster_url',
            'preview_url',
            'duration',
            'processing_status',
            'created_at',
        ]
        read_only_fields = fields

    def get_original_url(self, obj):
        request = self.context.get('request')
        if obj.original_file and request:
            return request.build_absolute_uri(obj.original_file.url)
        return None

    def get_display_url(self, obj):
        request = self.context.get('request')
        if obj.display_file and request:
            return request.build_absolute_uri(obj.display_file.url)
        return None

    def get_thumbnail_url(self, obj):
        request = self.context.get('request')
        if obj.thumbnail_file and request:
            return request.build_absolute_uri(obj.thumbnail_file.url)
        return None

    def get_poster_url(self, obj):
        request = self.context.get('request')
        if obj.poster_image and request:
            return request.build_absolute_uri(obj.poster_image.url)
        return None

    def get_preview_url(self, obj):
        request = self.context.get('request')
        if obj.preview_file and request:
            return request.build_absolute_uri(obj.preview_file.url)
        return None


class MediaAssetImageUploadSerializer(serializers.ModelSerializer):
    """
    Handles secure multipart/form-data image uploads.
    Extracts DSLR orientation parameters, generates display WebPs, thumbnail WebPs,
    and BlurHash data entirely in memory.
    """
    # Exposing the input key as 'image' to keep David's frontend calling code identical
    image = serializers.ImageField(required=True, write_only=True)

    class Meta:
        model = MediaAsset
        fields = ['image', 'title']

    def validate_image(self, file):
        """Executes secure size-bound and Pillow binary header validations."""
        if file.size > MAX_FILE_SIZE_BYTES:
            size_mb = file.size / (1024 * 1024)
            raise serializers.ValidationError(
                f"File size too large ({size_mb:.1f} MB). Maximum allowed limit is 25 MB."
            )

        try:
            file.seek(0)
            with PILImage.open(file) as img:
                detected_format = img.format
                if not detected_format or detected_format.upper() not in ALLOWED_IMAGE_FORMATS:
                    raise serializers.ValidationError(
                        f"Unsupported image format: {detected_format}. Allowed formats are: {ALLOWED_FORMAT_NAMES}."
                    )
            file.seek(0)
        except (UnidentifiedImageError, ValueError):
            raise serializers.ValidationError("The uploaded file is not a valid or supported image.")
        except Exception:
            raise serializers.ValidationError("The image file appears to be corrupted or unreadable.")

        return file

    def create(self, validated_data):
        """
        Builds the model instance, automatically calling the in-memory WebP 
        and BlurHash generators before saving under the 'image' discriminator type.
        """
        gallery = validated_data.pop('gallery')
        image_file = validated_data['image']

        # 1. Lazily extract pixel dimensions with EXIF rotation compensation
        image_file.seek(0)
        with PILImage.open(image_file) as img:
            img = exif_transpose(img)
            width, height = img.size
        image_file.seek(0)

        # 2. Extract immutable system and original metadata
        file_size = image_file.size
        original_name = os.path.basename(image_file.name)
        
        title = validated_data.get('title', '').strip()
        if not title:
            title = os.path.splitext(original_name)[0]

        # 3. Generate optimized display and thumbnail variants in-memory
        display_file = generate_display_webp(image_file)
        thumbnail_file = generate_thumbnail_webp(image_file)
        blurhash_str = calculate_blurhash(image_file)

        # 4. Instantiate and write the final record to PostgreSQL
        asset = MediaAsset(
            gallery=gallery,
            media_type=MediaAsset.MediaType.IMAGE,
            original_file=image_file,
            display_file=display_file,
            thumbnail_file=thumbnail_file,
            blurhash=blurhash_str,
            width=width,
            height=height,
            file_size=file_size,
            original_name=original_name,
            title=title
        )
        asset.save()
        return asset

    def to_representation(self, instance):
        return MediaAssetSerializer(
            instance,
            context=self.context
        ).data