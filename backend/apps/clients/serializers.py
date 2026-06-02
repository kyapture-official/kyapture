from django.contrib.auth.hashers import check_password
from rest_framework import serializers

from apps.galleries.models import Gallery
from apps.photos.models import Photo
from apps.core.utils import generate_secure_token
from .models import ClientSession


class PublicPhotoSerializer(serializers.ModelSerializer):
    """
    Read-only. Returns highly optimized, web-safe image paths.
    Using ModelSerializer ensures relative S3 or local disk media paths 
    automatically resolve to full absolute URLs [1.1.2].
    """
    class Meta:
        model = Photo
        fields = ['id', 'image', 'thumbnail', 'width', 'height', 'title']
        read_only_fields = fields


class PublicGallerySerializer(serializers.ModelSerializer):
    """
    GET /api/v1/public/{slug}/
    Exposes only safe, public metadata fields for client viewing.
    """
    photographer_name = serializers.SerializerMethodField()
    photos = PublicPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Gallery
        fields = [
            'id', 'title', 'description', 'slug', 'branding_color',
            'photographer_name', 'allow_download', 'watermark_enabled',
            'is_password_protected', 'photos',
        ]
        read_only_fields = fields

    def get_photographer_name(self, obj):
        """Falls back to username if display_name is empty or null [1.1.2]."""
        return obj.photographer.display_name or obj.photographer.username


class GalleryUnlockSerializer(serializers.Serializer):
    """
    Processes client password unlocking.
    Validates credentials in validate() and handles database state mutation 
    strictly inside create() to respect DRF transaction boundaries [1.1.2].
    """
    password = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(required=False, allow_blank=True, default='')

    def validate(self, data):
        """Verifies the gallery password against the database hash securely [1.1.2]."""
        gallery = self.context.get('gallery')
        password = data.get('password')

        if not gallery:
            raise serializers.ValidationError({"detail": "Gallery context is missing."})

        if not gallery.is_password_protected:
            raise serializers.ValidationError({"detail": "This gallery is not password protected."})

        # Constant-time password validation
        if not check_password(password, gallery.password_hash):
            raise serializers.ValidationError({"password": "Incorrect password."})

        return data

    def create(self, validated_data):
        """Executes the ClientSession database write only after validation passes [1.1.2]."""
        gallery = self.context.get('gallery')
        request = self.context.get('request')
        email = validated_data.get('email', '').strip() or None
        
        # Extract IP and generate high-entropy token [1.1.2]
        ip_address = self._get_client_ip(request)
        access_token = generate_secure_token()

        # Database transaction boundary respected [1.1.2]
        return ClientSession.objects.create(
            gallery=gallery,
            email=email,
            access_token=access_token,
            ip_address=ip_address,
            has_download_access=gallery.allow_download
        )

    def _get_client_ip(self, request):
        """Extracts real client IP addressing, bypassing reverse proxy sandboxes."""
        if not request:
            return None
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    def to_representation(self, instance):
        """Returns the secure token payload immediately after successful database save [1.1.2]."""
        return {
            'access_token': instance.access_token,
            'has_download_access': instance.has_download_access
        }