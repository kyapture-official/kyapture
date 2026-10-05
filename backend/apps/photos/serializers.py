# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/serializers.py
import io
import math
import os
from PIL import Image as PILImage, UnidentifiedImageError
from PIL.ImageOps import exif_transpose
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers
from apps.core.watermark import versioned_url

from apps.core.utils import (
    validate_magic_bytes,
    strip_exif_gps,
    process_image_pipeline,
    sanitize_text,
    validate_video_magic_bytes,
)
from .models import MediaAsset, PhotoSet

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
    medium_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    poster_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()
    playback_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = [
            'id',
            'media_type',
            'title',
            'original_name',
            'file_size',
            'order',
            'photo_set',
            'original_url',
            'display_url',
            'medium_url',
            'thumbnail_url',
            'blurhash',
            'width',
            'height',
            'stream_url',
            'poster_url',
            'preview_url',
            'playback_url',
            'duration',
            'processing_status',
            'is_favorite',
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
            return versioned_url(request.build_absolute_uri(obj.display_file.url), obj)
        return None

    def get_medium_url(self, obj):
        """1280px WebP tier — see MediaAsset.medium_file (Phase 2)."""
        request = self.context.get('request')
        if obj.medium_file and request:
            return versioned_url(request.build_absolute_uri(obj.medium_file.url), obj)
        return None

    def get_thumbnail_url(self, obj):
        request = self.context.get('request')
        if obj.thumbnail_file and request:
            return versioned_url(request.build_absolute_uri(obj.thumbnail_file.url), obj)
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

    def get_playback_url(self, obj):
        """
        Browser-compatible H.264/AAC MP4 derivative — see
        MediaAsset.playback_file (Phase 2). None until video processing
        completes; the dashboard preview can fall back to original_url
        in the meantime the same way it always could.
        """
        request = self.context.get('request')
        if obj.playback_file and request:
            return request.build_absolute_uri(obj.playback_file.url)
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


# ─────────────────────────────────────────────────────────────
# PHOTO SETS (Phase 3)
# ─────────────────────────────────────────────────────────────

class PhotoSetSerializer(serializers.ModelSerializer):
    """
    Photographer + public read shape for a PhotoSet. `photo_count` is
    always populated via annotation by the view (Count('assets')) —
    never computed here — so listing N sets costs one query total, not N.
    """
    photo_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = PhotoSet
        fields = ['id', 'name', 'description', 'order', 'photo_count']
        read_only_fields = ['id', 'order', 'photo_count']


class PhotoSetWriteSerializer(serializers.ModelSerializer):
    """Create/update. `gallery` is set by the view, never from the client."""
    class Meta:
        model = PhotoSet
        fields = ['name', 'description']

    def validate_name(self, value):
        value = sanitize_text(value).strip()
        if not value:
            raise serializers.ValidationError("Set name cannot be empty.")
        return value

    def validate_description(self, value):
        value = sanitize_text(value)
        if len(value) > 500:
            raise serializers.ValidationError("Description cannot exceed 500 characters.")
        return value


class PhotoSetReorderSerializer(serializers.Serializer):
    """Full ordered sequence of a gallery's PhotoSet UUIDs."""
    ordered_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        min_length=1
    )


class PhotoSetAssignSerializer(serializers.Serializer):
    """
    Moves a batch of MediaAssets into (or out of) a set in one call.
    `set_id: null` explicitly means "remove from any set" (unsorted) —
    distinct from omitting the field, which DRF would treat as a missing
    required key.
    """
    set_id = serializers.UUIDField(allow_null=True)
    photo_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        min_length=1
    )


# VID-C pre-flight limits: a drop of more than this many videos, or a single
# video longer than a day, is not a real browser answer.
MAX_PREFLIGHT_VIDEOS = 200
MAX_PREFLIGHT_SECONDS = 24 * 60 * 60


class _DurationSeconds(serializers.FloatField):
    """A positive, finite number of seconds (no booleans, NaN or Infinity)."""

    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail('invalid')
        value = super().to_internal_value(data)
        if not math.isfinite(value) or value <= 0:
            raise serializers.ValidationError('Duration must be a positive number of seconds.')
        if value > MAX_PREFLIGHT_SECONDS:
            raise serializers.ValidationError(f'Duration cannot exceed {MAX_PREFLIGHT_SECONDS} seconds.')
        return value


class VideoPreflightSerializer(serializers.Serializer):
    """
    What the browser read from the chosen videos before uploading: how many
    there are and the length of each one it could read. A video whose length
    the browser cannot read (unsupported codec) is counted but has no entry in
    `durations`, so `durations` may be shorter than `video_count`, never longer.
    """
    video_count = serializers.IntegerField(min_value=1, max_value=MAX_PREFLIGHT_VIDEOS)
    durations = serializers.ListField(
        child=_DurationSeconds(), allow_empty=True, max_length=MAX_PREFLIGHT_VIDEOS, required=False, default=list,
    )

    def validate(self, attrs):
        if len(attrs['durations']) > attrs['video_count']:
            raise serializers.ValidationError({'durations': 'More durations than videos.'})
        return attrs
