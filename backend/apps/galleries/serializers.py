from django.contrib.auth.hashers import make_password
from rest_framework import serializers

from apps.core.utils import generate_unique_slug
from apps.photos.models import Photo
from .models import Gallery


class CoverPhotoSerializer(serializers.ModelSerializer):
    """
    Read-only. Returns highly compact cover photo metadata 
    required for frontend grid aspect-ratio calculations [1.1.2].
    """
    class Meta:
        model = Photo
        fields = ['id', 'image', 'width', 'height']
        read_only_fields = fields


class GalleryListSerializer(serializers.ModelSerializer):
    """
    GET /api/v1/galleries/
    Returns an optimized, lightweight array of galleries.
    photo_count is annotated at the DB query level to prevent N+1 loops [1.1.2].
    """
    cover_photo = CoverPhotoSerializer(read_only=True)
    photo_count = serializers.IntegerField(read_only=True)  # Populated via SQL annotation [1.1.2]

    class Meta:
        model = Gallery
        fields = [
            'id', 'title', 'slug',
            'cover_photo', 'photo_count',
            'is_published', 'allow_download',
            'is_password_protected',
            'branding_color', 'created_at',
        ]
        read_only_fields = fields


class GalleryDetailSerializer(serializers.ModelSerializer):
    """
    GET /api/v1/galleries/{slug}/
    Returns complete gallery settings. Protects password hash [1.1.2].
    """
    cover_photo = CoverPhotoSerializer(read_only=True)
    photo_count = serializers.IntegerField(read_only=True)
    photographer = serializers.UUIDField(source='photographer.id', read_only=True)

    class Meta:
        model = Gallery
        fields = [
            'id', 'photographer', 'title', 'slug',
            'description', 'cover_photo', 'photo_count',
            'branding_color', 'is_password_protected',
            'password_hash', 'allow_download', 'watermark_enabled',
            'is_published', 'expires_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'photographer', 'slug', 'created_at', 'updated_at']
        extra_kwargs = {
            'password_hash': {'write_only': True},
        }


class GalleryCreateSerializer(serializers.ModelSerializer):
    """
    POST /api/v1/galleries/
    Auto-generates unique photographer-scoped slugs on creation [1.1.2, 1.2.7].
    """
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default=''
    )

    class Meta:
        model = Gallery
        fields = [
            'title', 'description', 'branding_color',
            'is_password_protected', 'password',
            'allow_download', 'watermark_enabled',
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
        raw_password = validated_data.pop('password', '').strip()

        # Generate unique slug scoped strictly to this photographer [1.1.2, 1.2.7]
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
        # Return full annotated details immediately after creation [1.1.2]
        return GalleryDetailSerializer(instance, context=self.context).data


class GalleryUpdateSerializer(serializers.ModelSerializer):
    """
    PUT /api/v1/galleries/{slug}/
    Permits cover photo updates while keeping slug immutable.
    """
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default=''
    )
    # Allows setting or updating the cover photo safely [1.1.2]
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
            'allow_download', 'watermark_enabled', 'is_published', 'expires_at',
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
        return GalleryDetailSerializer(instance, context=self.context).data