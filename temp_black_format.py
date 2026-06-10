# C:\Users\LENOVO\Desktop\kyapture\backend\apps\galleries\serializers.py

from django.contrib.auth.hashers import make_password
from rest_framework import serializers

# Integrated get_user_subscription_metrics and raise_gating_violation for resource gating
from apps.core.utils import (
    generate_unique_slug, 
    get_user_subscription_metrics, 
    raise_gating_violation
)
from apps.photos.models import Photo
from .models import Gallery


class CoverPhotoSerializer(serializers.ModelSerializer):
    """Read-only. Returns highly compact cover photo metadata."""
    class Meta:
        model = Photo
        fields = ['id', 'image', 'width', 'height']
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

    class Meta:
        model = Gallery
        fields = [
            'id', 'title', 'slug', 'branding_color', 
            'cover_url', 'photo_count', 'is_downloadable', 
            'is_active', 'is_published', 'has_password', 
            'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_cover_url(self, obj):
        """Returns the absolute URL of the cover photo"""
        request = self.context.get('request')
        if obj.cover_photo and request:
            return request.build_absolute_uri(obj.cover_photo.image.url)
        return None

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

    class Meta:
        model = Gallery
        fields = [
            'id', 'title', 'slug', 'description', 'branding_color', 
            'cover_url', 'photo_count', 'is_downloadable', 
            'is_active', 'is_published', 'has_password', 
            'password_hash', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']
        extra_kwargs = {
            'password_hash': {'write_only': True},
        }

    def get_cover_url(self, obj):
        request = self.context.get('request')
        if obj.cover_photo and request:
            return request.build_absolute_uri(obj.cover_photo.image.url)
        return None

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

    class Meta:
        model = Gallery
        fields = [
            'title', 'description', 'branding_color',
            'is_password_protected', 'password',
            'is_downloadable', 'watermark_enabled',
            'is_published', 'expires_at',
        ]

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

        # ─── SUBSCRIPTION RESOURCE GATING ───
        # Evaluate user's limits and usage before any DB write
        metrics = get_user_subscription_metrics(photographer)
        
        if metrics["current_galleries_count"] >= metrics["max_galleries"]:
            raise_gating_violation(
                message=f"Gallery creation limit reached. Your active plan ({metrics['plan_name']}) restricts you to a maximum of {metrics['max_galleries']} galleries.",
                code="gallery_limit_reached"
            )

        raw_password = validated_data.pop('password', '').strip()

        slug = generate_unique_slug(
            Gallery,
            validated_data['title'],
            photographer=photographer
        )

        password_hash = make_password(raw_password) if raw_password else None

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
        queryset=Photo.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Gallery
        fields = [
            'title', 'description', 'cover_photo',
            'branding_color', 'is_password_protected', 'password',
            'is_downloadable', 'watermark_enabled', 'is_published', 'expires_at',
        ]

    def validate_branding_color(self, value):
        import re
        if value and not re.match(r'^#[0-9a-fA-F]{6}$', value):
            raise serializers.ValidationError('Color must be a valid hex code (e.g., #FF5733).')
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
        raw_password = validated_data.pop('password', '').strip()

        if raw_password:
            instance.password_hash = make_password(raw_password)
        elif not validated_data.get('is_password_protected', instance.is_password_protected):
            instance.password_hash = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

    def to_representation(self, instance):
        # Fallback counting evaluation for updates
        instance.photo_count = instance.photos.count()
        return GalleryDetailSerializer(instance, context=self.context).data