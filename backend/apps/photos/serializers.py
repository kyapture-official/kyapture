# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/serializers.py
import io
import os
from PIL import Image as PILImage, UnidentifiedImageError
from PIL.ImageOps import exif_transpose
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers

from apps.core.utils import validate_magic_bytes, strip_exif_gps, process_image_pipeline, validate_video_magic_bytes
from .models import MediaAsset

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB Limit
ALLOWED_IMAGE_FORMATS = {'JPEG', 'JPG', 'PNG', 'WEBP', 'TIFF'}
ALLOWED_FORMAT_NAMES = 'JPEG, JPG, PNG, WEBP, TIFF'

# Technical safety ceiling only — protects multipart parsing / temp-disk
# spooling during FFmpeg processing. This is NOT a duration or quality
# restriction; per product decision, storage quota (checked in the view,
# before this serializer runs) is the only real gate on video uploads.
MAX_VIDEO_FILE_SIZE_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v'}
ALLOWED_VIDEO_FORMAT_NAMES = 'MP4, MOV, M4V'



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
    Validates secure multipart/form-data image uploads.

    NOTE: Intentionally has no create() method. PhotoListUploadView validates 
    via .is_valid() and then constructs the MediaAsset row directly to ensure 
    consistent handling of pipeline processing, watermarking, and status flags.
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

    def to_representation(self, instance):
        return MediaAssetSerializer(
            instance,
            context=self.context
        ).data

class MediaAssetVideoUploadSerializer(serializers.ModelSerializer):
    """
    Validates secure multipart/form-data video uploads.

    Deliberately enforces NO duration or resolution/quality limit — video
    length and quality are gated ONLY by the photographer's subscription
    storage quota (checked in the view, before this serializer ever runs).
    MAX_VIDEO_FILE_SIZE_BYTES above is a technical ceiling, not a business
    rule — see its comment.

    NOTE: like MediaAssetImageUploadSerializer, this intentionally has no
    create() method. PhotoListUploadView validates via .is_valid() and
    then constructs the MediaAsset row directly — mirroring the existing
    (if slightly duplicative) pattern already used for image uploads,
    rather than introducing a second, inconsistent convention.
    """
    video = serializers.FileField(required=True, write_only=True)

    class Meta:
        model = MediaAsset
        fields = ['video', 'title']

    def validate_video(self, file):
        if file.size > MAX_VIDEO_FILE_SIZE_BYTES:
            size_mb = file.size / (1024 * 1024)
            limit_mb = MAX_VIDEO_FILE_SIZE_BYTES / (1024 * 1024)
            raise serializers.ValidationError(
                f"File too large ({size_mb:.0f} MB). This exceeds the {limit_mb:.0f} MB technical "
                "upload ceiling for a single file — unrelated to your plan's storage quota."
            )

        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported video format: {ext or 'unknown'}. Allowed formats are: {ALLOWED_VIDEO_FORMAT_NAMES}."
            )

        validate_video_magic_bytes(file)
        return file

    def to_representation(self, instance):
        return MediaAssetSerializer(instance, context=self.context).data
    
class PhotoBulkDeleteSerializer(serializers.Serializer):
    """
    Validates a batch of MediaAsset UUID primary keys for bulk deletion.
    Gallery owner scoping and database writes are handled inside the view.
    """
    photo_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        min_length=1
    )


class PhotoReorderSerializer(serializers.Serializer):
    """
    Validates the complete reordered sequence of MediaAsset UUID primary keys 
    associated with a single gallery.
    """
    ordered_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        min_length=1
    )