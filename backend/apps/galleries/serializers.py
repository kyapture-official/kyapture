# C:/Users/LENOVO/Desktop/kyapture/backend/apps/galleries/serializers.py
import bcrypt 
from rest_framework import serializers
from apps.core.share import build_gallery_share_url
from apps.core.watermark import validate_watermark_config
from apps.users.collection_defaults import apply_collection_defaults
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email as django_validate_email

from apps.subscriptions.entitlements import ORIGINAL_DOWNLOAD, WATERMARK, require_feature

from apps.core.utils import generate_unique_slug, sanitize_text
from apps.photos.models import MediaAsset
from .models import Gallery

RESERVED_GALLERY_SLUGS = {
    'search', 'dashboard', 'stats',
    'publish', 'set-password',
    'unlock', 'download', 'video', 'photo', 'stream',
    'set-download-pin', 'favorites', 'download-logs', 'sets',
}

DOWNLOAD_SIZE_VALUES = {'download', 'web'}
# The three derivative tiers this app actually generates for the public
# gallery (apps/core/utils.py::_DISPLAY_TIERS: display/medium/thumbnail).
# Pixieset's own Web Size picker labels its three options 2048/1024/640 —
# we show our real numbers (2048/1280/640) instead of mislabeling the
# 1280px "medium" tier as 1024px (docs/KYAPTURE_AGENT_RULES.md: never
# invent measurements).
WEB_PX_VALUES = {2048, 1280, 640}
HIGH_RES_MODES = {'3600', 'original'}
MAX_ALLOWED_EMAILS = 500


