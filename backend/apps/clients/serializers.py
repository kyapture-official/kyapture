# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/serializers.py
import bcrypt
from rest_framework import serializers
from apps.core.share import build_gallery_share_url
from apps.core.watermark import versioned_url
from apps.core.typography import resolve_typography
from apps.users.collection_defaults import DESIGN_CHOICES, validate_presentation

from apps.galleries.models import Gallery
from apps.photos.models import MediaAsset, PhotoSet
from apps.subscriptions.entitlements import BRANDING, has_feature
from .models import ClientSession, Favorite, DownloadLog
from apps.core.request_ip import client_ip
from .download_access import download_pin_enforced, get_download_policy
from django.urls import reverse


class PublicPhotoSetSerializer(serializers.ModelSerializer):
    """
    Client-facing set tab metadata: id, name, and how many READY assets
    it contains. `photo_count` is annotated by the view (Count of READY
    assets only — a set showing "12" that's actually still processing
    would be a confusing tab label), never computed here.
    """
    photo_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = PhotoSet
        fields = ['id', 'name', 'photo_count']
        read_only_fields = fields


class PublicMediaAssetSerializer(serializers.ModelSerializer):
    """
    Read-only. Returns highly optimized, web-safe image and video paths.
    Allows public clients to browse unified gallery streams cleanly.
    """
    display_url = serializers.SerializerMethodField()
    medium_url = serializers.SerializerMethodField()
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
            'medium_url',
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
            return versioned_url(request.build_absolute_uri(obj.display_file.url), obj)
        return None

    def get_medium_url(self, obj):
        """
        1280px WebP tier — the srcset middle rung for typical in-page
        grid-column widths (the frontend builds `srcset`/`sizes` from
        thumbnail_url/medium_url/display_url; see PublicMasonryGrid.jsx).
        """
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
    Exposes only safe, public metadata fields for client viewing — the
    fields the MVP client gallery page actually renders (cover/hero,
    event date, download gating, password gate, photo grid, design
    settings). Nothing photographer-only (no internal ids beyond the
    gallery's own, no password_hash, no owner account details) is ever
    included here.

    Phase 2 (large-gallery performance): 'photos' is now only the FIRST
    PAGE of READY assets (GalleryMediaPagination.page_size, currently
    60) instead of the gallery's entire asset list embedded in one
    response — a 2000-photo gallery no longer means a 2000-entry JSON
    array (and 2000 signed/URL-built entries) on every single gallery
    load. The view (PublicGalleryView) queries that first page itself
    and passes it in via context['photos_page'] alongside the total
    READY count, so this serializer never re-queries or re-paginates —
    it only renders what it's handed. Further pages are fetched by the
    frontend from PublicGalleryPhotosView as the client scrolls.
    """
    photographer_name = serializers.SerializerMethodField()
    photographer_logo = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    cover_medium_url = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    photos_count = serializers.SerializerMethodField()
    photos_has_more = serializers.SerializerMethodField()
    photos_page_size = serializers.SerializerMethodField()
    photo_sets = serializers.SerializerMethodField()
    has_download_pin = serializers.SerializerMethodField()
    download_policy = serializers.SerializerMethodField()
    design_settings = serializers.SerializerMethodField()
    typography_style = serializers.SerializerMethodField()
    share_url = serializers.SerializerMethodField()

    class Meta:
        model = Gallery
        fields = [
            'id', 'title', 'description', 'slug', 'branding_color', 'share_url',
            'cover_url', 'cover_medium_url', 'event_date', 'design_settings', 'typography_style',
            'photographer_name', 'photographer_logo', 'allow_download', 'watermark_enabled',
            'is_password_protected', 'has_download_pin', 'download_policy',
            'photos', 'photos_count', 'photos_has_more', 'photos_page_size',
            'photo_sets',
        ]
        read_only_fields = fields

    def get_photo_sets(self, obj):
        """
        Reads context['photo_sets'] the same way get_photos() reads
        context['photos_page'] — the view queries+annotates this ONCE
        (Count of READY assets per set) and hands it in, so this
        serializer never issues its own query. Falls back to an empty
        list if a caller ever instantiates this serializer without that
        context, same defensive convention as get_photos().
        """
        photo_sets = self.context.get('photo_sets')
        if photo_sets is None:
            return []
        return PublicPhotoSetSerializer(photo_sets, many=True, context=self.context).data

    def get_has_download_pin(self, obj):
        return download_pin_enforced(obj)

    def get_download_policy(self, obj):
        return get_download_policy(obj)

    def get_photos(self, obj):
        """
        Renders whichever page of READY assets the view already fetched
        (context['photos_page'] — a plain list, not a queryset: the view
        builds it with an explicit LIMIT via GalleryMediaPagination, so
        there is no unbounded query hiding behind this field). Falls back
        to an empty list — never re-queries obj.assets here — if a caller
        ever instantiates this serializer without that context, since a
        silent full-table fetch is exactly the giant-payload regression
        this change exists to prevent.
        """
        photos_page = self.context.get('photos_page')
        if photos_page is None:
            return []
        return PublicMediaAssetSerializer(photos_page, many=True, context=self.context).data

    def get_photos_count(self, obj):
        return self.context.get('photos_total_count', 0)

    def get_photos_has_more(self, obj):
        return bool(self.context.get('photos_has_more', False))

    def get_photos_page_size(self, obj):
        return self.context.get('photos_page_size', 0)

    def get_photographer_name(self, obj):
        """Falls back to username if display_name is empty or null."""
        return obj.photographer.display_name or obj.photographer.username
    
    
    def get_photographer_logo(self, obj):
        """
        The business logo is a Pro+ feature: shown to clients only while the
        photographer is CURRENTLY entitled, so a lapsed plan stops showing it
        without the file or setting being touched. The URL is the public
        media URL of the logo itself (see get_branding_logo_path) — never a
        private/original storage path.
        """
        request = self.context.get('request')
        if not (obj.photographer.logo and request):
            return None
        if not has_feature(obj.photographer, BRANDING):
            return None
        return request.build_absolute_uri(obj.photographer.logo.url)

    def get_share_url(self, obj):
        return build_gallery_share_url(obj)

    # design_settings also holds photographer-only blocks (watermark config,
    # download rules with the contacts allow-list, PIN counters, anything a
    # future setting adds). The public payload is an ALLOWLIST of presentation
    # keys, each re-checked against the fixed vocabulary, so nothing else can
    # reach a client and a stale/legacy value is dropped instead of returned.
    # Typography additionally comes back resolved (`typography_style`) from the
    # server-side style table; the stored id is never turned into CSS here.
    _PUBLIC_DESIGN_SETTINGS_KEYS = frozenset(DESIGN_CHOICES) | {'gridSpacing', 'coverPhoto'}

    def get_design_settings(self, obj):
        settings_blob = obj.design_settings
        if not isinstance(settings_blob, dict):
            return {}
        public = {
            key: value for key, value in settings_blob.items()
            if key in self._PUBLIC_DESIGN_SETTINGS_KEYS and key != 'coverPhoto'
        }
        clean, _ = validate_presentation(public)
        # coverPhoto is the Design picker's remembered photo id (shown only as
        # a selection state); it is a string id, never a path or URL.
        if isinstance(settings_blob.get('coverPhoto'), str):
            clean['coverPhoto'] = settings_blob['coverPhoto']
        return clean

    def get_typography_style(self, obj):
        settings_blob = obj.design_settings if isinstance(obj.design_settings, dict) else {}
        return resolve_typography(settings_blob.get('typography'))

    def get_cover_url(self, obj):
        """
        Same source of truth as the dashboard side
        (GalleryDetailSerializer.get_cover_url) — the model's cover_photo
        FK, which GalleryUpdateSerializer keeps in sync with the Design
        page's selection and with auto-assignment on first processed
        upload. Falls back to poster_image for a video cover (videos have
        no thumbnail_file/display_file of their own).
        """
        request = self.context.get('request')
        cover = obj.cover_photo
        if not cover or not request:
            return None
        image_field = (
            getattr(cover, 'display_file', None)
            or getattr(cover, 'thumbnail_file', None)
            or getattr(cover, 'poster_image', None)
        )
        if not image_field or not hasattr(image_field, 'url'):
            return None
        url = request.build_absolute_uri(image_field.url)
        # Image derivatives carry the watermark version; a video poster does not.
        return url if image_field is getattr(cover, 'poster_image', None) else versioned_url(url, cover)


    def get_cover_medium_url(self, obj):
        """
        The 1280px tier of the same cover, so the hero <img> can offer the
        browser a srcset (medium for phones/small windows, display for wide
        screens) instead of every visitor downloading the 2048px file.
        Image covers only — a video poster has no size tiers.
        """
        request = self.context.get('request')
        cover = obj.cover_photo
        if not cover or not request or not cover.medium_file or not cover.display_file:
            return None
        return versioned_url(request.build_absolute_uri(cover.medium_file.url), cover)


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

        # The token goes back to the browser once; only its hash is stored (7-B, row 89).
        return ClientSession.objects.issue(
            gallery,
            email=email,
            # The address the throttles see (NUM_PROXIES), never a client-sent header (row 78).
            ip_address=client_ip(request) if request else None,
            has_download_access=gallery.allow_download
        )

    def to_representation(self, instance):
        """Returns the token issued by create() (it exists nowhere else afterwards)."""
        return {
            'access_token': instance.raw_token,
            'has_download_access': instance.has_download_access
        }


# ─────────────────────────────────────────────────────────────
# FAVORITES (Phase 3)
# ─────────────────────────────────────────────────────────────

class FavoriteToggleSerializer(serializers.Serializer):
    """
    Input validation for POST/DELETE favorite requests. `client_uid` is
    only required for OPEN (non-password-protected) galleries — for a
    protected gallery the view derives client identity from the already-
    verified session token instead, so a client can't fabricate an
    arbitrary identity for a gallery it would otherwise need a password
    to enter. See Favorite's docstring (apps/clients/models.py) for the
    full identity model.
    """
    media_asset_id = serializers.UUIDField()
    client_uid = serializers.CharField(
        required=False, allow_blank=True, max_length=128, default=''
    )


class PhotographerFavoriteSerializer(serializers.ModelSerializer):
    """
    Photographer-facing favorite activity row: which photo, by whom
    (email when known — never the raw client_key/token), and when.
    """
    media_asset_id = serializers.UUIDField(source='media_asset.id', read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    title = serializers.CharField(source='media_asset.title', read_only=True)
    original_name = serializers.CharField(source='media_asset.original_name', read_only=True)
    set_name = serializers.SerializerMethodField()

    class Meta:
        model = Favorite
        fields = ['id', 'media_asset_id', 'title', 'original_name', 'set_name', 'thumbnail_url', 'email', 'created_at']
        read_only_fields = fields

    def get_set_name(self, obj):
        """The photo set the favorited photo sits in (null when it is in none)."""
        asset = obj.media_asset
        return asset.photo_set.name if asset.photo_set_id else None

    def get_thumbnail_url(self, obj):
        request = self.context.get('request')
        asset = obj.media_asset
        image_field = getattr(asset, 'thumbnail_file', None) or getattr(asset, 'poster_image', None)
        if not image_field or not request:
            return None
        return request.build_absolute_uri(image_field.url) if hasattr(image_field, 'url') else None


# ─────────────────────────────────────────────────────────────
# DOWNLOAD ACTIVITY (Phase 3)
# ─────────────────────────────────────────────────────────────

class DownloadLogSerializer(serializers.ModelSerializer):
    """
    Photographer-facing download activity row. media_asset/photo_set are
    nullable FKs (a full-gallery ZIP download has neither) — plain
    SerializerMethodFields rather than dotted `source=` traversal, since
    DRF's dotted-attribute lookup raises AttributeError (not a clean
    None) when an intermediate relation is null.
    """
    media_asset_id = serializers.SerializerMethodField()
    media_asset_title = serializers.SerializerMethodField()
    media_asset_name = serializers.SerializerMethodField()
    photo_set_name = serializers.SerializerMethodField()
    set_names = serializers.SerializerMethodField()
    scope = serializers.SerializerMethodField()
    pin_state = serializers.SerializerMethodField()
    filename = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = DownloadLog
        fields = [
            'id', 'email', 'download_type', 'resolution', 'pin_verified', 'pin_state',
            'media_asset_id', 'media_asset_title', 'media_asset_name', 'photo_set_name', 'set_names', 'scope', 'filename',
            'photo_count', 'thumbnail_url', 'created_at',
        ]
        read_only_fields = fields

    def get_thumbnail_url(self, obj):
        """The downloaded photo's thumbnail (single-photo rows only; a ZIP has no single image)."""
        request = self.context.get('request')
        asset = obj.media_asset if obj.media_asset_id else None
        if asset is None or request is None:
            return None
        image = asset.thumbnail_file or asset.poster_image
        return request.build_absolute_uri(image.url) if image else None

    def get_media_asset_name(self, obj):
        """The uploaded filename of the downloaded photo/video (null for a whole-gallery ZIP)."""
        if not obj.media_asset_id or not obj.media_asset:
            return None
        return obj.media_asset.original_name or None

    def get_filename(self, obj):
        """
        The attachment name the server actually sent, as stored on the row.
        Rows written before that field existed fall back to the old derivation.
        """
        if obj.filename:
            return obj.filename
        if obj.media_asset_id and obj.media_asset:
            return obj.media_asset.original_name or None
        stem = obj.gallery.slug
        if obj.photo_set_id and obj.photo_set:
            stem = f'{stem}-{obj.photo_set.name}'
        return f'{stem}.zip'

    def get_scope(self, obj):
        """What the client actually downloaded, in words."""
        if obj.download_type == DownloadLog.DownloadType.GALLERY:
            return f'Set: {obj.photo_set.name}' if obj.photo_set_id and obj.photo_set else 'Entire gallery'
        return 'Single video' if obj.download_type == DownloadLog.DownloadType.VIDEO else 'Single photo'

    def get_pin_state(self, obj):
        """'verified' = the client passed the gallery's download PIN; 'not_required' = no PIN applied."""
        return 'verified' if obj.pin_verified else 'not_required'

    def get_media_asset_id(self, obj):
        return str(obj.media_asset_id) if obj.media_asset_id else None

    def get_media_asset_title(self, obj):
        # `title` is optional on uploads and usually blank; the filename is
        # what lets a photographer recognise which photo was downloaded.
        if not obj.media_asset_id or not obj.media_asset:
            return None
        return obj.media_asset.title or obj.media_asset.original_name or None

    def get_set_names(self, obj):
        """Every set the download came from, as stored on the row (never re-derived)."""
        names = [n for n in (obj.set_names or []) if isinstance(n, str) and n]
        if names:
            return names
        single = self.get_photo_set_name_single(obj)
        return [single] if single else []

    def get_photo_set_name_single(self, obj):
        # A set-scoped ZIP records its set; a single photo/video belongs to
        # whichever set the downloaded asset sits in.
        if obj.photo_set_id and obj.photo_set:
            return obj.photo_set.name
        asset = obj.media_asset if obj.media_asset_id else None
        if asset is not None and asset.photo_set_id and asset.photo_set:
            return asset.photo_set.name
        return None

    def get_photo_set_name(self, obj):
        """The set name, or "A, B" for a download spanning several sets; null when it had none."""
        return ', '.join(self.get_set_names(obj)) or None
