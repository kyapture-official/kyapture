import os
from PIL import Image as PILImage, UnidentifiedImageError
from rest_framework import serializers

from apps.core.utils import generate_image_thumbnail
from .models import Photo

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB Limit [1.1.2]
ALLOWED_IMAGE_FORMATS = {'JPEG', 'JPG', 'PNG', 'WEBP', 'TIFF'}
ALLOWED_FORMAT_NAMES = 'JPEG, JPG, PNG, WEBP, TIFF'


class PhotoListSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for displaying photo metadata inside grids.
    Resolves full absolute URLs for both original image and WebP thumbnails [1.1.2].
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
    and generates optimized WebP thumbnails entirely in-memory [1.1.2].
    """
    image = serializers.ImageField(required=True)

    class Meta:
        model = Photo
        fields = ['image', 'title']

    def validate_image(self, file):
        """
        Executes strict three-layer binary file validation:
        1. Enforces strict maximum file size bounds to prevent RAM exhaustion [1.1.2].
        2. Inspects binary headers via Pillow to verify the file is a valid image.
        3. Enforces that the file matches allowed professional photography formats.
        """
        # Layer 1: File size verification [1.1.2]
        if file.size > MAX_FILE_SIZE_BYTES:
            size_mb = file.size / (1024 * 1024)
            raise serializers.ValidationError(
                f"File size too large ({size_mb:.1f} MB). Maximum allowed limit is 25 MB."
            )

        # Layer 2: Binary header verification using Pillow [1.1.2]
        try:
            file.seek(0)
            with PILImage.open(file) as img:
                # We extract format and size to verify the header parses cleanly
                detected_format = img.format
                width, height = img.size
                
                # Layer 3: Format restriction check [1.1.2]
                if not detected_format or detected_format.upper() not in ALLOWED_IMAGE_FORMATS:
                    raise serializers.ValidationError(
                        f"Unsupported image format: {detected_format}. Allowed formats are: {ALLOWED_FORMAT_NAMES}."
                    )
            file.seek(0)  # Reset pointer to start of stream [1.1.2]
        except (UnidentifiedImageError, ValueError):
            raise serializers.ValidationError("The uploaded file is not a valid or supported image.")
        except Exception:
            raise serializers.ValidationError("The image file appears to be corrupted or unreadable.")

        return file

    def create(self, validated_data):
        """
        1. Resolves parent gallery owner and request context.
        2. Lazily extracts width, height, and file metadata.
        3. Automatically processes and appends an optimized WebP thumbnail in-memory [1.1.2].
        4. Writes the final record to PostgreSQL.
        """
        gallery = validated_data.pop('gallery')
        image_file = validated_data['image']

        # 1. Lazily extract pixel dimensions [1.1.2]
        image_file.seek(0)
        with PILImage.open(image_file) as img:
            width, height = img.size
        image_file.seek(0)

        # 2. Extract immutable system and original metadata [1.1.2]
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

        # 4. Generate optimized WebP thumbnail on-the-fly inside our memory buffer [1.1.2]
        thumbnail_file = generate_image_thumbnail(image_file)
        if thumbnail_file:
            photo.thumbnail = thumbnail_file

        photo.save()
        return photo

    def to_representation(self, instance):
        """
        Maps the freshly created instance back into the complete PhotoListSerializer
        format, providing the client with the newly generated UUID and absolute media URLs [1.1.2].
        """
        return PhotoListSerializer(
            instance,
            context=self.context
        ).data