def normalize_download_settings(value, *, instance=None, user=None):
    """
    Validate + normalize the gallery's download-policy block, stored under
    design_settings.downloads.

    Backward compatible with the original Task 1R.4 shape
    ({allowed_sizes, require_email}): a payload sending only those two
    keys still works exactly as before, and existing stored galleries
    that predate the newer keys get sane defaults for them.

    Task 1R.6 additions (Pixieset-style Download settings, product rules
    in docs/KYAPTURE_AGENT_RULES.md's task brief):
      - high_res: {enabled, mode}  mode 'original' is Pro+ only (checked
        here at save time via require_feature; the download-time path in
        apps/clients/download_access.py separately falls back to '3600'
        if the plan has since lapsed, so a stored 'original' choice is
        never silently honored for a Free/expired account).
      - web: {enabled, px}         px in WEB_PX_VALUES.
      - sets_enabled: null (all sets) or a list of this gallery's own
        PhotoSet ids — validated against `instance.sets` when an instance
        is available (an update; not on first create).
      - limit_total: null or a positive integer cap on total downloads.
      - restrict_contacts + allowed_emails: an explicit allow-list gate.

    allowed_sizes is still computed and returned (derived from
    high_res.enabled/web.enabled) because
    apps/clients/download_access.py's resolution_is_allowed() and every
    existing caller already key off it exactly as before — one source of
    truth, no duplicate "is this size on" flag.
    """
    if not isinstance(value, dict):
        raise serializers.ValidationError('downloads must be an object.')

    def _bool(d, key, default):
        v = d.get(key, default)
        if not isinstance(v, bool):
            raise serializers.ValidationError({key: f'{key} must be true or false.'})
        return v

    legacy_sizes = value.get('allowed_sizes')
    legacy_sizes = legacy_sizes if isinstance(legacy_sizes, list) else None
    if legacy_sizes is not None and any(not isinstance(s, str) for s in legacy_sizes):
        raise serializers.ValidationError({'allowed_sizes': 'Each size must be "download" or "web".'})

    high_res_in = value.get('high_res') if isinstance(value.get('high_res'), dict) else {}
    web_in = value.get('web') if isinstance(value.get('web'), dict) else {}

    if 'enabled' in high_res_in:
        high_res_enabled = _bool(high_res_in, 'enabled', True)
    elif legacy_sizes is not None:
        high_res_enabled = 'download' in legacy_sizes
    else:
        high_res_enabled = True

    if 'enabled' in web_in:
        web_enabled = _bool(web_in, 'enabled', True)
    elif legacy_sizes is not None:
        web_enabled = 'web' in legacy_sizes
    else:
        web_enabled = True

    if not high_res_enabled and not web_enabled:
        raise serializers.ValidationError({'allowed_sizes': 'Choose at least one download size.'})

    mode = high_res_in.get('mode', '3600')
    if mode not in HIGH_RES_MODES:
        raise serializers.ValidationError({'high_res': {'mode': 'mode must be "3600" or "original".'}})
    if mode == 'original' and high_res_enabled and user is not None:
        # Free users may never SAVE 'original' — not even disabled-but-stored,
        # since a lapsed-then-renewed Pro photographer should never find an
        # old Free-era attempt silently reactivated. Reject outright (403).
        require_feature(user, ORIGINAL_DOWNLOAD)

    px = web_in.get('px', 2048)
    if px not in WEB_PX_VALUES:
        raise serializers.ValidationError({'web': {'px': 'px must be 2048, 1280 or 640.'}})

    allowed_sizes = (['download'] if high_res_enabled else []) + (['web'] if web_enabled else [])

    if 'require_email' in value and not isinstance(value['require_email'], bool):
        raise serializers.ValidationError({'require_email': 'require_email must be true or false.'})
    require_email = value.get('require_email', True)

    sets_enabled = value.get('sets_enabled', None)
    if sets_enabled is not None:
        if not isinstance(sets_enabled, list) or any(not isinstance(s, str) for s in sets_enabled):
            raise serializers.ValidationError({
                'sets_enabled': 'sets_enabled must be a list of set ids, or null for all sets.'
            })
        if instance is not None and instance.pk:
            valid_ids = {str(pk) for pk in instance.sets.values_list('id', flat=True)}
            if any(s not in valid_ids for s in sets_enabled):
                raise serializers.ValidationError({
                    'sets_enabled': 'One or more sets do not belong to this gallery.'
                })
        sets_enabled = sorted(set(sets_enabled))

    limit_total = value.get('limit_total', None)
    if limit_total is not None:
        if isinstance(limit_total, bool) or not isinstance(limit_total, int) or limit_total < 1:
            raise serializers.ValidationError({
                'limit_total': 'limit_total must be a positive whole number, or null for no limit.'
            })

    restrict_contacts = _bool(value, 'restrict_contacts', False)
    allowed_emails_in = value.get('allowed_emails', [])
    if not isinstance(allowed_emails_in, list):
        raise serializers.ValidationError({'allowed_emails': 'allowed_emails must be a list of email addresses.'})
    allowed_emails = []
    seen = set()
    for raw in allowed_emails_in[:MAX_ALLOWED_EMAILS]:
        email = raw.strip().lower() if isinstance(raw, str) else ''
        if not email or email in seen:
            continue
        try:
            django_validate_email(email)
        except DjangoValidationError:
            raise serializers.ValidationError({'allowed_emails': f'"{raw}" is not a valid email address.'})
        seen.add(email)
        allowed_emails.append(email)
    if restrict_contacts and not allowed_emails:
        raise serializers.ValidationError({
            'allowed_emails': 'Add at least one email address to restrict downloads to.'
        })

    return {
        'allowed_sizes': allowed_sizes,
        # Frictionless downloads must be saved explicitly, never inferred
        # from a missing setting on an older gallery.
        'require_email': require_email,
        'high_res': {'enabled': high_res_enabled, 'mode': mode},
        'web': {'enabled': web_enabled, 'px': px},
        'sets_enabled': sets_enabled,
        'limit_total': limit_total,
        'restrict_contacts': restrict_contacts,
        'allowed_emails': allowed_emails,
    }


def normalize_privacy_settings(value, existing):
    """
    Validate + normalize design_settings.privacy: currently just the
    optional "Limit PIN Usage" cap (Pixieset Advanced Settings), moved to
    the Privacy tab per the 1R.6 product rule that every gate secret/limit
    lives there, never on the Download tab.

    pin_use_count is an internal counter (how many times the CURRENT PIN
    has successfully unlocked a download — apps/clients/views.py
    ::PublicDownloadAccessView) that a photographer request never sets
    directly; it is always carried forward from the existing stored value.
    GallerySetDownloadPinView resets it to 0 whenever the PIN itself is
    set, changed or cleared, since a new PIN should start its own count.
    """
    if not isinstance(value, dict):
        raise serializers.ValidationError('privacy must be an object.')
    pin_limit = value.get('pin_limit', None)
    if pin_limit is not None:
        if isinstance(pin_limit, bool) or not isinstance(pin_limit, int) or pin_limit < 1:
            raise serializers.ValidationError({
                'pin_limit': 'pin_limit must be a positive whole number, or null for no limit.'
            })
    existing_count = existing.get('pin_use_count', 0) if isinstance(existing, dict) else 0
    if not isinstance(existing_count, int):
        existing_count = 0
    return {'pin_limit': pin_limit, 'pin_use_count': existing_count}

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


