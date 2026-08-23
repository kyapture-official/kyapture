# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/serializers.py
import bcrypt
from rest_framework import serializers

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset
from apps.core.utils import generate_secure_token
from .models import ClientSession
from django.urls import reverse


class PublicMediaAssetSerializer(serializers.ModelSerializer):
    """
    Read-only. Returns highly optimized, web-safe image and video paths.
    Allows public clients to browse unified gallery streams cleanly.
    """
    display_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    poster_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    playback_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = [
            'id', 
            'media_type', 
            'title', 
            'original_name',
            'display_url', 
            'thumbnail_url', 
            'blurhash', 
            'width', 
            'height', 
            'stream_url', 
            'poster_url', 
            'preview_url', 
            'duration',
            'playback_url',
            'download_url',
        ]
        read_only_fields = fields

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

    def get_download_url(self, obj):
        """
        Points to PublicPhotoDownloadView, NOT a raw file URL — see that
        view's docstring for why. Returns None (frontend hides the button)
        unless the photographer has downloads enabled for this gallery.

        Reads 'gallery' from context rather than obj.gallery to avoid an
        N+1 query per photo — the view already has the gallery instance
        loaded once and passes it in explicitly.
        """
        request = self.context.get('request')
        gallery = self.context.get('gallery')
        if not request or not gallery or not gallery.allow_download:
            return None
        if not obj.original_file:
            return None

        from django.urls import reverse
        path = reverse('public-photo-download', kwargs={
            'username': gallery.photographer.username,
            'slug': gallery.slug,
            'photo_id': obj.id,
        })
        # No ?token= appended here on purpose — the frontend attaches it
        # from the client session store, same convention clientsApi.getGallery()
        # already uses for the main gallery fetch.
        return request.build_absolute_uri(path)
    
    def get_playback_url(self, obj):
        """
        Absolute URL to PublicVideoStreamView — the endpoint that serves
        the actual playable video (original_url isn't exposed on this
        serializer at all; see that view's docstring). None for images.

        Deliberately does NOT append the gallery's unlock token — this
        serializer has no reliable way to know it (it's held client-side
        only, never persisted server-side). The frontend appends
        '?token=...' itself for password-protected galleries, the same
        way it already does for the initial gallery fetch.
        """
        if obj.media_type != MediaAsset.MediaType.VIDEO:
            return None
        request = self.context.get('request')
        username = self.context.get('username')
        slug = self.context.get('slug')
        if not request or not username or not slug:
            return None
        url = reverse(
            'public-video-stream',
            kwargs={'username': username, 'slug': slug, 'asset_id': obj.id}
        )
        return request.build_absolute_uri(url)


class PublicGallerySerializer(serializers.ModelSerializer):
    """
    GET /api/v1/public/{username}/{slug}/
    Exposes only safe, public metadata fields for client viewing.
    """
    photographer_name = serializers.SerializerMethodField()
    photographer_logo = serializers.SerializerMethodField()
    # Alias: maps the unified 'assets' relationship back to the 'photos' key for David's React app
    photos = PublicMediaAssetSerializer(source='assets', many=True, read_only=True)

    class Meta:
        model = Gallery
        fields = [
            'id', 'title', 'description', 'slug', 'branding_color',
            'photographer_name', 'photographer_logo', 'allow_download', 'watermark_enabled',
            'is_password_protected', 'photos',
        ]
        read_only_fields = fields

    def get_photographer_name(self, obj):
        """Falls back to username if display_name is empty or null."""
        return obj.photographer.display_name or obj.photographer.username
    
    
    def get_photographer_logo(self, obj):
        request = self.context.get('request')
        if obj.photographer.logo and request:
            return request.build_absolute_uri(obj.photographer.logo.url)
        return None


class GalleryUnlockSerializer(serializers.Serializer):
    """
    Processes client password unlocking.
    Validates credentials in validate() and handles database state mutation 
    strictly inside create() to respect DRF transaction boundaries.
    """
    password = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(required=False, allow_blank=True, default='')

    def validate(self, data):
        """Verifies the gallery password against the database hash securely."""
        gallery = self.context.get('gallery')
        password = data.get('password')

        if not gallery:
            raise serializers.ValidationError({"detail": "Gallery context is missing."})

        if not gallery.is_password_protected:
            raise serializers.ValidationError({"detail": "This gallery is not password protected."})

        # Constant-time password validation
        is_valid = False
        if gallery.password_hash:
            try:
                # Enforce strict UTF-8 byte encoding on both payload and database hash
                is_valid = bcrypt.checkpw(
                    password.encode('utf-8'), 
                    gallery.password_hash.encode('utf-8')
                )
            except Exception:
                pass

        if not is_valid:
            raise serializers.ValidationError({"password": "Incorrect password."})

        return data

    def create(self, validated_data):
        """Executes the ClientSession database write only after validation passes."""
        gallery = self.context.get('gallery')
        request = self.context.get('request')
        email = validated_data.get('email', '').strip() or None
        
        # Extract IP and generate high-entropy token
        ip_address = self._get_client_ip(request)
        access_token = generate_secure_token()

        # Database transaction boundary respected
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
        """Returns the secure token payload immediately after successful database save."""
        return {
            'access_token': instance.access_token,
            'has_download_access': instance.has_download_access
        }