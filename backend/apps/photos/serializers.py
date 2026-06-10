import os
from PIL import Image as PILImage, UnidentifiedImageError
from rest_framework import serializers

# Import the core gating helpers
from apps.core.utils import (
    generate_image_thumbnail, 
    get_user_subscription_metrics, 
    raise_gating_violation
)
from .models import Photo

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB Limit
ALLOWED_IMAGE_FORMATS = {'JPEG', 'JPG', 'PNG', 'WEBP', 'TIFF'}
ALLOWED_FORMAT_NAMES = 'JPEG, JPG, PNG, WEBP, TIFF'


class PhotoListSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for displaying photo metadata inside grids.
    Resolves full absolute URLs for both original image and WebP thumbnails.
    """
    class Meta:
        model = Photo
        fields = [
            'id',
            'title',
            'image',
            'thumbnail',
            'width',
            'height',
            'file_size',
            'order',
            'original_name',
            'created_at',
        ]
        read_only_fields = fields


class PhotoUploadSerializer(serializers.ModelSerializer):
    """
    Handles secure multipart/form-data single and bulk photo uploads.
    Extracts image width/height headers, enforces size/type constraints,
    and generates optimized WebP thumbnails entirely in-memory.
    """
    image = serializers.ImageField(required=True)

    class Meta:
        model = Photo
        fields = ['image', 'title']

    def validate_image(self, file):
        """
        Executes strict three-layer binary file validation:
        1. Enforces strict maximum file size bounds to prevent RAM exhaustion.
        2. Inspects binary headers via Pillow to verify the file is a valid image.
        3. Enforces that the file matches allowed professional photography formats.
        """
        # Layer 1: File size verification 
        if file.size > MAX_FILE_SIZE_BYTES:
            size_mb = file.size / (1024 * 1024)
            raise serializers.ValidationError(
                f"File size too large ({size_mb:.1f} MB). Maximum allowed limit is 25 MB."
            )

        # Layer 2: Binary header verification using Pillow 
        try:
            file.seek(0)
            with PILImage.open(file) as img:
                # We extract format and size to verify the header parses cleanly
                detected_format = img.format
                
                # Layer 3: Format restriction check 
                if not detected_format or detected_format.upper() not in ALLOWED_IMAGE_FORMATS:
                    raise serializers.ValidationError(
                        f"Unsupported image format: {detected_format}. Allowed formats are: {ALLOWED_FORMAT_NAMES}."
                    )
            file.seek(0)  # Reset pointer to start of stream 
        except (UnidentifiedImageError, ValueError):
            raise serializers.ValidationError("The uploaded file is not a valid or supported image.")
        except Exception:
            raise serializers.ValidationError("The image file appears to be corrupted or unreadable.")

        return file

    def create(self, validated_data):
        """
        1. Resolves parent gallery owner and request context.
        2. Gates request against active subscription limits (Photo Count & Storage Footprint).
        3. Lazily extracts width, height, and file metadata.
        4. Automatically processes and appends an optimized WebP thumbnail in-memory.
        5. Writes the final record to PostgreSQL.
        """
        gallery = validated_data.pop('gallery')
        image_file = validated_data['image']
        photographer = gallery.photographer

        # ─── SUBSCRIPTION RESOURCE GATING ───
        metrics = get_user_subscription_metrics(photographer)

        # Gating Check 1: Maximum Photos per Gallery
        current_photos_in_gallery = Photo.objects.filter(gallery=gallery).count()
        if current_photos_in_gallery >= metrics["max_photos_per_gallery"]:
            raise_gating_violation(
                message=f"Photo upload limit reached. Your active plan limits you to a maximum of {metrics['max_photos_per_gallery']} photos per gallery.",
                code="photo_limit_reached"
            )

        # Gating Check 2: Total Cumulative Storage Limit (Bytes)
        incoming_file_size = image_file.size
        projected_storage_bytes = metrics["current_total_storage_bytes"] + incoming_file_size
        if projected_storage_bytes > metrics["storage_bytes_limit"]:
            allowed_gb = metrics["storage_bytes_limit"] / (1024 ** 3)
            raise_gating_violation(
                message=f"Storage quota exceeded. This upload of {incoming_file_size / (1024*1024):.1f} MB exceeds your active plan's cumulative storage limit of {allowed_gb:.1f} GB.",
                code="storage_limit_reached"
            )

        # 1. Lazily extract pixel dimensions 
        image_file.seek(0)
        with PILImage.open(image_file) as img:
            width, height = img.size
        image_file.seek(0)

        # 2. Extract immutable system and original metadata 
        file_size = image_file.size
        original_name = os.path.basename(image_file.name)
        
        title = validated_data.get('title', '').strip()
        if not title:
            title = os.path.splitext(original_name)[0]

        # 3. Instantiate the Photo record
        photo = Photo(
            gallery=gallery,
            width=width,
            height=height,
            file_size=file_size,
            original_name=original_name,
            title=title,
            image=image_file
        )

        # 4. Generate optimized WebP thumbnail on-the-fly inside our memory buffer 
        thumbnail_file = generate_image_thumbnail(image_file)
        if thumbnail_file:
            photo.thumbnail = thumbnail_file

        photo.save()
        return photo

    def to_representation(self, instance):
        """
        Maps the freshly created instance back into the complete PhotoListSerializer
        format, providing the client with the newly generated UUID and absolute media URLs.
        """
        return PhotoListSerializer(
            instance,
            context=self.context
        ).data