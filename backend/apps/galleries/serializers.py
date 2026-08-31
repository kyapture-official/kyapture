# C:/Users/LENOVO/Desktop/kyapture/backend/apps/galleries/serializers.py
import bcrypt 
from rest_framework import serializers

from apps.core.utils import generate_unique_slug, sanitize_text
from apps.photos.models import MediaAsset
from .models import Gallery

RESERVED_GALLERY_SLUGS = {
    'search', 'dashboard', 'stats',
    'publish', 'set-password',
    'unlock', 'download', 'video', 'photo', 'stream',
}

class CoverPhotoSerializer(serializers.ModelSerializer):
    """Read-only. Returns highly compact cover photo metadata."""
    class Meta:
        model = MediaAsset
        fields = ['id', 'thumbnail_file', 'width', 'height']
        read_only_fields = fields


class GalleryListSerializer(serializers.ModelSerializer):
    """
    GET /api/v1/galleries/
    Returns an optimized, lightweight array of galleries.
    Bridges backend schema with David's expected frontend keys cleanly
    """
    cover_url = serializers.SerializerMethodField()
    photo_count = serializers.IntegerField(read_only=True)
    is_downloadable = serializers.BooleanField(source='allow_download', read_only=True)
    has_password = serializers.SerializerMethodField()
    
    # NEW: Scoped photographer metadata mappings
    owner_username = serializers.CharField(source='photographer.username', read_only=True)
    photographer_username = serializers.CharField(source='photographer.username', read_only=True)
    class Meta:
        model = Gallery
        fields = [
            'id', 'title', 'slug', 'branding_color', 
            'cover_url', 'photo_count', 'is_downloadable', 
            'is_active', 'event_date', 'expires_at', 'is_published', 'has_password', 
            'owner_username', 'photographer_username',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_cover_url(self, obj):
        """Returns the absolute URL of the cover's thumbnail-scale image.
        Falls back to poster_image when the cover is a video — videos have
        no thumbnail_file of their own (only images get a small WebP grid
        thumbnail generated)."""
        
        request = self.context.get('request')
        cover = obj.cover_photo
        if not cover or not request:
            return None
        image_field = (
            cover.thumbnail_file
            if cover.media_type == MediaAsset.MediaType.IMAGE
            else cover.poster_image
        )
        if not image_field:
            return None
        return request.build_absolute_uri(image_field.url)

    def get_has_password(self, obj):
        """Converts password_hash existence into a clean boolean flag."""
        return bool(obj.password_hash)


class GalleryDetailSerializer(serializers.ModelSerializer):
    """
    GET /api/v1/galleries/{slug}/
    Returns complete gallery settings. Protects password hash.
    """
    cover_url = serializers.SerializerMethodField()
    photo_count = serializers.IntegerField(read_only=True)
    is_downloadable = serializers.BooleanField(source='allow_download', read_only=True)
    has_password = serializers.SerializerMethodField()
    
    # NEW: Scoped photographer metadata mappings
    owner_username = serializers.CharField(source='photographer.username', read_only=True)
    photographer_username = serializers.CharField(source='photographer.username', read_only=True)
    class Meta:
        model = Gallery
        fields = [
            'id', 'title', 'slug', 'description', 'branding_color', 
            'cover_url', 'photo_count', 'is_downloadable', 
            'is_active', 'event_date', 'expires_at', 'is_published', 'has_password', 
            'owner_username', 'photographer_username',
            'watermark_enabled',
            'password_hash', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']
        extra_kwargs = {
            'password_hash': {'write_only': True},
        }

    def get_cover_url(self, obj):
        request = self.context.get('request')
        cover = obj.cover_photo
        if not cover or not request:
            return None
        image_field = (
            cover.display_file
            if cover.media_type == MediaAsset.MediaType.IMAGE
            else cover.poster_image
        )
        if not image_field:
            return None
        return request.build_absolute_uri(image_field.url)

    def get_has_password(self, obj):
        return bool(obj.password_hash)


class GalleryCreateSerializer(serializers.ModelSerializer):
    """POST /api/v1/galleries/"""
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default=''
    )
    is_downloadable = serializers.BooleanField(source='allow_download', required=False, default=False)
    
    event_date = serializers.DateField(required=False, allow_null=True)
    expires_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        input_formats=['iso-8601', '%Y-%m-%d'],
    )

    class Meta:
        model = Gallery
        fields = [
            'title', 'description', 'branding_color',
            'is_password_protected', 'password',
            'is_downloadable', 'watermark_enabled',
            'is_published', 'expires_at', 'event_date',
        ]

    def validate_title(self, value):
        """Strips raw HTML/JS tags to defend against persistent XSS."""
        return sanitize_text(value)

    def validate_description(self, value):
        """Strips raw HTML/JS tags to defend against persistent XSS."""
        return sanitize_text(value)

    def validate_branding_color(self, value):
        import re
        if value and not re.match(r'^#[0-9a-fA-F]{6}$', value):
            raise serializers.ValidationError('Color must be a valid hex code (e.g., #FF5733).')
        return value

    def validate(self, data):
        is_protected = data.get('is_password_protected', False)
        password = data.get('password', '').strip()

        if is_protected and not password:
            raise serializers.ValidationError({
                'password': 'A password is required when gallery is protected.'
            })
        if not is_protected:
            data['password'] = ''
        return data

    def create(self, validated_data):
        photographer = self.context['request'].user
        raw_password = validated_data.pop('password', '').strip()

        slug = generate_unique_slug(
            Gallery,
            validated_data['title'],
            reserved_words=RESERVED_GALLERY_SLUGS,
            photographer=photographer
        )

        password_hash = (
            bcrypt.hashpw(raw_password.encode(), bcrypt.gensalt()).decode()
            if raw_password 
            else None
        )

        return Gallery.objects.create(
            photographer=photographer,
            slug=slug,
            password_hash=password_hash,
            **validated_data
        )

    def to_representation(self, instance):
        # Set annotated fallback to prevent NameErrors on fresh instance returns 
        instance.photo_count = 0
        return GalleryDetailSerializer(instance, context=self.context).data