class MediaAssetSimpleSerializer(serializers.ModelSerializer):
    display_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    is_cover = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = ['id', 'display_url', 'thumbnail_url', 'is_cover']

    def get_is_cover(self, obj):
        try:
            return getattr(obj, 'cover_for_gallery', None) is not None or (
                hasattr(obj, 'gallery') and obj.gallery and obj.gallery.cover_photo_id == obj.id
            )
        except Exception:
            return False

    def get_display_url(self, obj):
        request = self.context.get('request')
        img = getattr(obj, 'display_file', None) or getattr(obj, 'thumbnail_file', None)
        if not img and hasattr(obj, 'file'):
            img = obj.file
        return request.build_absolute_uri(img.url) if img and hasattr(img, 'url') and request else None

    def get_thumbnail_url(self, obj):
        request = self.context.get('request')
        img = getattr(obj, 'thumbnail_file', None) or getattr(obj, 'display_file', None)
        if not img and hasattr(obj, 'file'):
            img = obj.file
        return request.build_absolute_uri(img.url) if img and hasattr(img, 'url') and request else None


class GalleryDetailSerializer(serializers.ModelSerializer):
    """
    GET /api/v1/galleries/{slug}/
    Returns complete gallery settings. Protects password hash.
    """
    cover_url = serializers.SerializerMethodField()
    photo_count = serializers.IntegerField(read_only=True, default=0)
    is_downloadable = serializers.BooleanField(source='allow_download', read_only=True, default=False)
    has_password = serializers.SerializerMethodField()
    has_download_pin = serializers.SerializerMethodField()
    share_url = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()

    owner_username = serializers.CharField(source='photographer.username', read_only=True, default='')
    photographer_username = serializers.CharField(source='photographer.username', read_only=True, default='')

    class Meta:
        model = Gallery
        fields = [
            'id', 'title', 'slug', 'description', 'branding_color',
            'cover_url', 'photo_count', 'is_downloadable',
            'is_active', 'event_date', 'expires_at', 'is_published', 'has_password',
            'has_download_pin', 'share_url',
            'owner_username', 'photographer_username',
            'watermark_enabled', 'design_settings', 'photos',
            'password_hash', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']
        extra_kwargs = {
            'password_hash': {'write_only': True},
        }

    def get_photos(self, obj):
        """
        The first 20 assets (MediaAsset's own ordering) for the Design page's
        preview strip. This used to probe several reverse-relation names and
        run `.exists()` before fetching — two queries (plus a lazy gallery
        lookup per asset) for what is one bounded read through `assets`.
        """
        return MediaAssetSimpleSerializer(
            obj.assets.all()[:20], many=True, context=self.context
        ).data

    def get_cover_url(self, obj):
        request = self.context.get('request')
        cover = obj.cover_photo
        if not cover or not request:
            return None
        image_field = (
            getattr(cover, 'display_file', None) or getattr(cover, 'thumbnail_file', None) or getattr(cover, 'file', None)
        )
        if not image_field:
            return None
        return request.build_absolute_uri(image_field.url) if hasattr(image_field, 'url') else None

    def get_has_password(self, obj):
        return bool(obj.password_hash)

    def get_has_download_pin(self, obj):
        return bool(obj.download_pin_hash)

    def get_share_url(self, obj):
        return build_gallery_share_url(obj)

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

    def validate_watermark_enabled(self, value):
        """Watermark is a Pro+ feature; turning it OFF is always allowed."""
        if value:
            require_feature(self.context['request'].user, WATERMARK)
        return value

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

        # The photographer's Collection Defaults fill in anything this request
        # did not set explicitly. They are consulted only here, at creation —
        # never when an existing gallery is edited — so they cannot change
        # an existing collection. See apps/users/collection_defaults.py.
        validated_data = apply_collection_defaults(
            photographer, validated_data, set(getattr(self, 'initial_data', {}) or {})
        )

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
            'title', 'description', 'cover_photo', 'design_settings',
            'branding_color','event_date', 'is_password_protected', 'password',
            'is_downloadable', 'watermark_enabled', 'is_published', 'expires_at',
        ]

    def validate_watermark_enabled(self, value):
        """Watermark is a Pro+ feature; turning it OFF is always allowed."""
        if value:
            require_feature(self.context['request'].user, WATERMARK)
        return value

    def validate_design_settings(self, value):
        """
        design_settings is the gallery's small fixed set of look-and-feel
        choices plus the private `watermark` block (type/text/position/
        opacity/size/margin) — see apps/core/watermark.py.

        - The watermark block is validated field by field; nothing
          unvalidated reaches the renderer.
        - Saving a watermark configuration is Pro+ only, enforced here. A
          block identical to what is already stored is not a change, so a
          lapsed photographer's Design page can still save other settings.
        - A save that omits the block (e.g. the Design page, which doesn't
          know about it) keeps the stored one instead of wiping it.
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError('design_settings must be an object.')
        value = dict(value)
        existing = (self.instance.design_settings or {}) if self.instance else {}
        existing_block = existing.get('watermark') if isinstance(existing, dict) else None
        existing_downloads = existing.get('downloads') if isinstance(existing, dict) else None
        existing_privacy = existing.get('privacy') if isinstance(existing, dict) else None

        if 'downloads' in value:
            value['downloads'] = normalize_download_settings(
                value['downloads'], instance=self.instance, user=self.context['request'].user,
            )
        elif existing_downloads is not None:
            # Design-page updates must not erase download rules saved on the
            # Settings page.
            value['downloads'] = existing_downloads

        if 'privacy' in value:
            value['privacy'] = normalize_privacy_settings(value['privacy'], existing_privacy or {})
        elif existing_privacy is not None:
            value['privacy'] = existing_privacy

        if 'watermark' not in value:
            if existing_block is not None:
                value['watermark'] = existing_block
            return value

        incoming = value['watermark']
        if incoming is None:                      # explicit clear: always allowed
            value.pop('watermark')
            return value

        config, errors = validate_watermark_config(incoming)
        if errors:
            raise serializers.ValidationError({'watermark': errors})

        stored_config, _ = validate_watermark_config(existing_block) if isinstance(existing_block, dict) else (None, None)
        if config != stored_config:
            request = self.context['request']
            require_feature(request.user, WATERMARK)
            if config['type'] == 'logo' and not request.user.logo:
                raise serializers.ValidationError({
                    'watermark': {'type': 'Upload your business logo in Branding settings to use a logo watermark.'}
                })
        value['watermark'] = config
        return value

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
        hashes it using raw bcrypt.

        Locked product decision: gallery URLs are stable — the slug is
        assigned once at creation and a title edit must NEVER change it
        (changing the slug would break every link already shared with
        clients). So, unlike GalleryCreateSerializer.create(), title
        changes here only ever touch instance.title, never instance.slug.

        If design_settings carries a 'coverPhoto' id (the Design page's
        cover-photo picker), sync it onto the model's cover_photo FK so
        there is a single source of truth for "which photo is the cover"
        driving both the dashboard listing (GalleryListSerializer.cover_url)
        and the client-facing hero (PublicGallerySerializer.cover_url) —
        validated the same way an explicit cover_photo field is: must
        belong to this gallery.
        """
        raw_password = validated_data.pop('password', '').strip()

        if raw_password:
            instance.password_hash = bcrypt.hashpw(
                raw_password.encode('utf-8'), bcrypt.gensalt()
            ).decode('utf-8')
        elif not validated_data.get('is_password_protected', instance.is_password_protected):
            instance.password_hash = None

        design_settings = validated_data.get('design_settings')
        if isinstance(design_settings, dict) and 'coverPhoto' in design_settings:
            cover_photo_id = design_settings.get('coverPhoto')
            if cover_photo_id:
                cover_asset = MediaAsset.objects.filter(
                    pk=cover_photo_id, gallery_id=instance.pk
                ).first()
                if cover_asset:
                    validated_data['cover_photo'] = cover_asset
            else:
                validated_data['cover_photo'] = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

    def to_representation(self, instance):
        instance.photo_count = instance.assets.count()
        return GalleryDetailSerializer(instance, context=self.context).data
