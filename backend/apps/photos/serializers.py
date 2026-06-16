import io
import os
from PIL import Image as PILImage, UnidentifiedImageError
from PIL.ImageOps import exif_transpose
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers

from apps.core.utils import validate_magic_bytes, strip_exif_gps, process_image_pipeline
from .models import MediaAsset

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB Limit
ALLOWED_IMAGE_FORMATS = {'JPEG', 'JPG', 'PNG', 'WEBP', 'TIFF'}
ALLOWED_FORMAT_NAMES = 'JPEG, JPG, PNG, WEBP, TIFF'



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
        # Layer 1: Enforce physical file size limits
        if file.size > MAX_FILE_SIZE_BYTES:
            size_mb = file.size / (1024 * 1024)
            raise serializers.ValidationError(
                f"File size too large ({size_mb:.1f} MB). Maximum allowed limit is 25 MB."
            )
        # Layer 2: Enforce strict magic byte file signature validation (Security)
        validate_magic_bytes(file)
        
        # Layer 3: Binary header verification using Pillow
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

        # Enforce strict EXIF GPS coordinate stripping (Privacy Protection)
        image_file = strip_exif_gps(image_file)
        
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

        # 3. Generate optimized display, thumbnail, and BlurHash variants in a single-pass in-memory pipeline
        display_file, thumbnail_file, blurhash_str = process_image_pipeline(image_file)

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