class GalleryUpdateSerializer(serializers.ModelSerializer):
    """PUT /api/v1/galleries/{slug}/"""
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default=''
    )
    is_downloadable = serializers.BooleanField(source='allow_download', required=False)
    cover_photo = serializers.PrimaryKeyRelatedField(
        queryset=MediaAsset.objects.all(),
        required=False,
        allow_null=True
    )
    
    # Explicit rather than left to ModelSerializer's auto-generation — the
    # null/optional contract for these two should be visible here, not
    # inferred from the model's null=True/blank=True by a future reader.
    event_date = serializers.DateField(required=False, allow_null=True)
    expires_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        # A bare "YYYY-MM-DD" (what <input type="date"> sends) fails DRF's
        # default iso-8601-only DateTimeField parsing — parse_datetime()
        # requires a time component. Accepting '%Y-%m-%d' too resolves a
        # bare date to midnight of that day, matching what the picker sends.
        input_formats=['iso-8601', '%Y-%m-%d'],
    )

    class Meta:
        model = Gallery
        fields = [
            'title', 'description', 'cover_photo',
            'branding_color','event_date', 'is_password_protected', 'password',
            'is_downloadable', 'watermark_enabled', 'is_published', 'expires_at',
        ]

    def validate_title(self, value):
        """Strips raw HTML/JS tags to defend against persistent XSS."""
        return sanitize_text(value)

    def validate_description(self, value):
        """Strips raw HTML/JS tags to defend against persistent XSS."""
        return sanitize_text(value)

    def validate_branding_color(self, value):
        import re
        if value and not re.match(r'^#[0-9a-fA-F]{6}$', value):
            raise serializers.ValidationError('Color must be a valid hex code (e.g., #FF5733).')
        return value


    def validate_cover_photo(self, value):
        request = self.context.get('request')
        # Check if the photo belongs to the current user's gallery
        if value is not None and request and value.gallery.photographer_id != request.user.id:
            raise serializers.ValidationError(
                "You can only set a photo from one of your own galleries as the cover."
            )
        return value

    def validate(self, data):
        is_protected = data.get('is_password_protected', self.instance.is_password_protected)
        password = data.get('password', '').strip()
        if is_protected and not password:
            if not self.instance.password_hash:
                raise serializers.ValidationError({
                    'password': 'A password is required when enabling gallery protection.'
                })
        return data

    def update(self, instance, validated_data):
        """
        Updates the gallery instance safely. If a new password is submitted,
        hashes it using raw bcrypt. If the title actually changed, regenerates
        the slug — scoped per-photographer and checked against
        RESERVED_GALLERY_SLUGS, the same way GalleryCreateSerializer.create()
        does. exclude_pk=instance.pk is mandatory here: without it, the
        gallery's own current slug row counts as a self-collision.
        """
        raw_password = validated_data.pop('password', '').strip()

        if raw_password:
            instance.password_hash = bcrypt.hashpw(
                raw_password.encode('utf-8'), bcrypt.gensalt()
            ).decode('utf-8')
        elif not validated_data.get('is_password_protected', instance.is_password_protected):
            instance.password_hash = None

        new_title = validated_data.get('title')
        if new_title is not None and new_title != instance.title:
            instance.slug = generate_unique_slug(
                Gallery, new_title,
                reserved_words=RESERVED_GALLERY_SLUGS,
                exclude_pk=instance.pk,
                photographer=instance.photographer,
            )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

    def to_representation(self, instance):
        instance.photo_count = instance.assets.count()
        return GalleryDetailSerializer(instance, context=self.context).data